"""Hearth's plugin marketplace, generated from the pins (docs/decisions/0009).

Provision writes it, root-owned, to /opt/hearth/marketplace. Claude Code reads it live from there:
the tenant adds the directory as a marketplace, then installs each plugin from it. The pins live in
one place (the hearth distribution's own requirements, hearth.pins), so this file is derived, never
edited.

The shape is the one Ash ran on claude 2.1.288 (Buster's copy) and 2.1.300 in throwaway configs:
name, owner.name, and per plugin a name and a commit-pinned source. A plugin at its repository's root
is a `github` source; one in a subdirectory is `git-subdir`.
"""
import json
import re
import sys
from pathlib import Path

from hearth import pins as _pins

NAME = "hearth"
# Where each plugin lives inside its pinned repository. Order is the order Claude Code lists them.
PLUGINS = {"tapestry": "", "frontdesk": "plugins/claude-code"}
FILE = Path(".claude-plugin/marketplace.json")
_GITHUB = re.compile(r"^https://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(\.git)?$")


def entries(p=None) -> list[dict]:
    p = _pins.pins() if p is None else p
    if set(p) != set(PLUGINS):
        raise ValueError(f"pins name {sorted(p)}, the marketplace serves {sorted(PLUGINS)}")
    out = []
    for name, subdir in PLUGINS.items():
        pin = p[name]
        if subdir:
            src = {"source": "git-subdir", "url": pin["url"], "path": subdir, "sha": pin["commit"]}
        else:
            m = _GITHUB.match(pin["url"])
            if not m:
                raise ValueError(f"{name}: {pin['url']} isn't a github.com repository URL")
            src = {"source": "github", "repo": m["repo"], "sha": pin["commit"]}
        out.append({"name": name, "source": src})
    return out


def render(p=None) -> str:
    return json.dumps({"name": NAME, "owner": {"name": "Hearth"}, "plugins": entries(p)},
                      indent=2) + "\n"


def write(root: Path, p=None) -> str:
    """Write ROOT/.claude-plugin/marketplace.json. Never overwrites a file that differs: a different
    file is a pin change, which a person makes on purpose (delete it, then re-run)."""
    path = Path(root) / FILE
    text = render(p)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"{path} exists and isn't a regular file")
        if path.read_text() == text:
            return "present"
        raise RuntimeError(f"{path} exists and differs from the pins (a pin change?); remove it by hand")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(text)
    part.rename(path)
    return "written"


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) == 1 and a[0] == "render":
        sys.stdout.write(render())
        return 0
    if len(a) == 2 and a[0] == "write":
        try:
            print(f"{write(Path(a[1]))} {Path(a[1]) / FILE}")
        except RuntimeError as e:
            print(f"STOP: {e}", file=sys.stderr)
            return 1
        return 0
    print("usage: python -m hearth.marketplace render | write DIR", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
