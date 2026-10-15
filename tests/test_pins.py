"""The pin-equality check (docs/decisions/0009, Confirmation).

FAKE TENANT HOME: these build a tenant's home and plugin environment in tmp_path. A real
provisioned tenant (a user made by home/provision, running claude with both plugins) doesn't exist
on this host yet. Until it does, these prove the check, not a tenant.

Each red arm is one way a plugin can end up importing something other than the pin, and the check
must name it. The hearth venv is the interpreter running these tests (pip install -e .[dev]).
"""
import subprocess
import sys
from pathlib import Path

import pytest

from hearth import pins

HEARTH_PY = sys.executable


def tenant_env(**over):
    """A tenant whose plugins both point at Hearth's interpreter: the configuration provision is to
    write."""
    env = {"TAPESTRY_PYTHON": HEARTH_PY, "FRONTDESK_PYTHON": HEARTH_PY}
    env.update(over)
    return {k: v for k, v in env.items() if v is not None}


def test_the_pins_are_full_commits_of_both_packages():
    p = pins.pins()
    assert set(p) == {"frontdesk", "tapestry"}
    for name, pin in p.items():
        assert len(pin["commit"]) == 40, name


def test_the_installed_metadata_carries_the_same_pins_as_pyproject():
    """pins() reads the installed distribution; pyproject.toml is the source it was built from.
    A stale install (pyproject changed, venv not reinstalled) shows as a difference here."""
    assert pins.pins() == pins.pins(pins.PYPROJECT)


def test_a_non_editable_install_reads_its_pins_with_no_source_tree(tmp_path):
    """The case /opt/hearth/venv is: a normal install, run from outside any checkout. pyproject.toml
    isn't in site-packages, so reading it there would fail."""
    venv = tmp_path / "v"
    subprocess.run(["uv", "venv", "-q", "-p", HEARTH_PY, str(venv)], check=True)
    subprocess.run(["uv", "pip", "install", "-q", "--no-deps", "--python", str(venv / "bin/python"),
                    str(pins.PYPROJECT.parent)], check=True)
    r = subprocess.run([str(venv / "bin/python"), "-I", "-c",
                        "import json; from hearth import pins; print(json.dumps(pins.pins()))"],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    import json
    assert json.loads(r.stdout) == pins.pins(pins.PYPROJECT)


def test_hearths_own_venv_imports_exactly_the_pins():
    got = pins.installed(HEARTH_PY, ["frontdesk", "tapestry"])
    for name, pin in pins.pins().items():
        du = got[name]["direct_url"]
        assert du["url"] == pin["url"] and du["vcs_info"]["commit_id"] == pin["commit"], name


def test_green_a_tenant_whose_plugins_run_hearths_interpreter(tmp_path):
    assert pins.problems(HEARTH_PY, tenant_env(), tmp_path) == []


def test_green_frontdesk_configured_through_the_plugin_option(tmp_path):
    env = tenant_env(FRONTDESK_PYTHON=None, CLAUDE_PLUGIN_OPTION_PYTHON=HEARTH_PY)
    assert pins.problems(HEARTH_PY, env, tmp_path) == []


@pytest.fixture(scope="module")
def own_tapestry_home(tmp_path_factory):
    """A TAPESTRY_HOME whose venv has the same packages at the same commits: what Tapestry's own
    `bin/tapestry install` makes. Same versions, wrong interpreter, so only the interpreter check
    can catch it."""
    home = tmp_path_factory.mktemp("own") / ".tapestry"
    d = home / "venv"
    subprocess.run(["uv", "venv", "-q", "-p", HEARTH_PY, str(d)], check=True)
    deps = [f"{n} @ git+{p['url']}@{p['commit']}" for n, p in pins.pins().items()]
    subprocess.run(["uv", "pip", "install", "-q", "--python", str(d / "bin/python"), *deps], check=True)
    return home


def test_red_tapestry_falls_back_to_its_own_venv(tmp_path, own_tapestry_home):
    """No TAPESTRY_PYTHON: bin/tapestry runs $TAPESTRY_HOME/venv, which its installer built."""
    env = tenant_env(TAPESTRY_PYTHON=None, TAPESTRY_HOME=str(own_tapestry_home))
    found = pins.problems(HEARTH_PY, env, tmp_path)
    assert found == [f"tapestry: runs {own_tapestry_home / 'venv'}, not Hearth's {sys.prefix}"]


def test_red_frontdesk_unset_runs_python3_from_path(tmp_path):
    found = pins.problems(HEARTH_PY, tenant_env(FRONTDESK_PYTHON=None), tmp_path)
    assert found == ["frontdesk: runs 'python3' from PATH, not Hearth's interpreter"]


def test_red_tapestry_unset_and_never_installed(tmp_path):
    found = pins.problems(HEARTH_PY, tenant_env(TAPESTRY_PYTHON=None), tmp_path)
    assert len(found) == 1 and "doesn't exist" in found[0]


def test_red_a_moved_pin_is_named(tmp_path):
    """Hearth's pyproject names a different commit than the one installed: the venv is stale."""
    text = pins.PYPROJECT.read_text()
    moved = tmp_path / "pyproject.toml"
    commit = pins.pins()["tapestry"]["commit"]
    moved.write_text(text.replace(commit, "f" * 40))
    found = pins.problems(HEARTH_PY, tenant_env(), tmp_path, pyproject=moved)
    assert found == [f"tapestry: imports {pins.pins()['tapestry']['url']}@{commit}, pinned "
                     f"{pins.pins()['tapestry']['url']}@{'f' * 40}"]


def test_red_an_unpinned_dependency_is_refused(tmp_path):
    loose = tmp_path / "pyproject.toml"
    loose.write_text(pins.PYPROJECT.read_text().replace(
        "@" + pins.pins()["frontdesk"]["commit"], "@main"))
    with pytest.raises(ValueError, match="not pinned"):
        pins.pins(loose)
