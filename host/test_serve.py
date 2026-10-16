"""hearth#51, the service: serve() against a real throwaway desk (:8018, never :8008). Conversations
are listed the way a Claude Code session lists them, from a seat named by its session id, never
from the host's own desk. The turn is a fake runner.

Run: FRONTDESK_TEST_DESK=http://127.0.0.1:8018 python -m pytest -q host/
"""
import asyncio
import json
import os
import pwd
import subprocess
import sys
import time
import uuid

import pytest

from frontdesk import Desk
from frontdesk.hosts.claude_code import sessions
from hearth import host as hh

DESK = os.environ.get("FRONTDESK_TEST_DESK", "http://127.0.0.1:8018")


class Turns:
    def __init__(self, rc=0, hold=0.0, during=None):
        self.rc, self.hold, self.during = rc, hold, during
        self.calls: list[tuple[str, str]] = []

    def __call__(self, conversation, prompt):
        self.calls.append((conversation, prompt))
        if self.during:
            self.during(conversation)
        time.sleep(self.hold)
        return self.rc


@pytest.fixture
async def home(tmp_path):
    ns = f"h51s-{uuid.uuid4().hex[:8]}"
    keeper = await Desk.join(DESK, "keeper", tmp_path / "keeper", kind="person", namespace=ns)
    me = await Desk.join(DESK, "ember", tmp_path / "me", kind="agent", namespace=ns, answerable=keeper.me)
    await me.close()
    yield tmp_path / "me"
    await keeper.close()


async def session_alarm(home, session, text, in_ms=1500):
    """What a session's own server does for a self-alarm: list on its seat, send, exit."""
    desk = Desk(home, seat=session)
    try:
        handle = await desk.list_channel(session, "set the alarm")
        return await desk.send("ember", text, channel=handle, arrive="wake",
                               hold_until=int(time.time() * 1000) + in_ms)
    finally:
        await desk.close()


async def serving(home, turns, until, *, attended=lambda c: False, timeout=25.0):
    stop = asyncio.Event()
    made = []

    def factory(desk):
        h = hh.HearthHost(desk, turns, is_attended=lambda c: attended(c))
        made.append(h)
        return h

    task = asyncio.create_task(hh.serve(home, factory, sweep_s=0.3, poll_ms=500, stop=stop))
    end = time.monotonic() + timeout
    try:
        while not until():
            assert time.monotonic() < end, "timed out"
            assert not task.done(), f"serve stopped: {task.exception() if not task.cancelled() else 'cancelled'}"
            await asyncio.sleep(0.2)
    finally:
        stop.set()
        await asyncio.wait_for(task, 30)
    return made[0]


def state(home, receipt):
    d = Desk(home, seat="probe")
    try:
        for row in d.ledger._all("SELECT state, arrival FROM inbox"):
            if json.loads(row["arrival"] or "{}").get("id") == receipt.id:
                return row["state"]
    finally:
        d.ledger.close()
    return None


async def test_a_session_s_alarm_runs_a_turn_in_that_session(home):
    receipt = await session_alarm(home, "sess-A", "ALARM-NOTE check the deploy")
    turns = Turns()
    await serving(home, turns, lambda: turns.calls and state(home, receipt) == "taken_in")
    (conversation, prompt), = turns.calls
    assert conversation == "sess-A" and "ALARM-NOTE check the deploy" in prompt


async def test_alarms_in_two_sessions_each_run_in_their_own(home):
    a = await session_alarm(home, "sess-A", "FOR-A")
    b = await session_alarm(home, "sess-B", "FOR-B")
    turns = Turns()
    await serving(home, turns, lambda: len(turns.calls) >= 2 and state(home, a) == state(home, b) == "taken_in")
    assert sorted((c, "FOR-A" in p, "FOR-B" in p) for c, p in turns.calls) == \
        [("sess-A", True, False), ("sess-B", False, True)]


async def test_a_session_open_elsewhere_is_never_resumed_and_runs_once_it_closes(home):
    receipt = await session_alarm(home, "sess-A", "ALARM-NOTE wait for me", in_ms=500)
    open_ = {"sess-A"}
    turns = Turns()
    t0 = time.monotonic()
    # Open: the seat isn't served and nothing runs, for long enough that a served seat would have run.
    await serving(home, turns, lambda: time.monotonic() - t0 > 6, attended=lambda c: c in open_)
    # not even claimed: the open session's own server must be the one to take it and push it in
    assert turns.calls == [] and state(home, receipt) is None
    open_.clear()
    await serving(home, turns, lambda: turns.calls and state(home, receipt) == "taken_in")
    assert "ALARM-NOTE wait for me" in turns.calls[0][1]


async def test_a_session_that_opens_mid_wake_defers_and_runs_when_it_closes(home):
    receipt = await session_alarm(home, "sess-A", "ALARM-NOTE deferred", in_ms=1200)
    open_ = set()
    turns = Turns()
    t0 = time.monotonic()

    def attended(c):
        # the seat is served from the start; the session opens just before the alarm is due
        if time.monotonic() - t0 > 0.8 and time.monotonic() - t0 < 6:
            return c in {"sess-A"}
        return False

    await serving(home, turns, lambda: turns.calls and state(home, receipt) == "taken_in",
                  attended=attended)
    assert time.monotonic() - t0 >= 6   # not before the session closed


