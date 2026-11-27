"""Agents come and go without disturbing each other, and run with exactly the plugins they declare
(docs/primitives/AGENT.md)."""
import json

import pytest

from conftest import agent_status, ask, hearth_cli, push, quiet, register, status, wait_until, wakes
from hearth import agent as agents


async def all_done(home) -> bool:
    found = await wakes(home)
    return bool(found) and all(w["state"] == "done" for w in found)


def install(agent, *ids):
    """What `claude plugin list` will find in the agent's configuration directory."""
    agent.config_dir.mkdir(parents=True, exist_ok=True)
    (agent.config_dir / "fake_plugins.json").write_text(json.dumps([{"id": i, "enabled": True} for i in ids]))


async def test_registering_reloading_and_removing_one_agent_leaves_another_agents_running_turn_alone(
        home, fake, root, start_gateway):
    register(home, "ash", root)
    await start_gateway()
    fake.hold()
    await push(home, "ash", "talk", note="long job")
    await wait_until(lambda: len(fake.starts) == 1)
    running = fake.starts[0]["pid"]

    bee = register(home, "bee", root)
    assert (await ask(home, op="agent.reload", agent="bee"))["state"] == "loaded"
    bee.manifest.write_text(bee.manifest.read_text() + 'model = "haiku"\n')
    assert (await ask(home, op="agent.reload", agent="bee"))["ok"]
    agents.remove(home, "bee")
    assert (await ask(home, op="agent.reload", agent="bee"))["state"] == "removed"
    register(home, "cat", root)
    assert (await ask(home, op="agent.reload"))["ok"]
    await quiet()

    report = await status(home)
    assert [a["name"] for a in report["agents"]] == ["ash", "cat"]
    assert [t["conversation"] for t in agent_status(report, "ash")["live_turns"]] == ["talk"]
    assert len(fake.starts) == 1 and fake.ends == [], "ash's turn was disturbed"
    fake.release()
    await wait_until(lambda: all_done(home))
    assert fake.ends[0]["pid"] == running


async def test_a_reload_that_cannot_be_applied_leaves_the_agent_as_it_was_and_says_so(
        home, fake, root, start_gateway):
    ash = register(home, "ash", root)
    await start_gateway()
    ash.manifest.write_text("this is = not [valid toml")

    response = await ask(home, op="agent.reload", agent="ash")
    assert response["ok"] is False and "left as it was" in response["error"]
    assert agent_status(await status(home), "ash")["error"]

    await push(home, "ash", "talk")
    await wait_until(lambda: all_done(home))
    assert fake.starts[0]["cwd"] == str(ash.workdir.resolve()), "the agent did not keep its old manifest"

    ash.manifest.write_text(f'workdir = "{ash.workdir}"\nconfig_dir = "{ash.config_dir}"\n')
    assert (await ask(home, op="agent.reload", agent="ash"))["ok"]
    assert agent_status(await status(home), "ash")["error"] is None


async def test_an_agent_whose_manifest_is_broken_at_start_is_listed_with_the_reason_and_keeps_its_wakes(
        home, fake, root, start_gateway):
    ash = register(home, "ash", root)
    ash.manifest.write_text('colour = "blue"\n')
    await start_gateway()

    report = await status(home)
    assert "unknown setting colour" in agent_status(report, "ash")["error"]
    accepted = await push(home, "ash", "talk")
    assert accepted["ok"]
    await quiet()
    assert fake.starts == []

    ash.manifest.write_text(f'workdir = "{ash.workdir}"\n')
    await ask(home, op="agent.reload", agent="ash")
    await wait_until(lambda: all_done(home))


async def test_removing_an_agent_lets_its_running_turn_finish_and_keeps_its_wakes(home, fake, root, start_gateway):
    register(home, "ash", root)
    await start_gateway()
    fake.hold()
    await push(home, "ash", "talk")
    await wait_until(lambda: len(fake.starts) == 1)
    await push(home, "ash", "talk", note="after")

    agents.remove(home, "ash")
    await ask(home, op="agent.reload", agent="ash")
    refused = await push(home, "ash", "talk")
    assert refused["ok"] is False and "no agent named" in refused["error"]
    fake.release()
    await wait_until(lambda: len(fake.ends) == 1)
    await quiet()
    assert len(fake.starts) == 1, "a turn was started for an agent that is no longer registered"
    states = sorted(w["state"] for w in await wakes(home))
    assert states == ["done", "pending"]

    register(home, "ash", root)
    await ask(home, op="agent.reload", agent="ash")
    await wait_until(lambda: all_done(home), what="the kept wake to run once the agent is back")
    assert "after" in fake.starts[1]["prompt"]


async def test_an_agent_has_a_configuration_directory_of_its_own_unless_its_manifest_says_otherwise(
        home, fake, root, start_gateway):
    agents.add(home, "ash", "")
    agents.add(home, "bee", "")
    agents.add(home, "cat", f'config_dir = "{root / "shared"}"\n')
    await start_gateway()
    for name in ("ash", "bee", "cat"):
        await push(home, name, "talk")
    await wait_until(lambda: len(fake.ends) == 3)
    by_agent = {s["agent"]: s["config_dir"] for s in fake.starts}
    assert by_agent["ash"] == str(home.agents / "ash" / "claude")
    assert by_agent["bee"] == str(home.agents / "bee" / "claude")
    assert by_agent["cat"] == str(root / "shared")


async def test_an_agent_runs_with_exactly_the_plugins_its_manifest_declares_plus_hearths_own(
        home, fake, root, start_gateway):
    agent = register(home, "ash", root, lines=["[[plugin]]", 'id = "wanted@market"'])
    install(agent, "wanted@market", "stray@market")
    await start_gateway()

    await push(home, "ash", "talk")
    await wait_until(lambda: all_done(home))
    (start,) = fake.starts
    assert json.loads(start["settings"]) == {"enabledPlugins": {"wanted@market": True, "stray@market": False}}
    assert any(d.endswith("hearth/plugin") for d in start["plugin_dirs"])
    assert len(start["plugin_dirs"]) == 1


