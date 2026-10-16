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
# -I, because this script cd's to the repo root: without isolated mode the cwd
# supplies ./hearth/ and the import succeeds for ANY interpreter whether the
# project is installed or not, which makes the check dead code. With -I it
# discriminates installed from not-installed, and names the common cause in one
# line where a suite failure only says "not green". Same isolation pins.py uses.
if ! "$PY" -I -c 'import hearth.pins' >/dev/null 2>&1; then
  echo "FATAL: $PY cannot import hearth.pins (checked with -I) -- run 'pip install -e .' first." >&2
  exit 2
fi
# Capture the output instead of discarding it: a message that states the
# condition while withholding the reason stops the next person probing. On a
# deps-less venv the discarded tail is "7 failed, 5 passed" with every failure
# reading "not installed in", which names the actual cause.
base_log=$(mktemp)
"$PY" -m pytest -q -p no:cacheprovider tests/ >"$base_log" 2>&1
base_rc=$?
base_out=$(tail -1 "$base_log"); rm -f "$base_log"
if [ "$base_rc" -ne 0 ]; then
  echo "FATAL: the UNARMED suite is not green under PY=$PY, so arm results would be meaningless." >&2
  echo "       pytest: $base_out" >&2
  exit 2
fi
echo "precondition: unarmed suite green ($base_out)"
F=hearth/pins.py
B=$(mktemp); cp -p $F $B
# arm()'s cmp-guarded restore sits on its normal path, so a signal between the mutation and
# the restore leaves $F MUTATED on disk. The next reader then sees a real-looking defect in
# code they are reviewing: measured twice, once from a harness timeout and once from a
# gateway drain SIGKILLing the turn that launched this. SIGKILL cannot be trapped, so this
# covers TERM/INT/HUP and the ordinary exit paths; nothing can cover -9.
restore() {
  if [ -n "${B:-}" ] && [ -f "$B" ]; then
    cp -p "$B" "$F"
    if cmp -s "$B" "$F"; then
      rm -f "$B"
    else
      echo "RESTORE FAILED $F: backup kept at $B" >&2
      return 1
    fi
  fi
  return 0
}
trap restore EXIT
trap 'trap - EXIT; if restore; then echo "INTERRUPTED: restored $F" >&2; else echo "INTERRUPTED: $F NOT restored" >&2; fi; exit 130' TERM INT HUP
red=0; bad=0
arm() {
  local name="$1" old="$2" new="$3"
  local _g=0 _n=0 _t
  # A green arm is re-run (#99): one green is weak evidence and must not look
  # identical to a repeated one. Red on any trial means the guard is live.
  for _t in 1 2 3; do
    $PY - "$F" "$old" "$new" <<'EOF' || { echo "ARM $name: ANCHOR NOT FOUND, nothing mutated"; cp -p "$B" "$F"; cmp -s "$B" "$F" || echo "RESTORE FAILED"; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
assert s.count(old) == 1, f"anchor not unique: {old!r}"
want = s.replace(old, new)
with open(p, "w") as fh: fh.write(want)
assert open(p).read() == want, f"mutation did not land on disk: {p}"
EOF
    L=$(mktemp); timeout 300 $PY -m pytest -q -p no:cacheprovider tests/test_pins.py >"$L" 2>&1; prc=$?
    out=$(tail -1 "$L"); rm -f "$L"
    cp -p $B $F; cmp -s $B $F || { echo "RESTORE FAILED"; exit 2; }
    _n=$_t
    [ $prc = 1 ] && break
    [ $prc = 0 ] || break
    _g=$((_g+1))
  done
  if [ $prc = 1 ] && [ $_g = 0 ]; then echo "ARM $name: RED ($out)"; red=$((red+1));
  elif [ $prc = 1 ]; then echo "ARM $name: FLAKY, $_g green of $_n trials ($out)"; bad=$((bad+1));
  elif [ $prc = 0 ]; then echo "ARM $name: GREEN ($_g/$_n) ($out)"; bad=$((bad+1));
  else echo "ARM $name: NOT A RESULT, pytest rc=$prc ($out)"; bad=$((bad+1)); fi
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
echo "arms red: $red, arms bad: $bad"

# A GREEN arm means the mutation was NOT caught: the guard it probes has
# stopped working. $bad was counted and printed but never consulted, so the
# script exited 0 while reporting the exact inverse of a passing run. The
# summary a reader greps and the status CI reads must agree with each other.
if [ "$bad" -ne 0 ]; then
  echo "FATAL: $bad arm(s) did not come back cleanly RED -- see the GREEN, FLAKY and NOT A RESULT" >&2
  echo "lines above. A GREEN arm means the mutation was not caught, so the guard it probes is" >&2
  echo "not working; FLAKY and NOT A RESULT mean the arm produced no trustworthy verdict." >&2
  exit 1
fi