async def test_the_resumed_turn_s_own_server_does_not_wake_it_again(home):
    """While the host's turn runs, the turn's own Front Desk server (same session id, so same
    seat) starts and recovers. It must not find the alarm waiting and wake for it a second time."""
    receipt = await session_alarm(home, "sess-A", "ALARM-NOTE once", in_ms=800)
    woken = []

    class Rec:
        async def wake(self, c):
            woken.append(c)

        async def start(self, a):
            return None

    def server_starts(conversation):
        async def recover():
            d = Desk(home, seat=conversation)
            d.host = Rec()
            await d._recover()
            await d.close()
        asyncio.run(recover())

    turns = Turns(during=server_starts)
    await serving(home, turns, lambda: turns.calls and state(home, receipt) == "taken_in")
    assert woken == [] and len(turns.calls) == 1


async def test_what_the_turn_s_own_server_takes_mid_turn_runs_in_a_next_turn(home):
    """A message that arrives during a turn can be claimed by the turn's own server (same seat).
    Whether its channel push reaches a -p turn isn't relied on: the host runs another turn."""
    first = await session_alarm(home, "sess-A", "FIRST", in_ms=500)
    later = []

    class Rec:
        async def wake(self, c):
            pass

        async def start(self, a):
            return None

    def own_server_takes_one(conversation):
        if later:
            return

        async def go():
            d = Desk(home, seat=conversation)
            d.host = Rec()
            later.append(await d.send("ember", "SECOND", channel=d.ledger.channel_of(conversation)["handle"],
                                      arrive="wake"))
            end = time.monotonic() + 15
            while state(home, later[0]) != "arrived":
                assert time.monotonic() < end
                await d.pump(timeout_ms=500)
            await d.close()
        asyncio.run(go())

    turns = Turns(during=own_server_takes_one)
    await serving(home, turns, lambda: len(turns.calls) >= 2 and state(home, later[0]) == "taken_in")
    assert "FIRST" in turns.calls[0][1] and "SECOND" in turns.calls[1][1]
    assert state(home, first) == "taken_in"


async def test_a_failed_turn_puts_the_alarm_back_and_a_later_wake_runs_it(home):
    receipt = await session_alarm(home, "sess-A", "ALARM-NOTE retry", in_ms=500)
    turns = Turns(rc=1)
    await serving(home, turns, lambda: turns.calls)
    await asyncio.sleep(0.5)
    assert state(home, receipt) == "arrived"
    turns.rc = 0
    # a restart: the seat's recovery wakes what is still arrived
    await serving(home, turns, lambda: len(turns.calls) >= 2 and state(home, receipt) == "taken_in")
    assert "ALARM-NOTE retry" in turns.calls[-1][1]


# Host level, where the test controls who pumps: the cases a sweep or a lucky claim can hide.


async def _pump_until(desk, cond, timeout=20.0):
    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out"
        await desk.pump(timeout_ms=500)


async def test_host_a_wake_for_an_open_session_defers_and_retry_runs_it_once_closed(home):
    receipt = await session_alarm(home, "sess-A", "ALARM-NOTE open", in_ms=500)
    desk = Desk(home, seat="sess-A")
    open_ = {"sess-A"}
    turns = Turns()
    desk.host = hh.HearthHost(desk, turns, is_attended=lambda c: c in open_)
    try:
        await _pump_until(desk, lambda: state(home, receipt) == "arrived")
        await desk.host.drain()
        assert turns.calls == [] and desk.host.deferred == {"sess-A"}
        await desk.host.retry_deferred()   # still open: still nothing
        await desk.host.drain()
        assert turns.calls == []
        open_.clear()
        await desk.host.retry_deferred()
        await desk.host.drain()
        assert len(turns.calls) == 1 and state(home, receipt) == "taken_in"
    finally:
        await desk.close()


async def test_host_what_the_turn_s_own_server_claims_runs_in_a_next_turn(home):
    """During the turn only the turn's own server (same seat) pumps, so it is the one that claims
    the next message, and its push into a -p turn isn't relied on."""
    first = await session_alarm(home, "sess-A", "FIRST", in_ms=500)
    desk = Desk(home, seat="sess-A")
    later = []

    class Rec:
        async def wake(self, c):
            pass

        async def start(self, a):
            return None

    def own_server_claims_one(conversation):
        if later:
            return

        async def go():
            d = Desk(home, seat=conversation)
            d.host = Rec()
            later.append(await d.send("ember", "SECOND", channel=d.ledger.channel_of(conversation)["handle"],
                                      arrive="wake"))
            await _pump_until(d, lambda: state(home, later[0]) == "arrived")
            await d.close()
        asyncio.run(go())

    turns = Turns(during=own_server_claims_one)
    desk.host = hh.HearthHost(desk, turns, is_attended=lambda c: False)
    try:
        await _pump_until(desk, lambda: turns.calls)
        await desk.host.drain()   # nothing pumps the host's desk from here on
        assert [("FIRST" in p, "SECOND" in p) for _, p in turns.calls] == [(True, False), (False, True)]
        assert state(home, first) == state(home, later[0]) == "taken_in"
    finally:
        await desk.close()


