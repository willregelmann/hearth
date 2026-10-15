#!/bin/bash
# Mutation arms for hearth/plugintree.py: each removes one guard and must turn a test red.
# cmp-guarded: the source is restored and checked byte-identical after every arm.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
# Same baseline as tests/mutation-arms.sh (#66): a missing interpreter or a red unarmed suite turns
# every arm "red" for the wrong reason.
"$PY" -c 'import sys' >/dev/null 2>&1 || { echo "FATAL: PY=$PY is not a usable interpreter" >&2; exit 2; }
"$PY" -m pytest -q -p no:cacheprovider tests/ >/dev/null 2>&1 || { echo "FATAL: the UNARMED suite is not green under PY=$PY" >&2; exit 2; }
F=hearth/plugintree.py
B=$(mktemp); cp -p $F $B
# arm()'s cmp-guarded restore sits on its normal path, so a signal between the mutation and
# the restore leaves $F MUTATED on disk, where it reads as a real defect in reviewed code.
# SIGKILL cannot be trapped; this covers TERM/INT/HUP and the ordinary exit paths.
restore() {
  if [ -n "${B:-}" ] && [ -f "$B" ]; then cp -p "$B" "$F"; rm -f "$B"; fi
  return 0
}
trap restore EXIT
trap 'restore; echo "INTERRUPTED: restored $F; re-run before trusting any arm result." >&2; exit 130' TERM INT HUP
red=0; bad=0
arm() {
  local name="$1" old="$2" new="$3"
  $PY - "$F" "$old" "$new" <<'EOF'
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
assert s.count(old) == 1, f"anchor not unique: {old!r}"; open(p, "w").write(s.replace(old, new))
EOF
  out=$(timeout 120 $PY -m pytest -q -p no:cacheprovider tests/test_plugintree.py 2>&1 | tail -1)
  cp -p $B $F; cmp -s $B $F || { echo "RESTORE FAILED"; exit 2; }
  if echo "$out" | grep -qE "failed|error"; then echo "ARM $name: RED ($out)"; red=$((red+1)); else echo "ARM $name: GREEN ($out)"; bad=$((bad+1)); fi
}
arm "excuse every dotfile" \
  '    extra = have.pop(ALLOWED_EXTRA, None)' \
  '    [have.pop(p) for p in [p for p in have if p.rsplit("/", 1)[-1].startswith(".") and not p.startswith(".claude-plugin")]]
    extra = have.pop(ALLOWED_EXTRA, None)'
arm "excuse .in_use at any depth" \
  '    extra = have.pop(ALLOWED_EXTRA, None)' \
  '    [have.pop(p) for p in [p for p in have if p.endswith("/" + ALLOWED_EXTRA)]]
    extra = have.pop(ALLOWED_EXTRA, None)'
arm "accept a non-empty .in_use" \
  '        elif any(p.startswith(ALLOWED_EXTRA + "/") for p in have):' '        elif False:'
arm "accept .in_use as a file" \
  '        if not stat.S_ISDIR(extra.st_mode):' '        if False:'
arm "ignore extra entries" \
  '            found.append(f"{p}: not in the pinned tree")' '            pass'
arm "ignore the execute bit" \
  '            if (w.st_mode & stat.S_IXUSR) != (h.st_mode & stat.S_IXUSR):' '            if False:'
arm "size only, no contents" \
  '            elif _digest(installed / p, w.st_size) != _digest(expected / p, w.st_size):' '            elif False:'
arm "follow links (stat, not lstat)" \
  '                st = os.lstat(e.path)' '                st = os.stat(e.path)'
arm "open files blocking" \
  '        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)' '        fd = os.open(path, os.O_RDONLY)'
arm "follow a linked installed root" \
  '    st = os.lstat(installed)' '    st = os.stat(installed)'
arm "a digest of a non-file is a digest" \
  '        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            return None' '        pass'
rm -f $B
echo "arms red: $red, arms green: $bad"; [ "$bad" = 0 ]
