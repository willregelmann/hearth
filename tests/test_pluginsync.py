"""hearth.pluginsync against a FAKE TENANT HOME and a FAKE claude.

The fake claude does what Ash measured claude 2.1.288 doing (2026-10-16, throwaway configs):
`install` of an installed plugin changes nothing; `uninstall` removes the tree and the record and
empties the plugin's options in settings.json; `install` copies the marketplace's tree at its sha;
`configure --values-stdin` merges options. No real Claude Code runs here.
"""
import json
import shutil
import stat
import sys
from pathlib import Path

import pytest

from hearth import pins, pluginsync
from hearth.tenantcheck import Tenant

FAKE_CLAUDE = r'''#!@PY@
import json, shutil, sys
from pathlib import Path
home, ref, log = Path(@HOME@), Path(@REF@), Path(@LOG@)
cfg = home / ".claude"; plug = cfg / "plugins"
args = sys.argv[1:]
with log.open("a") as f: f.write(" ".join(args) + "\n")
assert args[0] == "plugin", args
verb, pid = args[1], args[2]
name = pid.split("@")[0]
rec_f = plug / "installed_plugins.json"; set_f = cfg / "settings.json"
rec = json.loads(rec_f.read_text()); s = json.loads(set_f.read_text())
cache = plug / "cache/hearth" / name / "0.1.0"
if verb == "uninstall":
    shutil.rmtree(cache); rec["plugins"].pop(pid)
    s.setdefault("pluginConfigs", {}).setdefault(pid, {})["options"] = {}
elif verb == "install":
    if pid in rec["plugins"]:
        print("already installed"); sys.exit(0)
    src = ref / "pinned" / name
    shutil.copytree(src, cache)
    rec["plugins"][pid] = [{"scope": "user", "installPath": str(cache), "version": "0.1.0", "gitCommitSha": "new"}]
elif verb == "configure":
    assert args[3] == "--values-stdin"
    s.setdefault("pluginConfigs", {}).setdefault(pid, {}).setdefault("options", {}).update(json.load(sys.stdin))
else:
    sys.exit("unexpected " + verb)
rec_f.write_text(json.dumps(rec)); set_f.write_text(json.dumps(s))
'''


def _tree(root: Path, hooks: str):
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin/plugin.json").write_text('{"version": "0.1.0"}')
    (root / "hooks").mkdir()
    (root / "hooks/hooks.json").write_text(hooks)


