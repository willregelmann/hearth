"""A wake pushed to the gateway becomes a turn in the right conversation (docs/primitives/WAKE.md,
docs/primitives/CONVERSATION.md, docs/capabilities/DELIVER.md)."""
import json
import logging

from conftest import (SECRET_REPLY, agent_status, ask, push, quiet, register, status, wait_until, wakes)


async def all_done(home) -> bool:
    found = await wakes(home)
    return bool(found) and all(w["state"] == "done" for w in found)


async def test_a_pushed_wake_runs_one_turn_in_the_named_conversation_with_the_agents_config_and_plugins(
        home, fake, root, start_gateway, caplog):
    caplog.set_level(logging.DEBUG)
    plugin = root / "my-plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "my-plugin"}')
    agent = register(home, "ash", root, lines=['model = "haiku"', '[[plugin]]', f'dir = "{plugin}"', '[env]',
                                               'FOO = "bar"'])
    await start_gateway()

    ack = await push(home, "ash", "build-watch", note="the build went red")
    assert ack["ok"] and not ack["duplicate"]
    await wait_until(lambda: all_done(home), what="the wake to be done")

    (start,) = fake.starts
    assert start["resume"] is None
    assert start["cwd"] == str(agent.workdir.resolve())
    assert start["config_dir"] == str(agent.config_dir)
    assert start["model"] == "haiku"
    assert start["foo"] == "bar"
    assert start["agent"] == "ash" and start["turn"] == "1"
    assert str(plugin) in start["plugin_dirs"]
    assert any(d.endswith("hearth/plugin") for d in start["plugin_dirs"])
    assert "- test: the build went red" in start["prompt"]
    assert "not delivered to anyone" in start["prompt"]

    report = agent_status(await status(home), "ash")
    assert [t["outcome"] for t in report["recent_turns"]] == ["ok"]
    assert report["recent_turns"][0]["session_id"] == start["session"]

    # Reply text is on no surface Hearth keeps: not status, not the database, not its log.
    assert SECRET_REPLY not in json.dumps(report)
    assert SECRET_REPLY not in caplog.text
    for path in home.root.glob("hearth.db*"):
        assert SECRET_REPLY.encode() not in path.read_bytes()
        assert b"not delivered to anyone" not in path.read_bytes()


async def test_a_turn_the_gateway_runs_is_told_where_it_is_and_is_not_recorded_as_open(
        home, fake, root, start_gateway):
    register(home, "ash", root)
    await start_gateway()
    await push(home, "ash", "talk")
    await wait_until(lambda: all_done(home))

    (start,) = fake.starts
    (context,) = start["contexts"]
    assert "ash" in context and start["session"] in context
    assert "set a wake" in context and "never hold a turn open" in context
    assert list(home.sessions.glob("*.json")) == []


async def test_a_named_conversation_starts_fresh_once_then_resumes_the_recorded_session(
        home, fake, root, start_gateway):
    register(home, "ash", root)
    register(home, "bee", root)
    await start_gateway()

    await push(home, "ash", "build")
    await wait_until(lambda: len(fake.ends) == 1)
    await push(home, "ash", "build")
    await wait_until(lambda: len(fake.ends) == 2)
    first, second = fake.starts
    assert first["resume"] is None
    assert second["resume"] == first["session"]

    await push(home, "ash", first["session"])
    await wait_until(lambda: len(fake.ends) == 3)
    assert fake.starts[2]["resume"] == first["session"]

    await push(home, "bee", "build")
    await wait_until(lambda: len(fake.ends) == 4)
    other = fake.starts[3]
    assert other["resume"] is None and other["session"] != first["session"]
    assert "first turn of the conversation named 'build'" in first["prompt"]
    assert "first turn" not in second["prompt"]


async def test_the_same_key_pushed_twice_produces_one_turn(home, fake, root, start_gateway):
    register(home, "ash", root)
    await start_gateway()

    first = await push(home, "ash", "talk", key="mail-17")
    again = await push(home, "ash", "talk", key="mail-17")
    assert not first["duplicate"] and again["duplicate"] and again["id"] == first["id"]
    await wait_until(lambda: all_done(home))

    long_after = await push(home, "ash", "talk", key="mail-17")
    assert long_after["duplicate"] and long_after["state"] == "done"
    await quiet()
    assert len(fake.starts) == 1


async def test_two_wakes_for_one_conversation_never_run_two_turns_at_once_but_other_conversations_do(
        home, fake, root, start_gateway):
    register(home, "ash", root)
    await start_gateway()
    fake.hold()

    await push(home, "ash", "a", note="first")
    await wait_until(lambda: len(fake.starts) == 1)
    await push(home, "ash", "a", note="second, while the first runs")
    await push(home, "ash", "b")
    await wait_until(lambda: len(fake.starts) == 2, what="another conversation to run beside it")
    await quiet()
    assert len(fake.starts) == 2, "a second turn started in a conversation that already had one"

    fake.release()
    await wait_until(lambda: len(fake.ends) == 3)
    a_first, b_first, a_second = fake.starts
    assert b_first["session"] != a_first["session"]
    assert a_second["resume"] == a_first["session"]
    a_first_end = next(e for e in fake.ends if e["pid"] == a_first["pid"])
    assert a_second["t"] >= a_first_end["t"]
    assert "second, while the first runs" in a_second["prompt"]
    assert "second, while the first runs" not in a_first["prompt"]


