"""hearth#51 against a real throwaway desk (:8018, never :8008). The turn is a fake runner, so
these pin the host; the run through real Claude Code is a separate, recorded arm.

Run: FRONTDESK_TEST_DESK=http://127.0.0.1:8018 python -m pytest -q host/test_hearth_host.py
(needs frontdesk importable, e.g. pip install -e <frontdesk>[dev]).
"""
import asyncio
import os
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from hearth_host import HearthHost  # noqa: E402

from frontdesk import Desk  # noqa: E402

DESK = os.environ.get("FRONTDESK_TEST_DESK", "http://127.0.0.1:8018")


@pytest.fixture(autouse=True, scope="session")
def _desk_up():
    assert not DESK.endswith(":8008"), "never the real desk"
    try:
        up = httpx.get(f"{DESK}/_matrix/client/versions", timeout=3).status_code == 200
    except httpx.HTTPError:
        up = False
    if not up:   # an absent desk is a failure, never a skip: a skip exits 0
        pytest.fail(f"no desk at {DESK}")


class FakeTurn:
    """Records each turn; can fail, or block until released, to expose overlap."""

    def __init__(self, rc: int = 0, hold: float = 0.0):
        self.rc, self.hold = rc, hold
        self.calls: list[tuple[str, str]] = []
        self.live = 0
        self.max_live = 0
        self._mu = threading.Lock()

    def __call__(self, conversation: str, prompt: str) -> int:
        with self._mu:
            self.live += 1
            self.max_live = max(self.max_live, self.live)
            self.calls.append((conversation, prompt))
        time.sleep(self.hold)
        with self._mu:
            self.live -= 1
        return self.rc


@pytest.fixture
async def agent(tmp_path):
    ns = f"h51-{uuid.uuid4().hex[:8]}"
    keeper = await Desk.join(DESK, "keeper", tmp_path / "keeper", kind="person", namespace=ns)
    me = await Desk.join(DESK, "ember", tmp_path / "me", kind="agent", namespace=ns, answerable=keeper.me)
    yield me
    await me.close()
    await keeper.close()


async def pump_until(desk, cond, timeout=20.0):
    end = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > end:
            raise AssertionError("timed out")
        await desk.pump(timeout_ms=500)


async def alarm(me, conversation, text, in_ms=1500):
    handle = await me.list_channel(conversation, "set the alarm")
    return await me.send("ember", text, channel=handle, arrive="wake",
                         hold_until=int(time.time() * 1000) + in_ms)


async def test_a_due_alarm_runs_a_turn_in_its_closed_conversation_and_is_taken_in(agent):
    turn = FakeTurn()
    agent.host = HearthHost(agent, turn)
    receipt = await alarm(agent, "session-A", "ALARM-NOTE check the deploy")
    await pump_until(agent, lambda: turn.calls)
    await agent.host.drain()
    (conversation, prompt), = turn.calls
    assert conversation == "session-A"
    assert "ALARM-NOTE check the deploy" in prompt
    assert 'from="ember"' in prompt and f'from_id="{agent.me}"' in prompt   # marked as its own
    assert (await agent.trace(receipt.id)).state == "taken_in"


async def test_a_failed_turn_leaves_the_alarm_pending_and_the_next_wake_shows_it_again(agent):
    turn = FakeTurn(rc=1)
    agent.host = HearthHost(agent, turn)
    receipt = await alarm(agent, "session-A", "ALARM-NOTE retry me")
    await pump_until(agent, lambda: turn.calls)
    await agent.host.drain()
    assert (await agent.trace(receipt.id)).state == "arrived"
    turn.rc = 0
    await agent.host.wake("session-A")
    await agent.host.drain()
    assert len(turn.calls) == 2 and "ALARM-NOTE retry me" in turn.calls[1][1]
    assert (await agent.trace(receipt.id)).state == "taken_in"


async def test_turns_in_one_conversation_never_overlap(agent):
    turn = FakeTurn(hold=1.5)
    agent.host = HearthHost(agent, turn)
    first = await alarm(agent, "session-A", "ONE", in_ms=500)
    await pump_until(agent, lambda: turn.calls)
    second = await alarm(agent, "session-A", "TWO", in_ms=200)   # arrives while ONE's turn runs
    await pump_until(agent, lambda: len(turn.calls) >= 2, timeout=30)
    await agent.host.drain()
    assert turn.max_live == 1
    assert [("ONE" in p, "TWO" in p) for _, p in turn.calls] == [(True, False), (False, True)]
    for r in (first, second):
        assert (await agent.trace(r.id)).state == "taken_in"


async def test_two_conversations_run_side_by_side(agent):
    turn = FakeTurn(hold=1.5)
    agent.host = HearthHost(agent, turn)
    await alarm(agent, "session-A", "FOR-A", in_ms=500)
    await alarm(agent, "session-B", "FOR-B", in_ms=500)
    await pump_until(agent, lambda: len(turn.calls) >= 2)
    await agent.host.drain()
    assert turn.max_live == 2


async def test_wake_never_blocks_the_desk_while_a_turn_runs(agent):
    turn = FakeTurn(hold=3.0)
    agent.host = HearthHost(agent, turn)
    await alarm(agent, "session-A", "SLOW", in_ms=300)
    await pump_until(agent, lambda: turn.calls)
    t0 = time.monotonic()
    await agent.host.wake("session-A")
    assert time.monotonic() - t0 < 0.5
    await agent.host.drain()


async def test_control_with_no_waking_message_no_turn_runs(agent):
    turn = FakeTurn()
    agent.host = HearthHost(agent, turn)
    handle = await agent.list_channel("session-A", "quiet")
    await agent.send("ember", "just a note", channel=handle, arrive="wait")
    end = time.monotonic() + 4
    while time.monotonic() < end:
        await agent.pump(timeout_ms=500)
    await agent.host.drain()
    assert turn.calls == []