# attended(): the record has to name a live claude process that isn't ours. A copy of this
# interpreter stands in for claude, in a scratch versions/ dir laid out like the tenant's.


def _record(home, pid, session, started=None):
    d = home / "claude-sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / str(pid)).write_text(json.dumps({"session": session,
                                          "started": sessions._started(pid) if started is None else started}))


@pytest.fixture
def versions(tmp_path):
    """A tenant's versions dir with two "claude" versions, as after an update. The stand-in is a
    copy of sleep, not of this interpreter: a copied uv-managed python finds no stdlib and dies at
    once (Ash, #108 S1), and a dead child would let every "not attended" test pass on nothing."""
    import shutil
    v = tmp_path / "versions"
    v.mkdir()
    for ver in ("2.1.288", "2.1.300"):
        shutil.copy2(SLEEP, v / ver)
    return v


SLEEP = os.path.realpath("/usr/bin/sleep")


def _alive(pid):
    """Running, not a zombie: what attended() is asked about must really be there."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def _detached(binary):
    """A live process running ``binary``, not a descendant of this one (double fork)."""
    out = subprocess.run([sys.executable, "-c",
                          "import subprocess, sys; p = subprocess.Popen([sys.argv[1], '60'], "
                          "start_new_session=True, stdout=subprocess.DEVNULL, "
                          "stderr=subprocess.DEVNULL); print(p.pid)", str(binary)],
                         capture_output=True, text=True, check=True)
    pid = int(out.stdout)
    assert _alive(pid), f"setup: the stand-in {binary} isn't running"
    return pid


@pytest.fixture
def procs():
    pids = []
    yield pids
    for pid in pids:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass


def test_attended_by_a_live_claude_of_the_current_version(tmp_path, versions, procs):
    procs.append(_detached(versions / "2.1.300"))
    _record(tmp_path, procs[-1], "sess-A")
    assert hh.attended(tmp_path, "sess-A", dirs=(str(versions),))
    assert not hh.attended(tmp_path, "sess-B", dirs=(str(versions),))


def test_attended_by_a_session_still_on_the_version_before_an_update(tmp_path, versions, procs):
    """Ash #91 R1 B: started on 2.1.288, ~/.local/bin/claude now points at 2.1.300."""
    procs.append(_detached(versions / "2.1.288"))
    _record(tmp_path, procs[-1], "sess-A")
    assert hh.attended(tmp_path, "sess-A", dirs=(str(versions),))


def test_attended_by_a_session_whose_binary_was_deleted_under_it(tmp_path, versions, procs):
    """Ash #91 R1 C: /proc/<pid>/exe reads "<path> (deleted)"."""
    procs.append(_detached(versions / "2.1.288"))
    _record(tmp_path, procs[-1], "sess-A")
    (versions / "2.1.288").unlink()
    assert os.readlink(f"/proc/{procs[-1]}/exe").endswith(" (deleted)")
    assert hh.attended(tmp_path, "sess-A", dirs=(str(versions),))


def test_not_attended_when_the_process_isn_t_claude(tmp_path, versions, procs):
    procs.append(_detached(SLEEP))   # a shell or tmux ancestor: also recorded by the hook
    _record(tmp_path, procs[-1], "sess-A")
    assert not hh.attended(tmp_path, "sess-A", dirs=(str(versions),))


def test_not_attended_by_a_binary_in_a_sibling_dir_with_the_same_prefix(tmp_path, versions, procs):
    import shutil
    sib = tmp_path / "versions-evil"
    sib.mkdir()
    shutil.copy2(versions / "2.1.300", sib / "x")
    procs.append(_detached(sib / "x"))
    _record(tmp_path, procs[-1], "sess-A")
    assert not hh.attended(tmp_path, "sess-A", dirs=(str(versions),))


def test_not_attended_when_the_pid_was_reused(tmp_path, versions, procs):
    procs.append(_detached(versions / "2.1.300"))
    _record(tmp_path, procs[-1], "sess-A", started="1")
    assert not hh.attended(tmp_path, "sess-A", dirs=(str(versions),))


def test_not_attended_by_this_host_s_own_turn(tmp_path, versions):
    child = subprocess.Popen([str(versions / "2.1.300"), "60"])
    try:
        assert _alive(child.pid), "setup: the stand-in isn't running"
        _record(tmp_path, child.pid, "sess-A")
        assert not hh.attended(tmp_path, "sess-A", dirs=(str(versions),))
    finally:
        child.kill()


def test_the_default_dirs_are_the_tenant_s_versions_and_root_s_store():
    home = pwd.getpwuid(os.getuid()).pw_dir
    assert hh.claude_dirs() == (os.path.realpath(f"{home}/.local/share/claude/versions"), "/opt/hearth/claude")
