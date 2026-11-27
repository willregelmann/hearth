"""The `hearth` command (docs/interfaces/COMMANDS.md)."""
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import uuid

from conftest import agent_status, hearth_cli, register, wait_until, wakes
from hearth import agent as agents


async def cli(home, *args, **kw):
    return await asyncio.to_thread(hearth_cli, home, *args, **kw)


async def all_done(home) -> bool:
    found = await wakes(home)
    return bool(found) and all(w["state"] == "done" for w in found)


def test_a_command_that_needs_the_gateway_says_it_is_not_running_and_fails(home):
    done = hearth_cli(home, "wake", "--agent", "ash", "--conversation", "talk")
    assert done.returncode == 3 and "not running" in done.stderr
    done = hearth_cli(home, "status")
    assert done.returncode == 3 and "not running" in done.stderr


def test_agents_are_registered_listed_and_removed_without_a_gateway(home, root):
    done = hearth_cli(home, "agent", "add", "ash", "--workdir", str(root / "w"), "--model", "haiku")
    assert done.returncode == 0 and "the gateway is not running" in done.stdout
    assert hearth_cli(home, "agent", "add", "ash").returncode == 1, "registering twice should be refused"
    listed = json.loads(hearth_cli(home, "agent", "list", "--json").stdout)
    assert [a["name"] for a in listed] == ["ash"] and listed[0]["error"] is None
    assert agents.load(home, "ash").model == "haiku"

    assert hearth_cli(home, "agent", "remove", "ash").returncode == 0
    assert hearth_cli(home, "agent", "remove", "ash").returncode == 1
    assert json.loads(hearth_cli(home, "agent", "list", "--json").stdout) == []


async def test_the_operator_raises_lists_and_cancels_wakes(home, fake, root, start_gateway, clock):
    await cli(home, "agent", "add", "ash", "--workdir", str(root / "w"))
    (root / "w").mkdir()
    await start_gateway()
    assert "the gateway has applied it" in (await cli(home, "agent", "reload", "ash")).stdout

    done = await cli(home, "wake", "--agent", "ash", "--conversation", "talk", "--note", "hello", "--key", "k1")
    assert done.returncode == 0 and "accepted wake" in done.stdout
    again = await cli(home, "wake", "--agent", "ash", "--conversation", "talk", "--key", "k1")
    assert again.returncode == 0 and "already accepted" in again.stdout
    await wait_until(lambda: all_done(home))
    assert len(fake.starts) == 1 and "- cli: hello" in fake.starts[0]["prompt"]

    later = await cli(home, "wake", "--agent", "ash", "--conversation", "talk", "--in", "1h30m")
    assert later.returncode == 0
    listing = json.loads((await cli(home, "wake", "list", "--agent", "ash", "--json")).stdout)
    [pending] = listing
    assert pending["not_before"] == clock.now + 5400
    cancelled = await cli(home, "wake", "cancel", str(pending["id"]), "--reason", "plans changed")
    assert cancelled.returncode == 0
    everything = json.loads((await cli(home, "wake", "list", "--all", "--json")).stdout)
    assert sorted(w["state"] for w in everything) == ["canceled", "done"]

    refused = await cli(home, "wake", "cancel", str(pending["id"]), "--reason", "plans changed")
    assert refused.returncode == 1 and "already canceled" in refused.stderr


async def test_a_wake_command_with_nothing_to_go_on_refuses_instead_of_guessing(home, fake, root, start_gateway):
    register(home, "ash", root)
    await start_gateway()
    no_agent = await cli(home, "wake", "--conversation", "talk")
    assert no_agent.returncode == 1 and "which agent" in no_agent.stderr
    no_conversation = await cli(home, "wake", "--agent", "ash")
    assert no_conversation.returncode == 1 and "which conversation" in no_conversation.stderr
    both = await cli(home, "wake", "--agent", "ash", "--conversation", "c", "--in", "5m", "--at", "2030-01-01T00:00:00Z")
    assert both.returncode == 1 and "not both" in both.stderr
    nonsense = await cli(home, "wake", "--agent", "ash", "--conversation", "c", "--in", "soonish")
    assert nonsense.returncode == 1 and "delay" in nonsense.stderr
    assert await wakes(home) == []


async def test_a_wake_set_from_inside_a_session_goes_to_the_conversation_it_was_set_in(
        home, fake, root, start_gateway):
    register(home, "ash", root)
    await start_gateway()
    session = str(uuid.uuid4())
    fake.know_session(session)
    done = await cli(home, "wake", "--source", "self", "--at", "1990-01-01T00:00:00Z", "--note", "back again",
                     env={"HEARTH_AGENT": "ash", "CLAUDE_CODE_SESSION_ID": session})
    assert done.returncode == 0, done.stderr
    await wait_until(lambda: all_done(home))
    assert fake.starts[0]["resume"] == session
    assert "- self: back again" in fake.starts[0]["prompt"]


