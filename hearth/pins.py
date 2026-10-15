"""Hearth's pinned imports, and the check that a tenant runs exactly them (docs/decisions/0009).

The pins are written once, in pyproject.toml. At run time they are read from the installed hearth
distribution's own metadata (its Requires-Dist), which is what pip or uv installed from that file:
pyproject.toml itself isn't installed, so a normal (non-editable) install like /opt/hearth/venv
has no file to read. What is checked is
what the plugins will actually run: each plugin starts its own interpreter (Tapestry's launcher
uses TAPESTRY_PYTHON or its own ~/.tapestry/venv; Front Desk's runs FRONTDESK_PYTHON or the
plugin's configured python), so the Hearth venv importing the right commit proves nothing about
the plugin unless the plugin's interpreter is that venv.
"""
import json
import os
import re
import subprocess
import tomllib
from importlib import metadata
from pathlib import Path
from typing import Optional

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
_DEP = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)(\[[^\]]*\])?\s*@\s*git\+(?P<url>[^@\s]+)@(?P<commit>[0-9a-f]{40})$")


def _parse(deps) -> dict[str, dict]:
    out = {}
    for dep in deps:
        if ";" in dep:          # an environment marker: only optional extras carry one here
            if "extra ==" in dep:
                continue
            raise ValueError(f"unexpected marker on a dependency: {dep!r}")
        m = _DEP.match(dep.strip())
        if not m:
            raise ValueError(f"not pinned to a 40-character commit: {dep!r}")
        out[m["name"]] = {"url": m["url"], "commit": m["commit"]}
    return out


def pins(pyproject: Optional[Path] = None) -> dict[str, dict]:
    """{name: {"url", "commit"}} for every git dependency. A dependency that isn't pinned to a
    full commit is an error, not skipped: a branch or tag can move without review.

    By default the pins come from the installed hearth distribution, so they are what this
    install was built from. Pass a pyproject.toml to read the source file instead."""
    if pyproject is not None:
        return _parse(tomllib.loads(pyproject.read_text())["project"]["dependencies"])
    return _parse(metadata.requires("hearth") or [])


_PROBE = r"""
import json, sys
from importlib import metadata
out = {"executable": sys.executable, "prefix": sys.prefix}
for name in sys.argv[1:]:
    try:
        d = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        out[name] = None
        continue
    du = d.read_text("direct_url.json")
    out[name] = {"version": d.version, "direct_url": json.loads(du) if du else None}
print(json.dumps(out))
"""


def installed(python: str, names) -> dict:
    """What ``python`` would import for each name: version and the commit it was installed from.
    Runs that interpreter, never this one, so the answer is about the plugin's environment."""
    r = subprocess.run([python, "-I", "-c", _PROBE, *names], capture_output=True, text=True,
                       timeout=60, env={"PATH": "/usr/bin:/bin"})
    if r.returncode != 0:
        raise RuntimeError(f"{python} couldn't be probed: {r.stderr.strip()}")
    return json.loads(r.stdout)


def plugin_pythons(env: dict, home: Path) -> dict[str, str]:
    """The interpreter each plugin would start, resolved the way its own launcher does.

    tapestry: bin/tapestry runs ${TAPESTRY_PYTHON:-${TAPESTRY_HOME:-$HOME/.tapestry}/venv/bin/python}.
    frontdesk: scripts/frontdesk-run runs ${FRONTDESK_PYTHON:-${CLAUDE_PLUGIN_OPTION_PYTHON:-python3}}.
    """
    tap_home = env.get("TAPESTRY_HOME") or str(home / ".tapestry")
    fd = env.get("FRONTDESK_PYTHON") or env.get("CLAUDE_PLUGIN_OPTION_PYTHON") or "python3"
    return {"tapestry": env.get("TAPESTRY_PYTHON") or f"{tap_home}/venv/bin/python", "frontdesk": fd}


def problems(hearth_python: str, env: dict, home: Path, pyproject: Optional[Path] = None) -> list[str]:
    """Everything wrong with a tenant's plugin interpreters, as sentences. Empty means each plugin
    runs Hearth's interpreter and imports exactly the pinned commit."""
    want = pins(pyproject)
    found = []
    hearth_prefix = installed(hearth_python, [])["prefix"]
    for plugin, python in plugin_pythons(env, home).items():
        if not os.path.isabs(python):
            found.append(f"{plugin}: runs {python!r} from PATH, not Hearth's interpreter")
            continue
        if not Path(python).exists():
            found.append(f"{plugin}: its interpreter {python} doesn't exist")
            continue
        got = installed(python, [plugin])
        if got["prefix"] != hearth_prefix:
            found.append(f"{plugin}: runs {got['prefix']}, not Hearth's {hearth_prefix}")
        dist = got[plugin]
        if dist is None:
            found.append(f"{plugin}: not installed in {got['prefix']}")
            continue
        du = dist["direct_url"] or {}
        commit = (du.get("vcs_info") or {}).get("commit_id")
        if du.get("url") != want[plugin]["url"] or commit != want[plugin]["commit"]:
            found.append(f"{plugin}: imports {du.get('url')}@{commit}, pinned "
                         f"{want[plugin]['url']}@{want[plugin]['commit']}")
    return found
