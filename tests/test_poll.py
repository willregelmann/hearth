"""A check raises a wake when a key appears, once (docs/capabilities/POLL.md, docs/interfaces/CHECKS.md)."""
import json

from conftest import agent_status, quiet, register, status, wait_until, wakes

INTERVAL = 10


def feed(root, *entries):
    """What the check will print next."""
    lines = [e if isinstance(e, str) else json.dumps(e) for e in entries]
    (root / "ash-work" / "feed.txt").write_text("\n".join(lines) + ("\n" if lines else ""))


def entry(key, conversation="inbox", note=None):
    return {"conversation": conversation, "key": key, **({"note": note} if note else {})}


def register_polled(home, root, command="cat feed.txt"):
    return register(home, "ash", root, lines=["[[check]]", 'name = "mail"', f'command = "{command}"',
                                              f"interval = {INTERVAL}"])


async def last_run(home):
    check = agent_status(await status(home), "ash")["checks"][0]
    return check["last_run"]


async def ran_again(home, since):
    now = await last_run(home)
    return now is not None and now > since


async def next_run(home, clock):
    """Let the clock reach the next time the check is due, and wait for it to have run."""
    before = await last_run(home)
    clock.advance(INTERVAL + 1)
    await wait_until(lambda: ran_again(home, before), what="the check to run again")


async def all_done(home):
    found = await wakes(home)
    return bool(found) and all(w["state"] == "done" for w in found)


async def test_a_check_raises_a_wake_when_a_key_appears_and_not_again_while_it_stays(
        home, fake, root, start_gateway, clock):
    register_polled(home, root)
    feed(root, entry("mail-1", note="Ada wrote"))
    await start_gateway()

    await wait_until(lambda: all_done(home), what="the polled wake to be delivered")
    (start,) = fake.starts
    assert "- mail: Ada wrote" in start["prompt"]
    (woken,) = await wakes(home)
    assert woken["source"] == "mail" and woken["key"] == "mail-1"

    await next_run(home, clock)
    await next_run(home, clock)
    await quiet()
    assert len(fake.starts) == 1
    assert len(await wakes(home)) == 1


async def test_a_key_that_went_away_and_came_back_raises_again(home, fake, root, start_gateway, clock):
    register_polled(home, root)
    feed(root, entry("mail-1"))
    await start_gateway()
    await wait_until(lambda: all_done(home))

    feed(root)
    await next_run(home, clock)
    feed(root, entry("mail-1"))
    await next_run(home, clock)
    await wait_until(lambda: len(fake.ends) == 2, what="the key's second appearance to raise a wake")
    assert len(await wakes(home)) == 2


async def test_a_key_is_not_raised_again_across_a_restart(home, fake, root, start_gateway, clock):
    register_polled(home, root)
    feed(root, entry("mail-1"))
    first = await start_gateway()
    await wait_until(lambda: all_done(home))
    await first.stop(grace=0)
    clock.advance(1)

    await start_gateway()
    await wait_until(lambda: _ran_at(home, clock.now), what="the check to run after the restart")
    await next_run(home, clock)
    await quiet()
    assert len(fake.starts) == 1
    assert len(await wakes(home)) == 1


async def _ran_at(home, when):
    return await last_run(home) == when


async def test_a_key_that_leaves_and_returns_while_its_wake_is_still_owed_raises_nothing_more(
        home, fake, root, start_gateway, clock):
    register_polled(home, root)
    feed(root, entry("mail-1"))
    fake.hold()
    await start_gateway()
    await wait_until(lambda: len(fake.starts) == 1)

    feed(root)
    await next_run(home, clock)
    feed(root, entry("mail-1"))
    await next_run(home, clock)
    assert [w["state"] for w in await wakes(home)] == ["running"]
    fake.release()
    await wait_until(lambda: all_done(home))
    assert len(fake.starts) == 1


async def test_a_failing_check_raises_nothing_and_shows_in_status(home, fake, root, start_gateway, clock):
    register_polled(home, root, command="echo stale >&2; exit 3")
    await start_gateway()

    check = await wait_until(lambda: _failed_check(home), what="the failure to show in status")
    assert check["last_ok"] is False and "exited 3" in check["last_error"]
    assert await wakes(home) == []
    assert fake.starts == []


async def _failed_check(home):
    check = agent_status(await status(home), "ash")["checks"][0]
    return check if check["last_ok"] is False else None


async def test_a_check_that_prints_something_unparseable_fails_as_a_whole_and_keeps_what_it_knew(
        home, fake, root, start_gateway, clock):
    register_polled(home, root)
    feed(root, entry("mail-1"))
    await start_gateway()
    await wait_until(lambda: all_done(home))

    feed(root, entry("mail-2"), "this line is not JSON")
    before = await last_run(home)
    clock.advance(INTERVAL + 1)
    check = await wait_until(lambda: _failed_check(home))
    assert "line 2 is not JSON" in check["last_error"]
    await quiet()
    assert len(await wakes(home)) == 1, "part of a bad output was used"

    feed(root, entry("mail-1"), entry("mail-2"))
    await next_run(home, clock)
    await wait_until(lambda: len(fake.ends) == 2)
    sources = [(w["key"]) for w in await wakes(home)]
    assert sorted(sources) == ["mail-1", "mail-2"], "mail-1 was raised again after the failure"
    assert before is not None


async def test_a_check_that_does_not_finish_in_time_fails_and_is_killed(home, fake, root, start_gateway, clock):
    register(home, "ash", root, lines=["[[check]]", 'name = "slow"', 'command = "sleep 30"', "interval = 10",
                                       "timeout = 1"])
    await start_gateway()
    check = await wait_until(lambda: _failed_check(home), timeout=20)
    assert "timed out" in check["last_error"]
    assert await wakes(home) == []


async def test_wakes_from_a_check_are_grouped_by_the_conversation_they_name(home, fake, root, start_gateway):
    register_polled(home, root)
    feed(root, entry("a", conversation="inbox"), entry("b", conversation="inbox"), entry("c", conversation="other"))
    await start_gateway()
    await wait_until(lambda: all_done(home))
    assert len(fake.starts) == 2
    prompts = sorted(s["prompt"] for s in fake.starts)
    assert sum("2 wakes" in p for p in prompts) == 1
