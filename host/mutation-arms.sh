#!/bin/bash
# Mutation arms for hearth/host.py: each breaks one guarantee and must turn a named test red.
# cmp-guarded: the source is restored and checked byte-identical after every arm. An anchor that
# isn't found exactly once is exit 3, never an arm.
set -u
cd "$(dirname "$0")/.."
export FRONTDESK_TEST_DESK=http://127.0.0.1:8018
PY=${PY:-python3}
F=hearth/host.py
# The unarmed suite must be green before any arm runs, scored on pytest's own rc rather
# than its prose (#98). Without this, a tree left mutated by a killed run -- SIGKILL
# defeats the trap (#93) -- is adopted as the pristine backup at $B, so every arm still
# reddens, the headline reads 6 red 0 green, and a real defect is preserved and reported
# as full coverage.
timeout 600 $PY -m pytest -q -p no:cacheprovider -c host/pytest.ini host/test_host.py >/dev/null 2>&1 || { echo "FATAL: the UNARMED suite is not green under PY=$PY" >&2; exit 2; }
B=$(mktemp); cp -p $F $B
trap 'cp -p $B $F; cmp -s $B $F || echo "RESTORE FAILED (trap)"; rm -f $B' EXIT INT TERM
red=0; bad=0
arm() {
  local name="$1" old="$2" new="$3"
  local _g=0 _n=0 _t
  # A green arm is re-run (#99): one green is weak evidence and must not look
  # identical to a repeated one. Red on any trial means the guard is live.
  for _t in 1 2 3; do
    $PY - "$F" "$old" "$new" <<'EOF' || { echo "ANCHOR NOT FOUND: $name"; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
if s.count(old) != 1: sys.exit(1)
open(p, "w").write(s.replace(old, new))
EOF
    L=$(mktemp); timeout 200 $PY -m pytest -q -p no:cacheprovider -c host/pytest.ini host/test_host.py >"$L" 2>&1; prc=$?
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
arm "today's host: only the open session (no turn for a closed one)" \
  "        task = asyncio.get_running_loop().create_task(self._turn(conversation))" \
  "        return
        task = asyncio.get_running_loop().create_task(self._turn(conversation))"
arm "commit even when the turn failed" \
  "                if rc != 0:" "                if False:"
arm "no per-conversation lock" \
  "        async with self._locks.setdefault(conversation, asyncio.Lock()):" \
  "        async with __import__('contextlib').AsyncExitStack():"
arm "one global lock (conversations serialised)" \
  "self._locks.setdefault(conversation, asyncio.Lock())" "self._locks.setdefault('ALL', asyncio.Lock())"
arm "wake runs the turn inline (blocks the desk)" \
  "        task = asyncio.get_running_loop().create_task(self._turn(conversation))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)" \
  "        await self._turn(conversation)"
arm "never commits (arrivals left pending)" \
  "                await self.desk.commit(conversation, also=refs)" \
  "                return"
echo "arms red: $red, arms bad: $bad"
[ $bad = 0 ]
