"""The tenant-side checks for Hearth's plugins, run by home/check AS THE TENANT.

    python -I -m hearth.tenantcheck plugin_match <name>   the plugin Claude Code will load is the pin
    python -I -m hearth.tenantcheck frontdesk_home        Front Desk's identity directory is set
    python -I -m hearth.tenantcheck other_plugins         plugins enabled from anywhere else
    python -I -m hearth.tenantcheck host_running          hearth-host@<tenant> runs as the tenant

Exit codes follow check's: 0 GREEN, 1 RED, 4 KNOWN (reported, never green, doesn't fail the run),
5 PENDING (a setup step a person still owes; fails the run). The message is one line.

Everything read here is in the tenant's home and the tenant is the judged party, so: settings and
records are parsed, never grepped; anything that isn't a regular JSON file under 1 MiB is RED; a
place that can't be read is RED, never "nothing found". The verdict on a plugin is its installed
tree compared with root's export at the CURRENT pin (hearth.plugintree). gitCommitSha is reported
when it disagrees, but never decides: it's a tenant-editable field.

Read from Ash's runs (claude 2.1.288 and 2.1.300, throwaway configs) and the plugin loading docs:
settings ~/.claude/settings.json, overridden by ~/.claude/settings.local.json (turns run with
cwd=$HOME, so those two are the whole user-and-project pair); records in ~/.claude/plugins/{installed_plugins,
known_marketplaces}.json; installed_plugins values are arrays of {scope, installPath, version,
gitCommitSha}; installPath is cache/hearth/<name>/<version>, keyed by the plugin's version, not
its commit. CLAUDE_CODE_PLUGIN_CACHE_DIR moves the plugins root; check can't see a tenant's session
env, so a plugins root set anywhere else is not something this can rule out (see the README).
"""
import json
import os
import pwd
import stat
import subprocess
import sys
from pathlib import Path

from hearth import marketplace, pins, plugintree

HEARTH_PY = "/opt/hearth/venv/bin/python"
MARKETPLACE = "/opt/hearth/marketplace"
REFERENCE = "/opt/hearth/plugins"
GREEN, RED, KNOWN, PENDING = 0, 1, 4, 5
_BOUND = 1 << 20


class Unreadable(Exception):
    pass


def load(path: Path):
    """A tenant-written JSON file: regular file, opened non-blocking, at most 1 MiB. None if it
    doesn't exist; Unreadable for anything else that isn't a parseable JSON file."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except FileNotFoundError:
        if os.path.lexists(path):
            raise Unreadable(f"{path}: a dangling link")
        return None
    except OSError as e:
        raise Unreadable(f"{path}: {e.strerror}")
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise Unreadable(f"{path}: not a regular file")
        raw = f.read(_BOUND + 1)
    if len(raw) > _BOUND:
        raise Unreadable(f"{path}: over {_BOUND} bytes")
    try:
        return json.loads(raw)
    except ValueError as e:
        raise Unreadable(f"{path}: unparseable ({type(e).__name__})")


def _merge(base, over):
    """over wins; objects merge key by key, anything else is replaced whole."""
    if not (isinstance(base, dict) and isinstance(over, dict)):
        return over
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if k in base else v
    return out


class Tenant:
    """What a tenant's Claude Code reads, located from its passwd home."""

    def __init__(self, home: Path, hearth_py=HEARTH_PY, mkt=MARKETPLACE, ref=REFERENCE,
                 writable=None):
        self.home = Path(home)
        self.cfg = self.home / ".claude"
        self.plugins = self.cfg / "plugins"
        self.hearth_py, self.mkt, self.ref = hearth_py, mkt, Path(ref)
        self.writable = writable or _writable_by_me

    def settings(self) -> dict:
        """The settings a turn runs with. home/turn starts claude with cwd=$HOME, so ~/.claude is
        both the user and the project settings dir, and settings.local.json there is read on every
        turn and overrides settings.json (Ash RAN this for enabledPlugins on 2.1.288 and 2.1.300,
        #68). The deep merge with local winning is assumed for every other key: read, not run."""
        s = load(self.cfg / "settings.json")
        if not isinstance(s, dict):
            raise Unreadable(f"{self.cfg / 'settings.json'}: missing or not an object")
        local = load(self.cfg / "settings.local.json")
        if local is None:
            return s
        if not isinstance(local, dict):
            raise Unreadable(f"{self.cfg / 'settings.local.json'}: not an object")
        return _merge(s, local)

    def record(self, name: str):
        d = load(self.plugins / name)
        if not isinstance(d, dict):
            raise Unreadable(f"{self.plugins / name}: missing or not an object")
        return d