async def test_status_says_what_the_gateway_is_holding_back_and_why(home, fake, root, start_gateway, clock):
    register(home, "ash", root, lines=["[[plugin]]", 'id = "gone@market"'])
    await start_gateway()
    fake.mode(fail="exit")
    await cli(home, "wake", "--agent", "ash", "--conversation", "talk", "--note", "x")
    await wait_until(lambda: _failed(home))

    text = (await cli(home, "status")).stdout
    assert "agent ash" in text
    assert "plugin gone@market: NOT LOADED" in text
    assert "failed 1x" in text and "exit 1" in text
    assert "turn 1 failed in talk" in text
    as_json = json.loads((await cli(home, "status", "--json")).stdout)
    assert agent_status(as_json, "ash")["wakes"][0]["failures"] == 1


async def _failed(home):
    return [w for w in await wakes(home) if w["failures"]]


def test_the_gateway_runs_until_told_to_stop_and_then_leaves_nothing_listening(home, fake, root):
    register(home, "ash", root)
    env = dict(os.environ, HEARTH_HOME=str(home.root), HEARTH_CLAUDE=str(fake.path),
               FAKE_CLAUDE_DIR=str(fake.dir))
    gw = subprocess.Popen([sys.executable, "-m", "hearth", "gateway"], env=env, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.time() + 15
        while not home.socket.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert hearth_cli(home, "status").returncode == 0
        refused = subprocess.run([sys.executable, "-m", "hearth", "gateway"], env=env, capture_output=True,
                                 text=True, timeout=30)
        assert refused.returncode == 1 and "already running" in refused.stderr
        gw.send_signal(signal.SIGTERM)
        assert gw.wait(timeout=15) == 0
        assert not home.socket.exists()
    finally:
        if gw.poll() is None:
            gw.kill()
            gw.wait()
        gw.stderr.close()


def test_the_plugin_hearth_loads_into_every_session_is_where_the_command_says(home):
    from pathlib import Path
    where = Path(hearth_cli(home, "plugin-dir").stdout.strip())
    manifest = json.loads((where / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "hearth"
    hooks = json.loads((where / "hooks" / "hooks.json").read_text())["hooks"]
    assert set(hooks) == {"SessionStart", "SessionEnd"}
    assert {"agents", "status", "wake"} <= {p.stem for p in (where / "commands").glob("*.md")}


def test_with_no_hearth_home_and_no_home_directory_the_command_says_so(monkeypatch):
    from pathlib import Path
    from hearth.home import ConfigError, Home
    import pytest

    def no_home():
        raise RuntimeError("Could not determine home directory.")
    monkeypatch.setattr(Path, "home", staticmethod(no_home))
    with pytest.raises(ConfigError, match="HEARTH_HOME"):
        Home.from_env({})


def test_install_writes_the_session_hooks_and_keeps_the_rest_of_the_settings(home, root, fake):
    agent = register(home, "ash", root)
    agent.config_dir.mkdir(parents=True, exist_ok=True)
    settings = agent.config_dir / "settings.json"
    settings.write_text(json.dumps({"model": "keep-me", "hooks": {"SessionStart": [
        {"hooks": [{"type": "command", "command": "echo mine"}]}]}}))
    for _ in range(2):          # installing twice leaves one copy
        done = hearth_cli(home, "agent", "install", "ash", env={"HEARTH_CLAUDE": str(fake.path)})
        assert done.returncode == 0, done.stdout + done.stderr
    written = json.loads(settings.read_text())
    assert written["model"] == "keep-me"
    starts = [h["command"] for g in written["hooks"]["SessionStart"] for h in g["hooks"]]
    assert starts[0] == "echo mine" and len(starts) == 2 and "--record-only" in starts[1]
    assert [h["command"] for g in written["hooks"]["SessionEnd"] for h in g["hooks"]][0].endswith(
        "hook session-end --record-only")


def test_install_sets_the_options_the_manifest_gives_each_plugin_and_reports_any_it_could_not(home, root, fake):
    plugin = root / "desk-plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "desk"}))
    register(home, "ash", root, lines=[
        "[[plugin]]", f'dir = "{plugin}"', 'options = {home = "/home/agent/desk", python = "/usr/bin/python3"}',
        "[[plugin]]", 'id = "other@market"', 'options = {token_file = "/run/secret"}'])
    fake.refuse_configure("other@market")      # it installs; only its options can't be set
    done = hearth_cli(home, "agent", "install", "ash", env={"HEARTH_CLAUDE": str(fake.path)})
    assert done.returncode == 1, "a plugin whose options couldn't be set was not reported as a failure"
    assert "desk-plugin: options set (home, python)" in done.stdout
    assert "other@market: options FAILED" in done.stdout
    settings = json.loads((root / "ash-claude" / "settings.json").read_text())
    assert settings["pluginConfigs"]["desk@inline"]["options"] == {"home": "/home/agent/desk", "python": "/usr/bin/python3"}
    assert any("--record-only" in h["command"] for g in settings["hooks"]["SessionStart"] for h in g["hooks"]), \
        "writing the session hooks lost or skipped"


def test_a_plugins_options_must_be_single_line_strings(home, root):
    import pytest
    with pytest.raises(agents.ManifestError, match="options"):
        register(home, "ash", root, lines=["[[plugin]]", 'id = "a@b"', "options = {n = 3}"])