async def test_every_due_wake_for_a_conversation_is_shown_to_one_turn(home, fake, root, start_gateway, clock):
    register(home, "ash", root)
    await start_gateway()
    await push(home, "ash", "talk", note="one", delay=10)
    await push(home, "ash", "talk", note="two", delay=10)
    await push(home, "ash", "talk", note="three", delay=500)

    clock.advance(11)
    await wait_until(lambda: len(fake.ends) == 1)
    await quiet()
    (turn,) = fake.starts
    assert "one" in turn["prompt"] and "two" in turn["prompt"] and "three" not in turn["prompt"]
    assert "2 wakes" in turn["prompt"]


async def test_a_failed_turn_leaves_its_wakes_pending_and_is_retried_after_a_doubling_backoff(
        home, fake, root, start_gateway, clock):
    register(home, "ash", root)
    await start_gateway()
    fake.mode(fail="exit")

    await push(home, "ash", "talk", note="please")
    await wait_until(lambda: len(fake.ends) == 1)
    (pending,) = await wait_until(lambda: _failed(home), what="the failure to be recorded")
    assert pending["state"] == "pending" and pending["failures"] == 1
    assert "exit 1" in pending["last_failure"]
    assert pending["next_try"] == clock.now + 30

    clock.advance(29)
    await quiet()
    assert len(fake.starts) == 1, "retried before the backoff had passed"
    clock.advance(2)
    await wait_until(lambda: len(fake.ends) == 2)
    (pending,) = await wait_until(lambda: _failed(home, failures=2))
    assert pending["next_try"] == clock.now + 60, "the backoff did not double"
    assert "may have been shown to an earlier turn" in fake.starts[1]["prompt"]

    clock.advance(59)
    await quiet()
    assert len(fake.starts) == 2
    fake.mode()
    clock.advance(2)
    await wait_until(lambda: all_done(home))
    assert len(fake.starts) == 3
    assert agent_status(await status(home), "ash")["wakes"] == []


async def _failed(home, failures=1):
    found = [w for w in await wakes(home) if w["failures"] == failures]
    return found or None


async def test_a_turn_that_does_not_print_a_result_is_a_failed_turn(home, fake, root, start_gateway):
    register(home, "ash", root)
    await start_gateway()
    fake.mode(fail="garbage")

    await push(home, "ash", "talk")
    (pending,) = await wait_until(lambda: _failed(home))
    assert "not a result" in pending["last_failure"]


async def test_a_wake_with_a_not_before_time_never_runs_early_and_says_how_late_it_ran(
        home, fake, root, start_gateway, clock):
    register(home, "ash", root)
    await start_gateway()
    await push(home, "ash", "talk", note="tomorrow", delay=3600)

    clock.advance(3599)
    await quiet()
    assert fake.starts == []
    clock.advance(1 + 180)
    await wait_until(lambda: len(fake.ends) == 1)
    prompt = fake.starts[0]["prompt"]
    assert "was due at" in prompt and "3m late" in prompt


async def test_an_operator_can_list_and_cancel_a_pending_wake_but_not_a_running_one(
        home, fake, root, start_gateway, clock):
    register(home, "ash", root)
    await start_gateway()
    later = await push(home, "ash", "talk", delay=3600)
    [listed] = (await ask(home, op="wake.list"))["wakes"]
    assert listed["id"] == later["id"] and listed["state"] == "pending"

    cancelled = await ask(home, op="wake.cancel", id=later["id"])
    assert cancelled["ok"]
    assert [w["state"] for w in await wakes(home)] == ["canceled"]
    clock.advance(7200)
    await quiet()
    assert fake.starts == []

    fake.hold()
    running = await push(home, "ash", "talk")
    await wait_until(lambda: len(fake.starts) == 1)
    refusal = await ask(home, op="wake.cancel", id=running["id"])
    assert not refusal["ok"] and "running" in refusal["error"]
    unknown = await ask(home, op="wake.cancel", id=9999)
    assert not unknown["ok"] and "no wake" in unknown["error"]
    fake.release()
    await wait_until(lambda: len(fake.ends) == 1)


async def test_a_turn_that_outlives_its_timeout_is_killed_with_everything_it_started(
        home, fake, root, start_gateway):
    register(home, "ash", root, lines=["turn_timeout = 1"])
    await start_gateway()
    fake.mode(child=True, sleep=30)

    await push(home, "ash", "talk")
    await wait_until(lambda: (fake.dir / "child.pid").exists())
    child = int((fake.dir / "child.pid").read_text())
    report = await wait_until(
        lambda: _turn_outcome(home, "timeout"), timeout=20, what="the turn to be recorded as timed out")
    assert "killed after" in report["detail"]
    assert not _alive(fake.starts[0]["pid"]) and not _alive(child)
    [pending] = [w for w in await wakes(home)]
    assert pending["state"] == "pending"


async def _turn_outcome(home, outcome):
    turns = agent_status(await status(home), "ash")["recent_turns"]
    return next((t for t in turns if t["outcome"] == outcome), None)


def _alive(pid: int) -> bool:
    import os
    import time
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        time.sleep(0.02)
    return True