def _writable_by_me(p: Path) -> list[str]:
    """Every place this user could write to change what `p` runs: the real file it resolves to, and
    the real directory holding every component met while resolving it, links included, wherever in
    the path they are. A symlink's own mode is 0777 on Linux, so asking access() about a link says
    "writable" to everyone; a link can only be replaced by writing the directory it sits in, so that
    directory is what's asked instead.

    Resolution is component by component, as the kernel does it: a link met anywhere (leaf or
    ancestor) has its target spliced in and resolved the same way, so every hop's directory is seen.
    realpath() would collapse a chain met at an ancestor and hide its middle hops."""
    found: list[Path] = []

    def add(q: Path):
        if q not in found:
            found.append(q)

    start = Path(p) if os.path.isabs(p) else Path.cwd() / p
    parts = list(start.parts[1:])
    cur, hops = Path("/"), 0
    add(cur)
    while parts:
        name = parts.pop(0)
        if name in ("", "."):
            continue
        if name == "..":
            cur = cur.parent
            continue
        nxt = cur / name
        if nxt.is_symlink():
            hops += 1
            if hops > 40:
                return [f"{p}: more than 40 links"]
            t = Path(os.readlink(nxt))
            parts = list(t.parts[1:] if t.is_absolute() else t.parts) + parts
            if t.is_absolute():
                cur = Path("/")
            continue
        cur = nxt
        add(cur)
    return [str(q) for q in found if os.access(q, os.W_OK)]


