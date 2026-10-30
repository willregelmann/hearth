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
  - Arrivals count as taken in only after the turn that was shown them finished ok
    (docs/capabilities/WAKE.md). They are marked shown while it runs, so the turn's own Front
    Desk server, recovering on the same seat, doesn't wake them a second time. A failed turn puts
    them back to arrived, logged at ERROR, and the conversation is woken again after a backoff
    that doubles with each failure in a row.
  - A wake outlives a restart. Front Desk's own recovery wakes only what is still arrived, so a
    host killed mid-turn would leave its arrivals shown and never woken; recover() wakes every
    conversation with a waking message pending in either state.
  - What arrives for the conversation during a turn runs in a next turn, straight after. Whether
    a channel push reaches a `claude -p` turn is not relied on.
  - A conversation that a live Claude Code process outside this host has open is never resumed:
    that would be two writers on one transcript. Its own server pushes the message into it; if it
    closes with the message still pending, the next sweep runs the turn.
  - start() returns None: a message to the default channel waits for adopt, as Front Desk
    already does for hosts that can't start a conversation.
  - An offer is carried out whether or not a session is open: every seat this host attends,
    its own included, holds the handlers from the identity's offers file.
  - The agent's status is served beside its turns (hearth.status), and only read: a host whose
    status can't be served runs the same without it.

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
import math
import os
import pwd
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from frontdesk import Desk, offers, wire
from frontdesk.hosts.claude_code import sessions
from hearth import status

logger = logging.getLogger("hearth.host")

TURN = "/opt/hearth/home/turn"
SWEEP_S = 5.0
RETRY_S, RETRY_MAX_S = 30.0, 1800.0
# The turn's reply text is discarded (turn_runner), so the agent has to know nobody reads it.
RESUMED = ("Hearth started this turn because a message came for this conversation while nobody had it "
           "open. Your reply text isn't delivered to anyone: whatever someone should see, send it through "
           "the Front Desk.")


def turn_runner(conversation: str, prompt: str, *, turn: str = TURN, timeout: int = 1800) -> int:
    """One turn in ``conversation`` (a Claude Code session id), through the installed runner.

    The turn's stdout is its reply text, which already sits in the session's transcript, inside
    the tenant's home. It is discarded here: inherited, it would land in the system journal,
    which adm and will can read (Ash, Buster 2026-10-16). stderr is kept for the journal: turn
    writes only its own one-line errors there, never prompt or reply text."""
    return subprocess.run([turn, "--trigger", "frontdesk", "--resume", conversation,
                           "--timeout", str(timeout), prompt],
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          timeout=timeout + 60).returncode


def configure_logging() -> None:
    """INFO for Hearth, WARNING for the HTTP client: httpx logs every /sync at INFO, one line per
    seat every few seconds (about 17k a day per tenant on Buster), which buries the host's own."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("hearth").setLevel(logging.INFO)
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def claude_dirs() -> tuple[str, ...]:
    """Where a tenant's claude binaries live: any version the tenant has installed, and root's
    store. A live session keeps running the version it started on, after an update repoints
    ~/.local/bin/claude (Ash, #91 R1 B), so the version isn't pinned here."""
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    return (os.path.realpath(home / ".local" / "share" / "claude" / "versions"), "/opt/hearth/claude")


def _exe(pid: int) -> Optional[str]:
    """The binary a process runs, as the kernel names it. A binary deleted or replaced while it
    runs reads as "<path> (deleted)" (Ash, #91 R1 C); the directory test below still holds for it,
    since the suffix comes after the file name."""
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None


def attended(home: Path, conversation: str, *, dirs: Optional[tuple[str, ...]] = None) -> bool:
    """A live claude process that isn't this host's own descendant has ``conversation`` open.

    Front Desk's SessionStart hook records the session id against every ancestor of the hook
    (sessions.record), so the records also name shells, tmux and, for its own turns, this host.
    A record counts only if its process is still the one recorded (same start time), runs a
    claude binary (one under ``dirs``), and doesn't descend from this process.

    Errs toward True: a false True only defers a turn, a false False is two writers on one
    transcript. Only Claude Code sessions are ever attended; a seat that isn't a session id has
    no records, so it is never skipped."""
    dirs = dirs or claude_dirs()
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
        exe = _exe(pid)
        if exe is None or not any(exe.startswith(d.rstrip("/") + "/") for d in dirs):
            continue
        if pid == me or me in sessions.ancestors(pid):
            continue
        return True
    return False


class HearthHost:
    def __init__(self, desk, runner: Callable[[str, str], int] = turn_runner,
                 is_attended: Optional[Callable[[str], bool]] = None,
                 retry_s: float = RETRY_S, retry_max_s: float = RETRY_MAX_S):
        self.desk, self.runner = desk, runner
        self.is_attended = is_attended or (lambda c: attended(desk.state_dir, c))
        self.retry_s, self.retry_max_s = retry_s, retry_max_s
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task] = set()
        self.deferred: set[str] = set()
        self.failed: dict[str, tuple[int, float]] = {}   # conversation: (failures in a row, when to try again)
        self.live: dict[str, float] = {}   # conversation: when its running turn started (wall clock)

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

    async def retry_failed(self) -> None:
        """Wake again what a failed turn left pending, once its backoff has passed."""
        now = time.monotonic()
        for conversation, (failures, due) in list(self.failed.items()):
            if due <= now:
                self.failed[conversation] = (failures, math.inf)   # one retry in flight, not one per sweep
                await self.wake(conversation)

    async def recover(self) -> None:
        """Wake every conversation with a waking message still pending, shown or not."""
        for channel in self.desk.ledger.live_channels():
            if any(json.loads(row["arrival"]).get("arrive") == wire.WAKE
                   for row in self.desk.ledger.pending(channel["handle"])):
                await self.wake(channel["conversation"])

    async def _turn(self, conversation: str) -> None:
        async with self._locks.setdefault(conversation, asyncio.Lock()):
            while True:
                if self.is_attended(conversation):
                    self.deferred.add(conversation)
                    logger.info("%s is open in a live session; it takes its own messages", conversation)
                    return
                arrivals = await self.desk.take(conversation, mark=False)
                if not arrivals:
                    self.failed.pop(conversation, None)
                    return
                refs = [a.ref for a in arrivals]
                self.desk.mark_shown(refs)
                prompt = "\n\n".join([RESUMED] + [wire.render(a) for a in arrivals])
                self.live[conversation] = time.time()
                try:
                    rc = await asyncio.to_thread(self.runner, conversation, prompt)
                except Exception as exc:
                    rc = None
                    logger.error("turn in %s could not run: %s", conversation, exc)
                finally:
                    self.live.pop(conversation, None)
                if rc != 0:
                    for ref in refs:   # back to arrived, unless the turn's own Stop hook took it in
                        row = self.desk.ledger.inbox_row(ref)
                        if row is not None and row["state"] == "shown":
                            self.desk.ledger.set_state(ref, wire.ARRIVED)
                    failures = self.failed.get(conversation, (0, 0.0))[0] + 1
                    backoff = min(self.retry_s * 2 ** (failures - 1), self.retry_max_s)
                    self.failed[conversation] = (failures, time.monotonic() + backoff)
                    logger.error("turn in %s failed (rc %s); %d message(s) stay pending, trying again in %ds",
                                 conversation, rc, len(arrivals), backoff)
                    return
                await self.desk.commit(conversation, also=refs)
                self.failed.pop(conversation, None)