@pytest.fixture
def tenant(tmp_path):
    """frontdesk installed at an OLD tree, with a hand-set home option; root's export at the pin
    differs from it. The fake marketplace serves the pinned tree."""
    home, opt = tmp_path / "home", tmp_path / "opt"
    commit = pins.pins()["frontdesk"]["commit"]
    _tree(opt / "frontdesk" / commit, '{"hooks": {"Stop": []}}\n')              # root's export at the pin
    shutil.copytree(opt / "frontdesk" / commit, tmp_path / "pinned" / "frontdesk")  # what install fetches
    cache = home / ".claude/plugins/cache/hearth/frontdesk/0.1.0"
    _tree(cache, '{"hooks": {}}\n')                                            # the old tree
    (home / ".claude/plugins/installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "frontdesk@hearth": [{"scope": "user", "installPath": str(cache), "version": "0.1.0", "gitCommitSha": "old"}]}}))
    (home / ".claude/settings.json").write_text(json.dumps({"pluginConfigs": {"frontdesk@hearth": {
        "options": {"python": "/opt/hearth/venv/bin/python", "home": "/home/buster/.frontdesk/buster"}}}}))
    log = tmp_path / "claude.log"
    claude = tmp_path / "claude"
    claude.write_text(FAKE_CLAUDE.replace("@PY@", sys.executable).replace("@HOME@", repr(str(home)))
                      .replace("@REF@", repr(str(tmp_path))).replace("@LOG@", repr(str(log))))
    claude.chmod(claude.stat().st_mode | stat.S_IXUSR)
    t = Tenant(home, ref=opt)
    t.claude, t.log = str(claude), log
    return t


def _opts(t):
    return json.loads((t.cfg / "settings.json").read_text())["pluginConfigs"]["frontdesk@hearth"]["options"]


def _calls(t):
    return t.log.read_text().splitlines() if t.log.exists() else []


def test_a_tree_that_differs_is_reinstalled_and_every_option_comes_back(tenant):
    before = _opts(tenant)
    rc, msg = pluginsync.sync(tenant, "frontdesk", tenant.claude, live=lambda: [])
    assert rc == 0, msg
    assert pluginsync.installed_diffs(tenant, "frontdesk") == []
    assert _opts(tenant) == before                     # home survives the uninstall
    assert [c.split()[1] for c in _calls(tenant)] == ["uninstall", "install", "configure"]
    assert "options kept: ['home', 'python']" in msg


def test_the_fake_claude_really_wipes_options_and_install_alone_moves_nothing(tenant):
    """Control: the fake behaves as measured, so the test above proves the round trip."""
    pluginsync.run_claude(tenant.claude, "install", "frontdesk@hearth")
    assert pluginsync.installed_diffs(tenant, "frontdesk") != []      # "already installed"
    pluginsync.run_claude(tenant.claude, "uninstall", "frontdesk@hearth")
    pluginsync.run_claude(tenant.claude, "install", "frontdesk@hearth")
    assert _opts(tenant) == {}


def test_a_tree_that_equals_the_pin_is_left_alone(tenant):
    pluginsync.sync(tenant, "frontdesk", tenant.claude, live=lambda: [])
    tenant.log.unlink()
    rc, msg = pluginsync.sync(tenant, "frontdesk", tenant.claude, live=lambda: [4242])
    assert rc == 0 and msg.startswith("= ") and _calls(tenant) == []


def test_a_live_claude_stops_it_and_nothing_is_touched(tenant):
    before = _opts(tenant)
    rc, msg = pluginsync.sync(tenant, "frontdesk", tenant.claude, live=lambda: [4242])
    assert rc == 1 and "pid 4242" in msg and "Close those sessions" in msg
    assert _calls(tenant) == [] and _opts(tenant) == before
    assert pluginsync.installed_diffs(tenant, "frontdesk") != []


def test_options_that_dont_come_back_are_a_failure(tenant):
    src = Path(tenant.claude).read_text().replace(
        '.setdefault("options", {}).update(json.load(sys.stdin))', '.setdefault("options", {})')
    Path(tenant.claude).write_text(src)
    rc, msg = pluginsync.sync(tenant, "frontdesk", tenant.claude, live=lambda: [])
    assert rc == 1 and "options came back as []" in msg


def test_a_reinstall_that_still_lands_another_tree_is_a_failure(tenant, tmp_path):
    """The marketplace served something other than root's export (e.g. its sha wasn't moved)."""
    (tmp_path / "pinned/frontdesk/hooks/hooks.json").write_text('{"hooks": {"Other": []}}\n')
    rc, msg = pluginsync.sync(tenant, "frontdesk", tenant.claude, live=lambda: [])
    assert rc == 1 and "still differs from the pin" in msg


def test_an_unreadable_record_is_a_difference_never_equal(tenant):
    (tenant.plugins / "installed_plugins.json").write_text("{")
    assert pluginsync.installed_diffs(tenant, "frontdesk")[0].startswith("couldn't read")


def test_live_claude_finds_a_process_under_the_dirs_and_not_others(tmp_path):
    import os
    import subprocess
    v = tmp_path / "versions"
    v.mkdir()
    shutil.copy2(os.path.realpath(sys.executable), v / "2.1.288")
    p = subprocess.Popen([str(v / "2.1.288"), "-c", "import time; time.sleep(30)"])
    q = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        found = pluginsync.live_claude((str(v),))
        assert p.pid in found and q.pid not in found
    finally:
        p.kill(); q.kill()