async def test_a_declared_plugin_that_did_not_load_is_reported_in_status_and_to_the_agent(
        home, fake, root, start_gateway):
    plugin = root / "not-a-plugin"
    plugin.mkdir()
    agent = register(home, "ash", root, lines=["[[plugin]]", 'id = "missing@market"', "[[plugin]]",
                                               f'dir = "{plugin}"'])
    install(agent)
    await start_gateway()

    report = agent_status(await status(home), "ash")
    by_label = {p["declared"]: p for p in report["plugins"]}
    assert by_label["missing@market"]["loaded"] is False
    assert "hearth agent install ash" in by_label["missing@market"]["detail"]
    assert by_label[str(plugin)]["loaded"] is False and "plugin.json" in by_label[str(plugin)]["detail"]

    await push(home, "ash", "talk")
    await wait_until(lambda: all_done(home))
    assert "missing@market" in fake.starts[0]["prompt"] and "not available" in fake.starts[0]["prompt"]


async def test_a_turn_whose_installed_plugins_cannot_be_listed_fails_instead_of_running_with_unknown_ones(
        home, fake, root, start_gateway):
    register(home, "ash", root)
    await start_gateway(claude="/nonexistent/claude")
    await push(home, "ash", "talk")
    pending = await wait_until(lambda: _failed(home), what="the failed turn")
    assert "claude plugin list" in pending["last_failure"]


async def _failed(home):
    found = [w for w in await wakes(home) if w["failures"]]
    return found[0] if found else None


async def test_installing_an_agents_plugins_adds_its_marketplaces_and_reports_what_failed(
        home, fake, root):
    agent = register(home, "ash", root, lines=[
        "[[marketplace]]", 'source = "some/market"', "[[plugin]]", 'id = "good@market"', "[[plugin]]",
        'id = "bad@market"'])
    fake.refuse_install("bad@market")

    done = hearth_cli(home, "agent", "install", "ash", env={"HEARTH_CLAUDE": str(fake.path),
                                                            "FAKE_CLAUDE_DIR": str(fake.dir)})
    assert done.returncode == 1
    assert "good@market" in done.stdout and "installed good@market" in done.stdout
    assert "bad@market: FAILED" in done.stdout
    added = [json.loads(l) for l in (fake.dir / "marketplaces.jsonl").read_text().splitlines()]
    assert [(m["source"], m["config"]) for m in added] == [("some/market", str(agent.config_dir))]
    installed = json.loads((agent.config_dir / "fake_plugins.json").read_text())
    assert [p["id"] for p in installed] == ["good@market"]


@pytest.mark.parametrize("manifest, says", [
    ("colour = 'blue'", "unknown setting colour"),
    ("turn_timeout = -1", "positive number"),
    ("model = 7", "model must be a string"),
    ("[env]\nA = 1", "env must be a table of strings"),
    ("[[plugin]]\nid = 'noat'", "name@marketplace"),
    ("[[plugin]]\nid = 'a@b'\ndir = '/x'", "exactly one of dir or id"),
    ("[[check]]\nname = 'c'\ncommand = 'true'", "needs an interval"),
    ("[[check]]\nname = 'c'\ncommand = ''\ninterval = 5", "needs a command"),
    ("[[check]]\nname = 'c'\ncommand = 'true'\ninterval = 5\n[[check]]\nname = 'c'\ncommand = 'true'\ninterval = 5",
     "two checks are named c"),
])
def test_a_manifest_that_makes_no_sense_is_refused_and_registers_nothing(home, manifest, says):
    done = hearth_cli(home, "agent", "add", "ash", "--manifest", "-", stdin=manifest)
    assert done.returncode == 1 and says in done.stderr
    assert agents.names(home) == []


def test_an_agent_name_that_could_escape_the_agents_directory_is_refused(home):
    done = hearth_cli(home, "agent", "add", "../evil")
    assert done.returncode == 1 and "not a usable agent name" in done.stderr
    assert not (home.root / "evil").exists()


# Permission mode (docs/primitives/AGENT.md) ------------------------------------------------------------

async def test_an_agents_turns_are_permissive_unless_its_manifest_says_otherwise(home, fake, root, start_gateway):
    from conftest import push, wait_until
    register(home, "ash", root)
    register(home, "wren", root, lines=['permission_mode = "acceptEdits"'])
    await start_gateway()
    await push(home, "ash", "a")
    await push(home, "wren", "w")
    await wait_until(lambda: len(fake.ends) == 2, what="both turns")
    modes = {s["agent"]: s["argv"][s["argv"].index("--permission-mode") + 1] for s in fake.starts}
    assert modes == {"ash": "bypassPermissions", "wren": "acceptEdits"}


def test_a_session_opened_as_the_agent_runs_with_the_same_permission_mode(home, root):
    from hearth import claude
    agent = register(home, "ash", root, lines=['permission_mode = "dontAsk"'])
    args = claude.launch_args(agent, "{}")
    assert args[args.index("--permission-mode") + 1] == "dontAsk"


def test_a_permission_mode_is_named_once_and_must_be_one_claude_code_accepts(home, root):
    import pytest
    from hearth import agent as agents
    for lines in (['permission_mode = "yolo"'], ['claude_args = ["--permission-mode", "plan"]'],
                  ['claude_args = ["--dangerously-skip-permissions"]']):
        with pytest.raises(agents.ManifestError, match="permission"):
            agents.parse("x", root / "agent.toml", "\n".join(lines))