def plugin_match(t: Tenant, name: str):
    """GREEN only if Claude Code will load <name>@hearth from root's marketplace, from exactly one
    user-scope install, whose tree equals root's export at the current pin, running Hearth's
    interpreter with the pinned package. Everything wrong is listed, not just the first thing."""
    pid = f"{name}@{marketplace.NAME}"
    want = pins.pins()[name]
    found = []
    try:
        s = t.settings()
        known = t.record("known_marketplaces.json")
        inst = t.record("installed_plugins.json")
    except Unreadable as e:
        return RED, f"couldn't look: {e}"
    # 1. The marketplace both settings and the records point at is root's, by exact path.
    src = {"source": "directory", "path": t.mkt}
    if (s.get("extraKnownMarketplaces") or {}).get(marketplace.NAME, {}).get("source") != src:
        found.append(f"settings declare marketplace {marketplace.NAME} as "
                     f"{(s.get('extraKnownMarketplaces') or {}).get(marketplace.NAME)}, not {t.mkt}")
    k = known.get(marketplace.NAME) or {}
    if k.get("source") != src or k.get("installLocation") != t.mkt:
        found.append(f"known_marketplaces has {marketplace.NAME} at {k.get('installLocation')}, not {t.mkt}")
    # 2. Enabled, in settings.json and settings.local.json merged (managed settings and the
    #    session's flags can't be read from here: README).
    if (s.get("enabledPlugins") or {}).get(pid) is not True:
        found.append(f"{pid} not enabled in ~/.claude settings (settings.local.json overrides settings.json)")
    # 3. Exactly one install record, user scope, at the cache path for its own version.
    entries = (inst.get("plugins") or {}).get(pid)
    installed = None
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        found.append(f"{pid}: {0 if not isinstance(entries, list) else len(entries)} install records, want exactly 1")
    else:
        e = entries[0]
        ver = e.get("version")
        expect = t.plugins / "cache" / marketplace.NAME / name / str(ver)
        if e.get("scope") != "user":
            found.append(f"{pid}: scope {e.get('scope')!r}, want 'user'")
        if not isinstance(ver, str) or not ver or "/" in ver or ver in (".", ".."):
            found.append(f"{pid}: version {ver!r} isn't a plain name")
        elif e.get("installPath") != str(expect):
            found.append(f"{pid}: installPath {e.get('installPath')} isn't {expect}")
        else:
            installed = expect
        if e.get("gitCommitSha") != want["commit"]:
            found.append(f"{pid}: records commit {e.get('gitCommitSha')}, pinned {want['commit']} "
                         f"(a first look only; the tree below decides)")
    # 4. The tree, against root's export at the current pin. No component of the path may be a
    #    link: the tree judged must be the tree Claude Code opens.
    ref = t.ref / name / want["commit"]
    if installed is not None:
        p, links = installed, []
        while p != t.home and p != p.parent:
            if p.is_symlink():
                links.append(str(p))
            p = p.parent
        if links:
            found.append(f"{pid}: links on the install path: {' '.join(links)}")
        else:
            try:
                diffs = plugintree.compare(ref, installed)
            except OSError as e:
                return RED, f"couldn't compare {installed} with {ref}: {e}"
            found += [f"{pid}: {d}" for d in diffs[:10]] + (
                [f"{pid}: and {len(diffs) - 10} more differences"] if len(diffs) > 10 else [])
    # 5. Root's side must be root's: the tenant can't write the reference, the marketplace or venv.
    for p in (ref, Path(t.mkt) / marketplace.FILE, Path(t.hearth_py)):
        w = t.writable(p)
        if w:
            found.append(f"writable by this tenant: {' '.join(w)}")
    # 6. The interpreter each plugin starts, as the plugin will see it (pluginConfigs for
    #    Front Desk; the settings env block for Tapestry, read-not-run until a real session).
    opts = ((s.get("pluginConfigs") or {}).get(f"frontdesk@{marketplace.NAME}") or {}).get("options") or {}
    env = {k: v for k, v in {
        "TAPESTRY_PYTHON": (s.get("env") or {}).get("TAPESTRY_PYTHON"),
        "CLAUDE_PLUGIN_OPTION_PYTHON": opts.get("python")}.items() if isinstance(v, str)}
    try:
        problems = [p for p in pins.problems(t.hearth_py, env, t.home) if p.startswith(name + ":")]
    except (OSError, RuntimeError, ValueError) as e:
        return RED, f"couldn't probe the interpreter: {e}"
    found += problems
    if found:
        return RED, "; ".join(found)
    return GREEN, f"{pid} is {want['commit'][:12]}: tree equals root's export, interpreter {t.hearth_py}"


def frontdesk_home(t: Tenant):
    """The Front Desk plugin can't run without its identity directory, made by `frontdesk join`,
    which provision leaves to Will. Unset is PENDING, never green."""
    try:
        s = t.settings()
    except Unreadable as e:
        return RED, f"couldn't look: {e}"
    opts = ((s.get("pluginConfigs") or {}).get(f"frontdesk@{marketplace.NAME}") or {}).get("options") or {}
    home = opts.get("home")
    if home is None:
        return PENDING, (f"frontdesk home unset: Will runs `frontdesk join` as {t.home.name}, then "
                         f"`claude plugin configure frontdesk@{marketplace.NAME}`")
    if not isinstance(home, str) or not os.path.isabs(home):
        return RED, f"frontdesk home is {home!r}, not an absolute path"
    p = Path(home)
    try:
        st = os.lstat(p)
    except OSError as e:
        return RED, f"frontdesk home {p}: {e.strerror}"
    if not stat.S_ISDIR(st.st_mode):
        return RED, f"frontdesk home {p} isn't a directory"
    if st.st_uid != os.getuid():
        return RED, f"frontdesk home {p} isn't owned by this tenant"
    real, h = p.resolve(), t.home.resolve()
    if real == h or not real.is_relative_to(h):
        return RED, f"frontdesk home {p} is outside {t.home}"
    return GREEN, f"frontdesk home {p}"