def turn_ledger() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / ".hearth" / "ledger.jsonl"


async def serve(home: Path, host_factory: Callable = HearthHost, *, sweep_s: float = SWEEP_S,
                poll_ms: int = 5000, stop: Optional[asyncio.Event] = None,
                status_path: Optional[Path] = None, ledger: Optional[Path] = None) -> None:
    """Stay at the desk for every live conversation of the identity in ``home``: one Desk per
    channel seat, sharing one host. A seat a live session has open is left to that session.
    The host's own seat is always attended, so a request reaches a desk that can carry it out
    even when no conversation is listed.

    With ``status_path``, the agent's status is served there (hearth.status). A status that
    can't be served is logged and the host carries on: the agent runs the same either way."""
    catalog = offers.load_catalog(home)
    main = Desk(home, seat="hearth")
    host = host_factory(main)
    main.host = host
    seats: dict[str, tuple[Desk, asyncio.Task]] = {}
    stop = stop or asyncio.Event()
    reporting = None
    if status_path is not None:
        reporter = status.Reporter(host, pwd.getpwuid(os.getuid()).pw_name, ledger or turn_ledger())
        try:
            reporting = await status.serve(reporter, status_path)
        except Exception as exc:
            logger.error("status not served: %s", exc)
    await host.recover()

    async def attend(desk):
        # Whichever seat claims a request carries it out, so every seat holds the offers' handlers.
        await offers.attach(desk, catalog)
        await desk.run(host, poll_ms=poll_ms)

    async def drop(seat):
        desk, task = seats.pop(seat)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await desk.close()

    try:
        while not stop.is_set():
            want = {r["seat"] for r in main.ledger.live_channels() if r["seat"]}
            want = {s for s in want if not host.is_attended(s)} | {main.seat}
            for seat in list(seats):
                if seat not in want or seats[seat][1].done():
                    task = seats[seat][1]
                    if task.done() and not task.cancelled() and task.exception():
                        logger.error("seat %s stopped: %r; starting it again", seat, task.exception())
                    await drop(seat)
            for seat in want - set(seats):
                desk = Desk(home, seat=seat)
                seats[seat] = (desk, asyncio.get_running_loop().create_task(attend(desk)))
            await host.retry_deferred()
            await host.retry_failed()
            try:
                await asyncio.wait_for(stop.wait(), sweep_s)
            except asyncio.TimeoutError:
                pass
    finally:
        for seat in list(seats):
            await drop(seat)
        await host.drain()
        await main.close()
        if reporting is not None:
            await reporting.stop(grace=1)


def main() -> int:
    from hearth import tenantcheck
    configure_logging()
    t = tenantcheck.Tenant(Path(pwd.getpwuid(os.getuid()).pw_dir))
    rc, msg = tenantcheck.frontdesk_home(t)
    if rc != tenantcheck.GREEN:
        print(f"hearth.host: {msg}", file=sys.stderr)
        return 78   # EX_CONFIG: systemd doesn't restart-loop on it (RestartPreventExitStatus)
    # systemd's RuntimeDirectory= (hearth-host@.service): made for this tenant only, gone when it stops
    runtime = os.environ.get("RUNTIME_DIRECTORY")
    if runtime is None:
        logger.error("no RUNTIME_DIRECTORY; status not served")
    asyncio.run(serve(tenantcheck.frontdesk_home_path(t),
                      status_path=Path(runtime) / "status.sock" if runtime else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
