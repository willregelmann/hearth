#!/bin/bash
# Mutation arms for hearth/host.py's service (hearth#51): each breaks one guarantee and must turn a
# named test in host/test_serve.py red. cmp-guarded: the source is restored and checked
# byte-identical after every arm. An anchor that isn't found exactly once is exit 3, never an arm.
set -u
cd "$(dirname "$0")/.."
export FRONTDESK_TEST_DESK=http://127.0.0.1:8018
PY=${PY:-python3}
F=hearth/host.py
B=$(mktemp); cp -p $F $B
trap 'cp -p $B $F; cmp -s $B $F || echo "RESTORE FAILED (trap)"; rm -f $B' EXIT INT TERM
# Scored on pytest's own rc, not its prose: piping to tail discards the exit status, and
# "1 error" from an unparseable tree is not distinguishable from a test failure (#98).
BL=$(mktemp); timeout 600 $PY -m pytest -q -p no:cacheprovider -c host/pytest.ini host/test_serve.py >"$BL" 2>&1; brc=$?
base=$(tail -1 "$BL"); rm -f "$BL"
[ $brc = 0 ] || { echo "not green unarmed (pytest rc=$brc): $base"; exit 2; }
echo "unarmed: $base"
red=0; bad=0
arm() {
  local name="$1" k="$2" old="$3" new="$4"
  local _g=0 _n=0 _t
  # A green arm is re-run (#99): one green is weak evidence and must not look
  # identical to a repeated one. Red on any trial means the guard is live.
  for _t in 1 2 3; do
    $PY - "$F" "$old" "$new" <<'EOF' || { echo "ANCHOR NOT FOUND: $name"; cp -p $B $F; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
if s.count(old) != 1: sys.exit(1)
open(p, "w").write(s.replace(old, new))
EOF
    L=$(mktemp); timeout 300 $PY -m pytest -q -p no:cacheprovider -c host/pytest.ini host/test_serve.py -k "$k" >"$L" 2>&1; prc=$?
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
arm "#55's shape: one desk on the host's own seat, no seat per conversation" "session_s_alarm" \
  "            want = {s for s in want if not host.is_attended(s)}" "            want = set()"
arm "serve claims for a seat a live session has open" "open_elsewhere" \
  "            want = {s for s in want if not host.is_attended(s)}" "            pass"
arm "a turn starts while the session is open" "host_a_wake_for_an_open_session" \
  "                if self.is_attended(conversation):" "                if False:"
arm "arrivals not marked shown during the turn" "own_server_does_not_wake" \
  "                self.desk.mark_shown(refs)" "                pass"
arm "a failed turn leaves them shown" "failed_turn" \
  "                        if row is not None and row[\"state\"] == \"shown\":" "                        if False:"
arm "one turn per wake (nothing taken mid-turn runs)" "host_what_the_turn" \
  "                await self.desk.commit(conversation, also=refs)" "                await self.desk.commit(conversation, also=refs)
                return"
arm "deferred is never retried" "host_a_wake_for_an_open_session" \
  "                self.deferred.discard(conversation)
                await self.wake(conversation)" "                pass"
arm "the exact current binary only (B: a session on the old version)" "before_an_update" \
  '        if exe is None or not any(exe.startswith(d.rstrip("/") + "/") for d in dirs):' \
  '        if exe is None or os.path.basename(exe) != "2.1.300":'
arm "an exact path compared (C: a binary deleted under it)" "deleted_under_it" \
  '        if exe is None or not any(exe.startswith(d.rstrip("/") + "/") for d in dirs):' \
  '        if exe is None or not os.path.exists(exe):'
arm "a prefix match without the separator" "sibling_dir_with_the_same_prefix" \
  'exe.startswith(d.rstrip("/") + "/")' 'exe.startswith(d.rstrip("/"))'
arm "any process counts as claude" "isn_t_claude" \
  '        if exe is None or not any(exe.startswith(d.rstrip("/") + "/") for d in dirs):' '        if exe is None:'
arm "our own turn counts as attended" "own_turn" \
  '        if pid == me or me in sessions.ancestors(pid):' '        if pid == me:'
arm "root's store not a claude dir" "default_dirs" \
  ', "/opt/hearth/claude")' ')'
echo "arms red: $red, arms bad: $bad"
[ $bad = 0 ]
