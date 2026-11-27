"""Every session of an agent starts by showing it its own pending wakes (docs/interfaces/PLUGIN.md)."""
import json
import subprocess
import uuid

import pytest

from conftest import hearth_cli, push, register, wait_until


@pytest.fixture
def person():
    p = subprocess.Popen(["sleep", "120"])
    yield p
    p.kill()
    p.wait()


def opening_context(home, session: str, pid: int, agent: str = "ash") -> str:
    done = hearth_cli(home, "hook", "session-start", stdin=json.dumps({"session_id": session}),
                      env={"HEARTH_AGENT": agent, "CLAUDE_PID": str(pid)})
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]


async def test_every_session_starts_by_showing_the_agent_its_pending_wakes_in_all_its_conversations(
        home, fake, root, start_gateway, person):
    register(home, "ash", root)
    register(home, "wren", root)
    await start_gateway()
    await push(home, "ash", "deploy", delay=3600, note="check the deploy at 20:30")
    await push(home, "ash", "chat", delay=7200, note="ask Will about the cluster")
    await push(home, "wren", "house", delay=3600, note="wren's own business")

    shown = opening_context(home, str(uuid.uuid4()), person.pid)
    assert "check the deploy at 20:30" in shown and "in deploy" in shown
    assert "ask Will about the cluster" in shown and "in chat" in shown
    assert "wren's own business" not in shown, "another agent's wakes were shown"

    await push(home, "ash", "now", note="go")
    await wait_until(lambda: len(fake.ends) == 1, what="a turn")
    [turn_context] = [c for c in fake.starts[0]["contexts"] if "pending wakes" in c]
    assert "check the deploy at 20:30" in turn_context, "a gateway turn's session was not shown the pending wakes"


async def test_a_session_with_nothing_pending_is_told_so(home, fake, root, start_gateway, person):
    register(home, "ash", root)
    await start_gateway()
    assert "You have no pending wakes." in opening_context(home, str(uuid.uuid4()), person.pid)


def test_pending_wakes_that_cannot_be_read_are_reported_never_shown_as_none(home, person):
    home.ensure()
    home.db.write_text("this is not a database")
    shown = opening_context(home, str(uuid.uuid4()), person.pid)
    assert "could not be read" in shown and "does not mean you have none" in shown
    assert "You have no pending wakes" not in shown


async def test_the_list_says_how_many_wakes_it_left_out(home, fake, root, start_gateway, person):
    register(home, "ash", root)
    await start_gateway()
    for i in range(12):
        await push(home, "ash", f"c{i}", delay=3600, note=f"note {i} " + "x" * 1500)
    shown = opening_context(home, str(uuid.uuid4()), person.pid)
    assert "more, not shown here" in shown
    shown_count = shown.count("- wake ")
    assert 0 < shown_count < 12 and f"and {12 - shown_count} more" in shown
