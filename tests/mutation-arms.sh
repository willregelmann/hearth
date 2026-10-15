#!/bin/bash
# Mutation arms for hearth/pins.py: each removes one guard and must turn a named test red.
# cmp-guarded: the source is restored and checked byte-identical after every arm.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
# Three preconditions, because the summary line is identical whether every arm
# proved its guard or the suite never ran. With $PY absent, every arm dies on
# "No such file or directory", the loop greps the output for "failed", the
# shell's own error supplies that word, and the script prints the IDEAL result.
command -v "$PY" >/dev/null 2>&1 || [ -x "$PY" ] || {
  echo "FATAL: PY=$PY is not executable. Point PY at the venv python with the project installed." >&2
  exit 3
}
"$PY" -c 'import hearth.pins' 2>/dev/null || {
  echo "FATAL: $PY cannot import hearth.pins -- run 'pip install -e .' first." >&2
  exit 3
}
# Importing is NOT sufficient: an editable install leaves the source dir on
# sys.path for any interpreter run inside the tree, so a venv missing the pinned
# DEPS imports hearth.pins fine, then fails every test on "not installed in",
# which the loop reads as RED and again summarises as a perfect score. Requiring
# the UNARMED suite to be green is the only precondition under which a later red
# is attributable to the arm rather than to the environment.
base_out=$(timeout 300 "$PY" -m pytest -q -p no:cacheprovider tests/test_pins.py 2>&1 | tail -1)
case "$base_out" in
  *failed*|*error*)
    echo "FATAL: the suite is not green BEFORE any arm is applied: $base_out" >&2
    echo "       Fix the environment -- the arms measure nothing until this passes." >&2
    exit 3 ;;
esac
echo "precondition: unarmed suite green ($base_out)"
F=hearth/pins.py
B=$(mktemp); cp -p $F $B
red=0; bad=0
arm() {
  local name="$1" old="$2" new="$3"
  $PY - "$F" "$old" "$new" <<'EOF'
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
assert s.count(old) == 1, f"anchor not unique: {old!r}"; open(p, "w").write(s.replace(old, new))
EOF
  out=$(timeout 300 $PY -m pytest -q -p no:cacheprovider tests/test_pins.py 2>&1 | tail -1)
  cp -p $B $F; cmp -s $B $F || { echo "RESTORE FAILED"; exit 2; }
  if echo "$out" | grep -q failed; then echo "ARM $name: RED ($out)"; red=$((red+1)); else echo "ARM $name: GREEN ($out)"; bad=$((bad+1)); fi
}
arm "no interpreter check (same commit in another venv passes)" \
  '        if got["prefix"] != hearth_prefix:' '        if False:'
arm "no commit check" \
  "commit != want[plugin][\"commit\"]" "False"
arm "a PATH python is trusted" \
  "        if not os.path.isabs(python):" "        if False:"
arm "a branch or tag counts as a pin" \
  "(?P<commit>[0-9a-f]{40})" "(?P<commit>[^\\s]+)"
arm "probe the test's own interpreter, not the plugin's" \
  "        got = installed(python, [plugin])" "        got = installed(hearth_python, [plugin])"
arm "frontdesk ignores the plugin option" \
  ' or env.get("CLAUDE_PLUGIN_OPTION_PYTHON")' ""
arm "an empty or partial pin list is accepted" \
  "    if missing:" "    if False:"
rm -f $B
echo "arms red: $red, arms green: $bad"
