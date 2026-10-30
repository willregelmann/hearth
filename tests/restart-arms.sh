#!/bin/bash
# Mutation arms for Restart (docs/interfaces/BOARD.md; hearth/board.py, hearth/host.py,
# home/hearth-board.rules): each breaks one guarantee and must turn a named test red. The host's
# test needs a desk (FRONTDESK_TEST_DESK). cmp-guarded: every file is restored and checked
# byte-identical after every arm. An anchor that isn't found exactly once is exit 3.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-python3}
FILES="hearth/board.py hearth/host.py home/hearth-board.rules"
B=$(mktemp -d); for f in $FILES; do cp -p $f $B/$(basename $f); done
restore() { for f in $FILES; do cp -p $B/$(basename $f) $f; cmp -s $B/$(basename $f) $f || echo "RESTORE FAILED: $f"; done; }
trap 'restore; rm -rf $B' EXIT INT TERM
BOARD="tests/test_board.py tests/test_polkit_rule.py"
HOST="host/test_serve.py"
for t in "$BOARD" "$HOST"; do
  (cd $( [ "$t" = "$HOST" ] && echo host || echo . ) && $PY -m pytest -q -p no:cacheprovider ${t//host\//} -k "restart or polkit or only_the_operator" >/dev/null 2>&1) \
    || { echo "not green unarmed: $t"; exit 2; }
done
echo "unarmed: green"
red=0; bad=0
arm() {
  local name="$1" f="$2" t="$3" k="$4" old="$5" new="$6"
  $PY - "$f" "$old" "$new" <<'PYEOF' || { echo "ANCHOR NOT FOUND: $name"; restore; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
if s.count(old) != 1: sys.exit(1)
open(p, "w").write(s.replace(old, new))
PYEOF
  L=$(mktemp)
  if [ "$t" = host ]; then (cd host && timeout 300 $PY -m pytest -q -p no:cacheprovider test_serve.py -k "$k" >"$L" 2>&1); prc=$?
  else timeout 300 $PY -m pytest -q -p no:cacheprovider $BOARD -k "$k" >"$L" 2>&1; prc=$?; fi
  out=$(tail -1 "$L"); rm -f "$L"
  restore
  if [ $prc = 1 ]; then echo "ARM $name: RED ($out)"; red=$((red+1));
  else echo "ARM $name: NOT RED, pytest rc=$prc ($out)"; bad=$((bad+1)); fi
}
arm "the board restarts any name" hearth/board.py board "never_stops_another" \
  "        if name not in self.names():
            raise KeyError(name)" "        pass"
arm "a failed restart is shown as done" hearth/board.py board "fails_says_so" \
  "        self._restart(name)
        self.restarts[name] = self.clock()" \
  "        self.restarts[name] = self.clock()
        self._restart(name)"
arm "another site's page restarts through the operator's browser" hearth/board.py board "only_the_operator_can_restart" \
  "            if self.headers.get(\"Sec-Fetch-Site\", \"same-origin\") != \"same-origin\" \\
                    or self.headers.get_content_type() != \"application/json\":" \
  "            if self.headers.get_content_type() != \"application/json\":"
arm "polkit lets the board do anything to an agent's host" home/hearth-board.rules board "polkit" \
  "      action.lookup(\"verb\") == \"restart\" &&" ""
arm "polkit lets the board restart any unit named like a host" home/hearth-board.rules board "polkit" \
  "/^hearth-host@[a-z0-9_-]+\\.service\$/" "/hearth-host@[a-z0-9_-]+\\.service/"
arm "polkit lets anyone restart an agent" home/hearth-board.rules board "polkit" \
  "      subject.user == \"hearth-board\" &&" ""
arm "a restart isn't shown" hearth/host.py host "restart_is_shown" \
  "        if before is not None:
            stamp" "        if False:
            stamp"
arm "a restart is shown once, even if that turn failed" hearth/host.py host "restart_is_shown" \
  "                notice = self.restarted" "                notice, self.restarted = self.restarted, None"
arm "a first start is shown as a restart" hearth/host.py host "restart_is_shown" \
  "        except FileNotFoundError:
            before = None" "        except FileNotFoundError:
            before = 0.0"
arm "a restart is shown at every turn" hearth/host.py host "restart_is_shown" \
  "                if notice is not None and self.restarted == notice:
                    self.restarted = None" "                pass"
echo "arms red: $red, arms bad: $bad"
[ $bad = 0 ]
