"""docs/interfaces/STATUS.md, served by the host (hearth.status) against a real throwaway desk
(:8018). The turn is a fake runner; the status is read the way a reader would, over its socket.

Run: FRONTDESK_TEST_DESK=http://127.0.0.1:8018 python -m pytest -q -c host/pytest.ini host/test_status.py
"""
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import grpc
import pytest

from hearth import host as hh
from hearth import status_pb2 as pb
from hearth import status_pb2_grpc as rpc
from test_serve import Turns, home, session_alarm, state  # noqa: F401  (home is a fixture)


@pytest.fixture
def run_dir():
    # AF_UNIX paths are short (104 bytes on macOS), so not under pytest's tmp_path.
    d = Path(tempfile.mkdtemp(prefix="hst-"))
    d.chmod(0o700)
    yield d
    for f in d.iterdir():
        f.unlink()
    d.rmdir()


async def read(sock: Path) -> pb.Report:
    async with grpc.aio.insecure_channel(f"unix:{sock}") as ch:
        return await rpc.StatusStub(ch).Get(pb.GetRequest(), timeout=5)


async def serving(home, turns, until, *, sock, ledger, during=None, timeout=25.0, **host):
    """hh.serve with a status socket. ``during`` is awaited on every poll while it serves."""
    stop = asyncio.Event()
    made = []

    def factory(desk):
        h = hh.HearthHost(desk, turns, is_attended=lambda c: False, **host)
        made.append(h)
        return h

    task = asyncio.create_task(hh.serve(home, factory, sweep_s=0.3, poll_ms=500, stop=stop,
                                        status_path=sock, ledger=ledger))
    end = time.monotonic() + timeout
    try:
        while not until():
            assert time.monotonic() < end, "timed out"
            assert not task.done(), f"serve stopped: {task.exception() if not task.cancelled() else 'cancelled'}"
            if during is not None and sock.exists():
                await during()
            await asyncio.sleep(0.2)
    finally:
        stop.set()
        await asyncio.wait_for(task, 30)
    return made[0]


def ledger_row(ledger: Path, thread: str, rc: int) -> None:
    """One row as home/turn writes it: ids, times and outcome, never prompt or reply text."""
    t = time.time()
    with open(ledger, "a") as f:
        f.write(json.dumps({"v": 1, "trigger": "frontdesk", "resume": thread, "session_id": thread,
                            "ts_start_epoch": t - 1, "ts_end_epoch": t, "rc": rc,
                            "error": None if rc == 0 else f"turn error: rc {rc}"}) + "\n")


async def test_status_never_starts_a_turn_sends_or_changes_the_home(home, run_dir, tmp_path):
    """A failed turn waits out a long backoff. Reading the status again and again, meanwhile, runs
    nothing, takes nothing in, and leaves the turn ledger as it was."""
    sock, ledger = run_dir / "status.sock", tmp_path / "ledger.jsonl"
    receipt = await session_alarm(home, "sess-A", "ALARM-NOTE retry later", in_ms=300)

    calls = []

    def failing(conversation, prompt):
        calls.append((conversation, time.monotonic()))
        ledger_row(ledger, conversation, 1)
        return 1

    reports = []

    async def look():
        reports.append(await read(sock))

    await serving(home, failing, lambda: calls and time.monotonic() - calls[0][1] > 4,
                  sock=sock, ledger=ledger, during=look, retry_s=600)
    calls = [c for c, _ in calls]
    assert calls == ["sess-A"], "reading the status ran a turn"
    assert state(home, receipt) == "arrived"
    assert len(ledger.read_text().splitlines()) == 1
    last = reports[-1]
    (wake,) = last.pending_wakes
    assert (wake.thread, wake.waiting, wake.failures) == ("sess-A", 1, 1)
    assert wake.retry_at > time.time() + 500
    (turn,) = last.recent_turns
    assert (turn.thread, turn.ok) == ("sess-A", False)


async def test_status_never_shows_what_was_said_in_a_thread(home, run_dir, tmp_path):
    """Read while the turn runs and after it: the message's words appear in no report."""
    sock, ledger = run_dir / "status.sock", tmp_path / "ledger.jsonl"
    words = "PLUM-HERON-7731 the vault code"
    receipt = await session_alarm(home, "sess-A", words, in_ms=2500)
    reports = []

    async def look():
        reports.append(await read(sock))

    def runner(c, p):
        time.sleep(1.5)
        ledger_row(ledger, c, 0)
        return 0

    await serving(home, runner, lambda: state(home, receipt) == "taken_in", sock=sock, ledger=ledger, during=look)
    reports.append(await read_after(home, sock, ledger))
    assert any(r.live_turns for r in reports), "never read mid-turn"
    assert any(w.waiting for r in reports for w in r.pending_wakes), "never read while it waited"
    for r in reports:
        assert b"PLUM-HERON" not in r.SerializeToString()


async def read_after(home, sock, ledger):
    """The status once the turn is over, from a fresh host on the same home."""
    out = []

    async def look():
        out.append(await read(sock))

    await serving(home, lambda c, p: 0, lambda: bool(out), sock=sock, ledger=ledger, during=look)
    return out[-1]


async def test_no_other_agent_can_read_its_status_and_the_agent_runs_the_same_without_it(home, tmp_path):
    """A status directory every user can enter is refused, and the alarm still runs its turn."""
    open_dir = Path(tempfile.mkdtemp(prefix="hso-"))
    try:
        open_dir.chmod(0o755)
        receipt = await session_alarm(home, "sess-A", "ALARM-NOTE run anyway")
        turns, sock, appeared = Turns(), open_dir / "status.sock", []
        await serving(home, turns,
                      lambda: appeared.append(sock.exists()) or (turns.calls and state(home, receipt) == "taken_in"),
                      sock=sock, ledger=tmp_path / "ledger.jsonl")
        assert not any(appeared), "status was served from a directory every user can enter"
    finally:
        os.rmdir(open_dir)


async def test_a_report_names_what_it_cannot_give(home, run_dir, tmp_path):
    """So an empty list it wasn't given is never read as "none"."""
    sock = run_dir / "status.sock"
    seen = []

    async def look():
        seen.append(await read(sock))

    await serving(home, Turns(), lambda: bool(seen), sock=sock, ledger=tmp_path / "ledger.jsonl", during=look)
    assert seen[0].agent
    assert {n.report for n in seen[0].not_reported} >= {"faculties", "last sweep"}
