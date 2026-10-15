"""Hearth's Front Desk host: a waking message reaches its conversation even when no turn is open.

Front Desk's Claude Code host can only push into the session that is open right now
(frontdesk hosts/claude_code/server.py, ClaudeCodeHost.wake), so an alarm, a handoff or a peer
message to a closed conversation waits until a person reopens it. This host is the desk's
``Host`` for one agent, run by that agent's long-lived process. When a waking message is due it
resumes the conversation by its session id and runs one turn there, with the arrivals as the
prompt (hearth#51).

What holds:
  - wake() never blocks the desk: the turn runs as its own task, so the desk keeps bringing
    messages in while a turn is running.
  - One turn at a time per conversation. A wake for a conversation that is mid-turn runs after
    it, never beside it; different conversations run in parallel.
  - Arrivals count as taken in only after the turn that was shown them finished ok. A failed
    turn leaves them pending, logged at ERROR, and the next wake (or the desk's recovery after a
    restart) shows them again.
  - start() returns None: a message to the default channel waits for adopt, as Front Desk
    already does for hosts that can't start a conversation.

The turn itself is a runner: ``runner(conversation, prompt) -> rc``. The real one is Hearth's
installed turn runner, run as the tenant, resuming the session. Tests pass a fake.
"""
import asyncio
import logging
import subprocess
from typing import Callable, Optional

from frontdesk import wire

logger = logging.getLogger("hearth.host")

TURN = "/opt/hearth/home/turn"


def turn_runner(conversation: str, prompt: str, *, turn: str = TURN, timeout: int = 1800) -> int:
    """One turn in ``conversation`` (a Claude Code session id), through the installed runner."""
    return subprocess.run([turn, "--trigger", "frontdesk", "--resume", conversation,
                           "--timeout", str(timeout), prompt],
                          stdin=subprocess.DEVNULL, timeout=timeout + 60).returncode


class HearthHost:
    def __init__(self, desk, runner: Callable[[str, str], int] = turn_runner):
        self.desk, self.runner = desk, runner
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task] = set()

    async def wake(self, conversation: str) -> None:
        task = asyncio.get_running_loop().create_task(self._turn(conversation))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def start(self, arrival) -> Optional[str]:
        return None

    async def drain(self) -> None:
        """Wait for every turn started so far (and any it led to) to finish."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _turn(self, conversation: str) -> None:
        async with self._locks.setdefault(conversation, asyncio.Lock()):
            arrivals = await self.desk.take(conversation, mark=False)
            if not arrivals:
                return
            prompt = "\n\n".join(wire.render(a) for a in arrivals)
            try:
                rc = await asyncio.to_thread(self.runner, conversation, prompt)
            except Exception as exc:
                rc = None
                logger.error("turn in %s could not run: %s", conversation, exc)
            if rc != 0:
                logger.error("turn in %s failed (rc %s); %d message(s) stay pending",
                             conversation, rc, len(arrivals))
                return
            await self.desk.commit(conversation, also=[a.ref for a in arrivals])
