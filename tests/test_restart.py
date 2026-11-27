"""An accepted wake survives the gateway stopping, however it stops (docs/primitives/WAKE.md)."""
import os
import signal
import subprocess
import sys

import pytest

from conftest import push, quiet, register, wait_until, wakes
from hearth import gateway


async def all_done(home) -> bool:
    found = await wakes(home)
    return bool(found) and all(w["state"] == "done" for w in found)


async def test_a_wake_accepted_and_pending_before_a_restart_runs_after_it(home, fake, root, start_gateway, clock):
    register(home, "ash", root)
    first = await start_gateway()
    await push(home, "ash", "talk", note="remember me", delay=100)
    await first.stop(grace=0)

    await start_gateway()
    await quiet()
    assert fake.starts == [], "a not-before wake ran early after the restart"
    clock.advance(101)
    await wait_until(lambda: all_done(home))
    assert "remember me" in fake.starts[0]["prompt"]
    assert len(fake.starts) == 1


async def test_a_wake_whose_turn_was_running_when_the_gateway_stopped_runs_again_and_says_so(
        home, fake, root, start_gateway):
    register(home, "ash", root)
    first = await start_gateway()
    fake.hold()
    await push(home, "ash", "talk", note="half done")
    await wait_until(lambda: len(fake.starts) == 1)

    await first.stop(grace=0)
    assert fake.ends == [], "the turn should have been cut off"
    assert [w["state"] for w in await _wakes_offline(home)] == ["pending"]

    fake.release()
    await start_gateway()
    await wait_until(lambda: all_done(home))
    again = fake.starts[1]
    assert "half done" in again["prompt"]
    assert "may have been shown to an earlier turn" in again["prompt"]
    assert len(fake.ends) == 1, "the wake must finish exactly once"


async def _wakes_offline(home):
    import sqlite3
    conn = sqlite3.connect(home.db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT state FROM wakes")]
    finally:
        conn.close()


async def test_a_second_gateway_for_the_same_home_refuses_to_start(home, fake, root, start_gateway):
    register(home, "ash", root)
    await start_gateway()
    with pytest.raises(gateway.GatewayError, match="already running"):
        await start_gateway()


def _gateway_process(home, fake, tmp_env):
    (home.root / "config.toml").write_text("tick_s = 0.05\nretry_s = 1\nshutdown_grace_s = 0\n")
    env = dict(os.environ, HEARTH_HOME=str(home.root), HEARTH_CLAUDE=str(fake.path), **tmp_env)
    return subprocess.Popen([sys.executable, "-m", "hearth", "gateway"], env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


async def test_a_gateway_killed_outright_leaves_no_turn_running_and_loses_no_wake(home, fake, root):
    home.ensure()
    register(home, "ash", root)
    env = {"FAKE_CLAUDE_DIR": str(fake.dir)}
    first = _gateway_process(home, fake, env)
    try:
        await wait_until(lambda: home.socket.exists(), what="the gateway to listen")
        fake.hold()
        await push(home, "ash", "talk", note="survive")
        await wait_until(lambda: len(fake.starts) == 1)
        orphan = fake.starts[0]["pid"]
        first.send_signal(signal.SIGKILL)
        first.wait()
        os.kill(orphan, 0)   # the turn outlived the gateway that started it

        second = _gateway_process(home, fake, env)
        try:
            await wait_until(lambda: not _exists(orphan), what="the orphaned turn to be killed on recovery")
            fake.release()
            await wait_until(lambda: len(fake.ends) == 1, what="the wake to run again")
            await wait_until(lambda: all_done(home))
            assert "may have been shown to an earlier turn" in fake.starts[-1]["prompt"]
        finally:
            second.terminate()
            second.wait(timeout=10)
    finally:
        if first.poll() is None:
            first.kill()
            first.wait()


def _exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def test_only_wakes_finished_very_long_ago_are_forgotten_so_a_key_stays_a_duplicate_until_then(
        home, fake, root, start_gateway, clock):
    register(home, "ash", root)
    gw = await start_gateway()
    await push(home, "ash", "talk", key="mail-1")
    await wait_until(lambda: all_done(home))
    day = 24 * 3600

    clock.advance(100 * day)
    await gw.stop(grace=0)
    gw = await start_gateway()
    assert (await push(home, "ash", "talk", key="mail-1"))["duplicate"]

    clock.advance(100 * day)
    await gw.stop(grace=0)
    await start_gateway()
    again = await push(home, "ash", "talk", key="mail-1")
    assert again["ok"] and not again["duplicate"]


def test_a_process_start_is_read_without_ps_where_proc_exists(monkeypatch, tmp_path):
    from hearth import proc
    if not proc.HAVE_PROC:
        pytest.skip("no /proc on this system")
    monkeypatch.setenv("PATH", str(tmp_path))      # no ps anywhere on it
    started = proc.start_time(os.getpid())
    assert started and started.startswith("proc:")
    assert proc.is_recorded_process(os.getpid(), started)


async def test_a_missing_working_directory_is_named_as_the_failure_not_the_program(tmp_path):
    from hearth import proc
    ran = await proc.run(["true"], cwd=str(tmp_path / "nowhere"), env={}, timeout=10)
    assert ran.error and "working directory" in ran.error and "nowhere" in ran.error
