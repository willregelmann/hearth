"""A plugin's installed tree, judged against the tree at its pin (docs/decisions/0009).

Claude Code records the commit it installed (gitCommitSha in installed_plugins.json), but that file
is in the tenant's home and the tenant can edit it. So the verdict compares the files themselves:
the tree Claude Code will load, against the tree git holds at the pinned commit, exported by root.

    export(url, commit, subdir, dest)   root, at provision: the reference tree, read-only
    compare(expected, installed)        the tenant, at check: every difference, as a sentence

What counts as a difference: an entry present on one side only, a different type (file, directory,
link, anything else), different bytes, a different owner-execute bit, or a different link target.
Exactly one entry is allowed beyond the export: an empty directory `.in_use` at the top, which Claude
Code creates in the install directory (Ash, measured on 2.1.288 and 2.1.300). Nothing else is
excused, dotfiles included, so a planted `.hook` is a difference.

The installed side belongs to the judged party, so nothing on it is trusted: links are never
followed, nothing but a regular file is ever opened, files are opened non-blocking and checked on
the open descriptor, and no file is read past the size of its counterpart in the export.
"""
import hashlib
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ALLOWED_EXTRA = ".in_use"
_CHUNK = 1 << 16


def export(url: str, commit: str, subdir: str, dest: Path) -> None:
    """Write the tree at ``commit`` (or its ``subdir``) into ``dest``, which must not exist yet.
    A shallow fetch of the one commit, then `git archive`, so the result is exactly git's tree."""
    dest = Path(dest)
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"{dest} already exists")
    with tempfile.TemporaryDirectory() as tmp:
        git = ["git", "-C", tmp, "-c", "advice.detachedHead=false"]
        subprocess.run(["git", "init", "-q", tmp], check=True)
        subprocess.run(git + ["fetch", "-q", "--depth", "1", url, commit], check=True)
        tree = f"{commit}:{subdir}" if subdir else commit
        part = dest.with_name(dest.name + ".part")
        part.mkdir(parents=True)
        archive = subprocess.Popen(git + ["archive", "--format=tar", tree], stdout=subprocess.PIPE)
        subprocess.run(["tar", "-x", "-C", str(part), "-f", "-"], stdin=archive.stdout, check=True)
        if archive.wait() != 0:
            raise RuntimeError(f"git archive {tree} failed")
        part.rename(dest)       # a failed export never looks like a finished one


def _kind(st) -> str:
    m = st.st_mode
    return ("file" if stat.S_ISREG(m) else "dir" if stat.S_ISDIR(m) else
            "link" if stat.S_ISLNK(m) else "other")


def _digest(path: Path, limit: int):
    """sha256 of a regular file, reading at most ``limit`` + 1 bytes. None if it isn't a regular
    file once opened (swapped after the lstat)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            return None
        h, left = hashlib.sha256(), limit + 1
        while left > 0:
            b = f.read(min(_CHUNK, left))
            if not b:
                break
            h.update(b)
            left -= len(b)
        return h.hexdigest()


def _entries(root: Path) -> dict:
    """{relative path: lstat} for everything under root, links not followed. Errors are raised:
    a place that can't be listed is a reason to say so, never a reason to report nothing."""
    out = {}

    def walk(d: Path, rel: str):
        with os.scandir(d) as it:
            for e in it:
                r = f"{rel}/{e.name}" if rel else e.name
                st = os.lstat(e.path)
                out[r] = st
                if stat.S_ISDIR(st.st_mode):
                    walk(Path(e.path), r)
    walk(root, "")
    return out


def compare(expected: Path, installed: Path) -> list[str]:
    """Every difference between the export and the installed tree. Empty means identical."""
    expected, installed = Path(expected), Path(installed)
    st = os.lstat(installed)
    if not stat.S_ISDIR(st.st_mode):
        return [f"{installed} is a {_kind(st)}, not a directory"]
    want, have = _entries(expected), _entries(installed)
    found = []
    extra = have.pop(ALLOWED_EXTRA, None)
    if extra is not None:
        if not stat.S_ISDIR(extra.st_mode):
            found.append(f"{ALLOWED_EXTRA}: a {_kind(extra)}, only an empty directory is expected")
        elif any(p.startswith(ALLOWED_EXTRA + "/") for p in have):
            found.append(f"{ALLOWED_EXTRA}: not empty")
        for p in [p for p in have if p.startswith(ALLOWED_EXTRA + "/")]:
            del have[p]
    for p in sorted(set(want) | set(have)):
        w, h = want.get(p), have.get(p)
        if h is None:
            found.append(f"{p}: missing")
            continue
        if w is None:
            found.append(f"{p}: not in the pinned tree")
            continue
        if _kind(w) != _kind(h):
            found.append(f"{p}: a {_kind(h)}, the pin has a {_kind(w)}")
            continue
        if _kind(w) == "link":
            if os.readlink(expected / p) != os.readlink(installed / p):
                found.append(f"{p}: link target differs")
        elif _kind(w) == "file":
            if (w.st_mode & stat.S_IXUSR) != (h.st_mode & stat.S_IXUSR):
                found.append(f"{p}: execute bit {'set' if h.st_mode & stat.S_IXUSR else 'clear'}, "
                             f"the pin has it {'set' if w.st_mode & stat.S_IXUSR else 'clear'}")
            if w.st_size != h.st_size:
                found.append(f"{p}: {h.st_size} bytes, the pin has {w.st_size}")
            elif _digest(installed / p, w.st_size) != _digest(expected / p, w.st_size):
                found.append(f"{p}: contents differ")
    return found


def main(argv=None) -> int:
    """compare EXPECTED INSTALLED: prints each difference; exit 0 identical, 1 different,
    2 couldn't look."""
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) != 3 or a[0] != "compare":
        print("usage: python -m hearth.plugintree compare EXPECTED INSTALLED", file=sys.stderr)
        return 2
    try:
        found = compare(Path(a[1]), Path(a[2]))
    except OSError as e:
        print(f"couldn't look: {e}")
        return 2
    for f in found:
        print(f)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
