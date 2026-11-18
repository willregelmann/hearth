"""Hearth never resumes a conversation a person has open (docs/primitives/CONVERSATION.md), and learns
what is open from its plugin's hooks (docs/interfaces/PLUGIN.md)."""
import json
import subprocess
import uuid

import pytest

from conftest import agent_status, hearth_cli, push, quiet, register, status, wait_until, wakes
from hearth import conversation


@pytest.fixture
def person():
    """A process standing in for the interactive Claude Code session a person has open."""
    p = subprocess.Popen(["sleep", "120"])
    yield p
    p.kill()
    p.wait()


def session_hook(home, event: str, session_id: str, pid: int, agent: str = None):
    env = {"CLAUDE_PID": str(pid)}
    if agent:
        env["HEARTH_AGENT"] = agent
    return hearth_cli(home, "hook", event, stdin=json.dumps({"session_id": session_id}), env=env)


async def test_a_conversation_open_in_a_live_session_is_deferred_and_run_once_the_session_ends(
        home, fake, root, start_gateway, person):
    register(home, "ash", root)
    await start_gateway()
    session = str(uuid.uuid4())
    fake.know_session(session)
    assert session_hook(home, "session-start", session, person.pid).returncode == 0

    await push(home, "ash", session, note="while you were typing")
    await quiet(0.6)
    assert fake.starts == [], "a turn was started in a conversation a person has open"
    report = agent_status(await status(home), "ash")
    assert [s["session"] for s in report["open_sessions"]] == [session]
    [pending] = report["wakes"]
    assert pending["deferred"] and pending["state"] == "pending"

    assert session_hook(home, "session-end", session, person.pid).returncode == 0
    await wait_until(lambda: len(fake.ends) == 1, what="the deferred wake to run")
    assert fake.starts[0]["resume"] == session
    assert "while you were typing" in fake.starts[0]["prompt"]


async def test_a_session_that_died_without_ending_stops_counting_as_open(home, fake, root, start_gateway, person):
    register(home, "ash", root)
    await start_gateway()
    session = str(uuid.uuid4())
    fake.know_session(session)
    session_hook(home, "session-start", session, person.pid)
    await push(home, "ash", session)
    await quiet(0.4)
    assert fake.starts == []

    person.kill()
    person.wait()
    await wait_until(lambda: len(fake.ends) == 1, what="the wake to run once the session's process was gone")
    assert list(home.sessions.glob("*.json")) == []


async def test_a_record_whose_process_id_now_belongs_to_another_process_is_not_an_open_session(
        home, fake, root, start_gateway, person):
    register(home, "ash", root)
    await start_gateway()
    session = str(uuid.uuid4())
    fake.know_session(session)
    conversation.record_open(home.sessions, session, person.pid, "Mon Jan  1 00:00:00 2001", None)

    await push(home, "ash", session)
    await wait_until(lambda: len(fake.ends) == 1, what="the wake to run, the recorded process being someone else")


async def test_where_the_start_of_a_live_process_cannot_be_checked_the_conversation_counts_as_open(
        home, fake, root, start_gateway, person):
    register(home, "ash", root)
    await start_gateway()
    session = str(uuid.uuid4())
    fake.know_session(session)
    conversation.record_open(home.sessions, session, person.pid, None, None)

    await push(home, "ash", session)
    await quiet(0.5)
    assert fake.starts == []
    assert [w["deferred"] for w in await wakes(home)] == [True]


async def test_a_name_whose_session_is_open_is_deferred_too(home, fake, root, start_gateway, person):
    register(home, "ash", root)
    await start_gateway()
    await push(home, "ash", "talk")
    await wait_until(lambda: len(fake.ends) == 1)
    session = fake.starts[0]["session"]

    session_hook(home, "session-start", session, person.pid)
    await push(home, "ash", "talk")
    await quiet(0.5)
    assert len(fake.starts) == 1
    session_hook(home, "session-end", session, person.pid)
    await wait_until(lambda: len(fake.ends) == 2)


def test_the_session_start_hook_tells_an_agent_how_to_wait_and_records_the_session(home, person):
    session = str(uuid.uuid4())
    done = session_hook(home, "session-start", session, person.pid, agent="ash")
    assert done.returncode == 0
    context = json.loads(done.stdout)["hookSpecificOutput"]
    assert context["hookEventName"] == "SessionStart"
    text = context["additionalContext"]
    assert "'ash'" in text and session in text
    assert "never hold a turn open" in text and "wake --source self --conversation " + session in text
    assert [s.session_id for s in conversation.open_sessions(home.sessions)] == [session]


def test_the_hooks_never_fail_a_session_even_when_given_nonsense(home):
    for event in ("session-start", "session-end"):
        done = hearth_cli(home, "hook", event, stdin="this is not json")
        assert done.returncode == 0 and done.stdout == ""
    assert list(home.sessions.glob("*.json")) == []
