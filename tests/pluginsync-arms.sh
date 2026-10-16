#!/bin/bash
# Mutation arms for hearth/pluginsync.py: each breaks one guarantee and must turn
# tests/test_pluginsync.py red. cmp-guarded; an anchor not found exactly once is exit 3.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
F=hearth/pluginsync.py
B=$(mktemp); cp -p $F $B
trap 'cp -p $B $F; cmp -s $B $F || echo "RESTORE FAILED (trap)"; rm -f $B' EXIT INT TERM
T="$PY -m pytest -q -p no:cacheprovider tests/test_pluginsync.py"
base=$($T 2>&1 | tail -1)
case "$base" in *failed*|*error*|"") echo "not green unarmed: $base"; exit 2;; esac
red=0; bad=0
arm() {
  $PY - "$F" "$2" "$3" <<'EOF' || { echo "ANCHOR NOT FOUND: $1"; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
if s.count(old) != 1: sys.exit(1)
open(p, "w").write(s.replace(old, new))
EOF
  out=$($T 2>&1 | tail -1)
  cp -p $B $F; cmp -s $B $F || { echo "RESTORE FAILED"; exit 2; }
  if echo "$out" | grep -qE 'failed|error'; then echo "ARM $1: RED ($out)"; red=$((red+1)); else echo "ARM $1: GREEN ($out)"; bad=$((bad+1)); fi
}
arm "a plain repeat install (what exits 0 and moves nothing)" \
  '        run_claude(claude, "uninstall", pid)' '        pass'
arm "options not put back" \
  '        if saved:
            run_claude(claude, "configure", pid, "--values-stdin", stdin=json.dumps(saved))' '        pass'
arm "options not checked after" \
  '    if back != saved:' '    if False:'
arm "the tree not checked after" \
  '    after = installed_diffs(t, name)' '    after = []'
arm "reinstall even when the tree equals the pin" \
  '    if not diffs:
        return 0' '    if False:
        return 0'
arm "reinstall under a live claude" \
  '    if running:' '    if False:'
arm "an unreadable record read as equal" \
  '        return [f"couldn'"'"'t read the install record: {e}"]' '        return []'
arm "live_claude: any binary counts" \
  '        if any(exe.startswith(x.rstrip("/") + "/") for x in dirs):' '        if True:'
echo "arms red: $red, bad: $bad"
[ $bad = 0 ]