UNIT_DIR = "/etc/systemd/system"
UNIT = "hearth-host@.service"


def _systemctl_show(unit: str) -> dict:
    out = subprocess.run(["/usr/bin/systemctl", "show", unit, "-p", "ActiveState,MainPID,FragmentPath,User"],
                         capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
    if out.returncode != 0:
        raise Unreadable(f"systemctl show {unit}: rc {out.returncode} {out.stderr.strip()[:200]}")
    return dict(line.split("=", 1) for line in out.stdout.splitlines() if "=" in line)


def host_running(t: Tenant, show=_systemctl_show, proc: str = "/proc", unit_file: str = UNIT_DIR + "/" + UNIT):
    """hearth-host@<tenant> is active, from root's unit file, and its main process runs as this
    tenant from root's venv: what wakes the tenant's conversations (hearth#51)."""
    me = pwd.getpwuid(os.getuid()).pw_name
    unit = f"hearth-host@{me}.service"
    try:
        s = show(unit)
    except (Unreadable, OSError, subprocess.SubprocessError) as e:
        return RED, f"couldn't look: {e}"
    want = unit_file
    if s.get("FragmentPath") != want:
        return RED, f"{unit} comes from {s.get('FragmentPath') or 'nowhere'}, not {want}"
    try:
        st = os.lstat(want)
    except OSError as e:
        return RED, f"{want}: {e.strerror}"
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
        return RED, f"{want} isn't a root-owned file only root can write"
    if s.get("ActiveState") != "active" or s.get("MainPID", "0") == "0":
        return RED, f"{unit} is {s.get('ActiveState')}, not running"
    pid = s["MainPID"]
    try:
        uid = os.stat(f"{proc}/{pid}").st_uid
        argv = Path(f"{proc}/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError as e:
        return RED, f"main pid {pid}: {e.strerror}"
    if uid != os.getuid():
        return RED, f"{unit}'s main process {pid} runs as uid {uid}, not {me}"
    if argv[:4] != [HEARTH_PY.encode(), b"-I", b"-m", b"hearth.host"]:
        return RED, f"{unit}'s main process runs {b' '.join(argv).decode(errors='replace')[:200]}"
    return GREEN, f"{unit} active, pid {pid} as {me}"


def frontdesk_home_path(t: Tenant) -> Path:
    """The configured Front Desk home, for a caller that has had frontdesk_home GREEN."""
    s = t.settings()
    return Path(s["pluginConfigs"][f"frontdesk@{marketplace.NAME}"]["options"]["home"])


def other_plugins(t: Tenant):
    """Plugins enabled in ~/.claude settings (local overriding) from anywhere but Hearth's marketplace also load into the
    tenant's session. v0 reports them and doesn't fail (Ash, 2026-10-15). KNOWN when there are any,
    GREEN when there are none."""
    try:
        s = t.settings()
    except Unreadable as e:
        return RED, f"couldn't look: {e}"
    on = sorted(k for k, v in (s.get("enabledPlugins") or {}).items()
                if v is True and not k.endswith("@" + marketplace.NAME))
    if on:
        return KNOWN, f"enabled outside @{marketplace.NAME}: {' '.join(on)} (reported, not failed, in v0)"
    return GREEN, f"no plugin enabled outside @{marketplace.NAME} in ~/.claude settings"


CHECKS = {"plugin_match": plugin_match, "frontdesk_home": frontdesk_home, "other_plugins": other_plugins,
          "host_running": host_running}


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if not a or a[0] not in CHECKS:
        print(f"usage: python -I -m hearth.tenantcheck {'|'.join(CHECKS)} [arg]")
        return RED
    t = Tenant(Path(pwd.getpwuid(os.getuid()).pw_dir))
    try:
        rc, msg = CHECKS[a[0]](t, *a[1:])
    except TypeError:
        print(f"bad arguments for {a[0]}: {a[1:]}")
        return RED
    print(msg.replace("\n", " "))
    return rc


if __name__ == "__main__":
    sys.exit(main())
