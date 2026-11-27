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


# Sessions Hearth didn't start, and processes that have exited (docs/primitives/CONVERSATION.md) -------

async def test_a_session_started_without_hearth_in_the_agents_configuration_directory_defers_a_wake(
        home, fake, root, start_gateway):
    import os
    agent = register(home, "ash", root)
    installed = hearth_cli(home, "agent", "install", "ash", env={"HEARTH_CLAUDE": str(fake.path)})
    assert installed.returncode == 0, installed.stdout + installed.stderr
    await start_gateway()
    session = str(uuid.uuid4())
    fake.know_session(session)

    fake.hold()
    plain = subprocess.Popen([str(fake.path), "--resume", session, "typing by hand"],
                             env={k: v for k, v in dict(os.environ, CLAUDE_CONFIG_DIR=str(agent.config_dir)).items()
                                  if not k.startswith("HEARTH_")},
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        await wait_until(lambda: list(home.sessions.glob(f"{session}.*.json")),
                         what="the plain session to be recorded by the configuration directory's hook")
        assert fake.starts[0]["contexts"] == [], "the record-only hook told the session something"
        await push(home, "ash", session, note="while it was open by hand")
        await quiet(0.6)
        assert [s for s in fake.starts if s["turn"]] == [], "a turn resumed a session someone had open"
    finally:
        fake.release()
        plain.wait(timeout=30)
    await wait_until(lambda: [s for s in fake.starts if s["turn"]], what="the wake to run once the session ended")


def test_a_process_that_has_exited_but_not_been_reaped_is_not_an_open_session(root):
    import time
    from hearth import proc
    sessions = root / "sessions"
    zombie = subprocess.Popen(["sleep", "0.2"])
    session = str(uuid.uuid4())
    conversation.record_open(sessions, session, zombie.pid, proc.start_time(zombie.pid), "ash")
    assert conversation.is_open(sessions, session)
    time.sleep(0.6)                     # exited, and not waited for: a zombie
    try:
        assert not conversation.is_open(sessions, session), "a zombie counted as an open session"
    finally:
        zombie.wait()


async def test_a_session_that_opens_while_a_turn_is_being_prepared_defers_the_turn(
        home, fake, root, start_gateway, person, monkeypatch):
    from hearth import agent as agents
    register(home, "ash", root)
    await start_gateway()
    session = str(uuid.uuid4())
    fake.know_session(session)
    real = agents.installed_plugins

    def opens_meanwhile(*args, **kwargs):
        conversation.record_open(home.sessions, session, person.pid, None, "ash")
        return real(*args, **kwargs)

    monkeypatch.setattr(agents, "installed_plugins", opens_meanwhile)
    await push(home, "ash", session)
    await quiet(0.6)
    assert fake.starts == [], "a turn resumed a session that opened while it was being prepared"
    [pending] = await wakes(home)
    assert pending["state"] == "pending" and not pending["failures"], "a deferral counted as a failure"
    monkeypatch.setattr(agents, "installed_plugins", real)
    conversation.clear_open(home.sessions, session)
    await wait_until(lambda: len(fake.ends) == 1, what="the wake to run once the session closed")
