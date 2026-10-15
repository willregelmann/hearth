#!/bin/bash
# Mutation arms for hearth/pins.py: each removes one guard and must turn a named test red.
# cmp-guarded: the source is restored and checked byte-identical after every arm.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}

# An arm that goes red because the interpreter does not exist is
# indistinguishable from an arm that goes red because the guard matters:
# with a missing PY every arm reports RED and the summary line is
# byte-identical to a full pass, while the script still exits 0 -- so no
# CI could catch it either. Require a usable interpreter AND a green
# unarmed suite before arming anything, so a pass is the baseline.
if ! "$PY" -c 'import sys' >/dev/null 2>&1; then
  echo "FATAL: PY=$PY is not a usable interpreter. Set PY to your venv python." >&2
  exit 2
fi
if ! "$PY" -m pytest -q tests/ >/dev/null 2>&1; then
  echo "FATAL: the UNARMED suite is not green under PY=$PY, so arm results would be meaningless." >&2
  exit 2
fi
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
