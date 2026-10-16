"""Bring a tenant's installed Hearth plugin to the pinned tree, keeping its options. Run by
home/provision step 5c AS THE TENANT, after `claude plugin install`:

    python -I -m hearth.pluginsync <claude> <name>

Why (Ash ran this on claude 2.1.288, 2026-10-16): Claude Code keys an installed plugin by its
version, not its commit. On a pin bump that keeps the version, a repeat `plugin install`,
`plugin update` and `plugin marketplace update` all exit 0 and leave the OLD tree. Only
`plugin uninstall` then `plugin install` moves it, and uninstall wipes the plugin's options in
settings.json (Front Desk's `home`, which a person set by hand), which reinstalling doesn't
bring back.

So, per plugin:
  - the installed tree equals root's export at the pin (the comparison check makes): nothing;
  - it differs, and no claude process of this tenant is running: read the plugin's options,
    uninstall, install, put every option back, and compare again;
  - it differs and a claude process is running: stop, and say to close it. Uninstalling under a
    live session is not run.
gitCommitSha is never consulted (it's the tenant's file, and it lags, see tenantcheck).

Exit 0: the tree equals the pin (now or already). 1: it doesn't, with the reason. One line out.
"""
import json
import os
import pwd
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from hearth import marketplace, pins, plugintree
from hearth.tenantcheck import REFERENCE, Tenant, Unreadable, load


def claude_dirs(home: Path) -> tuple[str, ...]:
    """Where this tenant's claude binaries live (the same rule as hearth.host)."""
    return (os.path.realpath(home / ".local" / "share" / "claude" / "versions"), "/opt/hearth/claude")


def live_claude(dirs: tuple[str, ...], proc: str = "/proc") -> list[int]:
    """This user's running processes whose binary is a claude under ``dirs``. A deleted binary
    reads "<path> (deleted)", which still has the directory prefix."""
    me, found = os.getuid(), []
    for d in os.listdir(proc):
        if not d.isdigit():
            continue
        try:
            if os.stat(f"{proc}/{d}").st_uid != me:
                continue
            exe = os.readlink(f"{proc}/{d}/exe")
        except OSError:
            continue
        if any(exe.startswith(x.rstrip("/") + "/") for x in dirs):
            found.append(int(d))
    return found


def installed_diffs(t: Tenant, name: str) -> list[str]:
    """How the installed tree differs from root's export at the pin. Empty means equal. A record
    this can't follow is a difference too, named, so it's never read as equal."""
    pid = f"{name}@{marketplace.NAME}"
    try:
        entries = (t.record("installed_plugins.json").get("plugins") or {}).get(pid)
    except Unreadable as e:
        return [f"couldn't read the install record: {e}"]
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        return [f"{0 if not isinstance(entries, list) else len(entries)} install records, want exactly 1"]
    ver = entries[0].get("version")
    if not isinstance(ver, str) or not ver or "/" in ver or ver in (".", ".."):
        return [f"version {ver!r} isn't a plain name"]
    installed = t.plugins / "cache" / marketplace.NAME / name / ver
    p = installed
    while p != t.home and p != p.parent:
        if p.is_symlink():
            return [f"a link on the install path: {p}"]
        p = p.parent
    if not installed.is_dir():
        return [f"{installed} is missing"]
    return plugintree.compare(t.ref / name / pins.pins()[name]["commit"], installed)


def options(t: Tenant, name: str) -> dict:
    """The plugin's options as `claude plugin configure` wrote them, in settings.json."""
    s = load(t.cfg / "settings.json")
    if not isinstance(s, dict):
        raise Unreadable(f"{t.cfg / 'settings.json'}: missing or not an object")
    o = ((s.get("pluginConfigs") or {}).get(f"{name}@{marketplace.NAME}") or {}).get("options") or {}
    if not isinstance(o, dict):
        raise Unreadable(f"pluginConfigs options for {name} isn't an object")
    return o


def run_claude(claude: str, *args: str, stdin: Optional[str] = None) -> None:
    p = subprocess.run([claude, "plugin", *args], input=stdin, capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        raise RuntimeError(f"claude plugin {' '.join(args)}: rc {p.returncode}: {(p.stderr or p.stdout).strip()[:300]}")


def sync(t: Tenant, name: str, claude: str, live: Callable[[], list[int]]) -> tuple[int, str]:
    pid = f"{name}@{marketplace.NAME}"
    diffs = installed_diffs(t, name)
    if not diffs:
        return 0, f"= {pid} tree equals the pin"
    running = live()
    if running:
        return 1, (f"{pid} differs from the pin ({diffs[0]}), and claude is running as this tenant "
                   f"(pid {' '.join(map(str, running))}). Close those sessions and stop "
                   f"hearth-host@{t.home.name} for the run, then re-run provision.")
    saved = None
    try:
        saved = options(t, name)
        run_claude(claude, "uninstall", pid)
        run_claude(claude, "install", pid)
        if saved:
            run_claude(claude, "configure", pid, "--values-stdin", stdin=json.dumps(saved))
        back = options(t, name)
    except (RuntimeError, Unreadable, OSError, subprocess.SubprocessError) as e:
        lost = f", and its hand-set options {sorted(saved)} are gone" if saved else ""
        return 1, f"{pid}: reinstall failed: {e}{lost}"
    if back != saved:
        return 1, f"{pid}: reinstalled, but its options came back as {sorted(back)}, were {sorted(saved)}"
    after = installed_diffs(t, name)
    if after:
        return 1, f"{pid}: reinstalled, still differs from the pin: {after[0]}"
    return 0, f"+ {pid} reinstalled at the pin ({diffs[0]} before), options kept: {sorted(saved) or 'none'}"


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) != 2 or a[1] not in marketplace.PLUGINS:
        print(f"usage: python -I -m hearth.pluginsync <claude> {'|'.join(marketplace.PLUGINS)}")
        return 1
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    rc, msg = sync(Tenant(home, ref=REFERENCE), a[1], a[0], lambda: live_claude(claude_dirs(home)))
    print(msg)
    return rc


if __name__ == "__main__":
    sys.exit(main())
