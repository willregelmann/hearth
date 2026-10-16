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
  - Arrivals count as taken in only after the turn that was shown them finished ok. They are
    marked shown while it runs, so the turn's own Front Desk server, recovering on the same seat,
    doesn't wake them a second time. A failed turn puts them back to arrived, logged at ERROR,
    and the next wake (or the desk's recovery after a restart) shows them again.
  - What arrives for the conversation during a turn runs in a next turn, straight after. Whether
    a channel push reaches a `claude -p` turn is not relied on.
  - A conversation that a live Claude Code process outside this host has open is never resumed:
    that would be two writers on one transcript. Its own server pushes the message into it; if it
    closes with the message still pending, the next sweep runs the turn.
  - start() returns None: a message to the default channel waits for adopt, as Front Desk
    already does for hosts that can't start a conversation.

Seats. Front Desk binds each channel to the seat that listed it, and a Claude Code session's
server uses its session id as its seat; a desk on any other seat leaves the message to that seat
(desk.py _route). So the service (``serve``) keeps one Desk per live channel's seat, all sharing
this host. `claude -p --resume` keeps the session id (Ash ran it, 2.1.288 and 2.1.300), so the
resumed turn's own server takes the same seat; claims are exactly-once, so one of them handles
each message. Needs Front Desk's "a seat never claims another seat's message" (frontdesk
foil/claim-own-seat): without it two seats can lose a message between them.

The turn itself is a runner: ``runner(conversation, prompt) -> rc``. The real one is Hearth's
installed turn runner, run as the tenant, resuming the session. Tests pass a fake.

    python -I -m hearth.host        as the tenant: the service (hearth-host@<tenant>.service)
"""
import asyncio
import json
import logging
import os
import pwd
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from frontdesk import Desk, wire
from frontdesk.hosts.claude_code import sessions

logger = logging.getLogger("hearth.host")

TURN = "/opt/hearth/home/turn"
SWEEP_S = 5.0


def turn_runner(conversation: str, prompt: str, *, turn: str = TURN, timeout: int = 1800) -> int:
    """One turn in ``conversation`` (a Claude Code session id), through the installed runner."""
    return subprocess.run([turn, "--trigger", "frontdesk", "--resume", conversation,
                           "--timeout", str(timeout), prompt],
                          stdin=subprocess.DEVNULL, timeout=timeout + 60).returncode


def claude_exe() -> str:
    """What a tenant's live session runs: its pinned claude binary, links resolved."""
    return os.path.realpath(Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local" / "bin" / "claude")


def attended(home: Path, conversation: str, *, exe: Optional[str] = None) -> bool:
    """A live claude process that isn't this host's own descendant has ``conversation`` open.

    Front Desk's SessionStart hook records the session id against every ancestor of the hook
    (sessions.record), so the records also name shells, tmux and, for its own turns, this host.
    A record counts only if its process is still the one recorded (same start time), runs the
    claude binary, and doesn't descend from this process."""
    exe = exe or claude_exe()
    try:
        entries = list((Path(home) / "claude-sessions").iterdir())
    except OSError:
        return False
    me = os.getpid()
    for f in entries:
        try:
            pid, entry = int(f.name), json.loads(f.read_text())
        except (ValueError, OSError):
            continue
        if entry.get("session") != conversation or entry.get("started") != sessions._started(pid):
            continue
        try:
            if os.path.realpath(f"/proc/{pid}/exe") != exe:
                continue
        except OSError:
            continue
        if pid == me or me in sessions.ancestors(pid):
            continue
        return True
    return False


class HearthHost:
    def __init__(self, desk, runner: Callable[[str, str], int] = turn_runner,
                 is_attended: Optional[Callable[[str], bool]] = None):
        self.desk, self.runner = desk, runner
        self.is_attended = is_attended or (lambda c: attended(desk.state_dir, c))
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task] = set()
        self.deferred: set[str] = set()

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

    async def retry_deferred(self) -> None:
        """Wake again what was skipped because a live session had it open, once it hasn't."""
        for conversation in list(self.deferred):
            if not self.is_attended(conversation):
                self.deferred.discard(conversation)
                await self.wake(conversation)

    async def _turn(self, conversation: str) -> None:
        async with self._locks.setdefault(conversation, asyncio.Lock()):
            while True:
                if self.is_attended(conversation):
                    self.deferred.add(conversation)
                    logger.info("%s is open in a live session; it takes its own messages", conversation)
                    return
                arrivals = await self.desk.take(conversation, mark=False)
                if not arrivals:
                    return
                refs = [a.ref for a in arrivals]
                self.desk.mark_shown(refs)
                prompt = "\n\n".join(wire.render(a) for a in arrivals)
                try:
                    rc = await asyncio.to_thread(self.runner, conversation, prompt)
                except Exception as exc:
                    rc = None
                    logger.error("turn in %s could not run: %s", conversation, exc)
                if rc != 0:
                    for ref in refs:   # back to arrived, unless the turn's own Stop hook took it in
                        row = self.desk.ledger.inbox_row(ref)
                        if row is not None and row["state"] == "shown":
                            self.desk.ledger.set_state(ref, wire.ARRIVED)
                    logger.error("turn in %s failed (rc %s); %d message(s) stay pending",
                                 conversation, rc, len(arrivals))
                    return
                await self.desk.commit(conversation, also=refs)


async def serve(home: Path, host_factory: Callable = HearthHost, *, sweep_s: float = SWEEP_S,
                poll_ms: int = 5000, stop: Optional[asyncio.Event] = None) -> None:
    """Stay at the desk for every live conversation of the identity in ``home``: one Desk per
    channel seat, sharing one host. A seat a live session has open is left to that session."""
    main = Desk(home, seat="hearth")
    host = host_factory(main)
    main.host = host
    seats: dict[str, tuple[Desk, asyncio.Task]] = {}
    stop = stop or asyncio.Event()

    async def drop(seat):
        desk, task = seats.pop(seat)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await desk.close()

    try:
        while not stop.is_set():
            want = {r["seat"] for r in main.ledger.live_channels() if r["seat"]}
            want = {s for s in want if not host.is_attended(s)}
            for seat in list(seats):
                if seat not in want or seats[seat][1].done():
                    task = seats[seat][1]
                    if task.done() and not task.cancelled() and task.exception():
                        logger.error("seat %s stopped: %r; starting it again", seat, task.exception())
                    await drop(seat)
            for seat in want - set(seats):
                desk = Desk(home, seat=seat)
                seats[seat] = (desk, asyncio.get_running_loop().create_task(desk.run(host, poll_ms=poll_ms)))
            await host.retry_deferred()
            try:
                await asyncio.wait_for(stop.wait(), sweep_s)
            except asyncio.TimeoutError:
                pass
    finally:
        for seat in list(seats):
            await drop(seat)
        await host.drain()
        await main.close()


def main() -> int:
    from hearth import tenantcheck
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    t = tenantcheck.Tenant(Path(pwd.getpwuid(os.getuid()).pw_dir))
    rc, msg = tenantcheck.frontdesk_home(t)
    if rc != tenantcheck.GREEN:
        print(f"hearth.host: {msg}", file=sys.stderr)
        return 78   # EX_CONFIG: systemd doesn't restart-loop on it (RestartPreventExitStatus)
    asyncio.run(serve(tenantcheck.frontdesk_home_path(t)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
