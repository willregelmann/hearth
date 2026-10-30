#!/bin/bash
# Mutation arms for the agent's status (docs/interfaces/STATUS.md, hearth/status.py): each breaks
# one guarantee and must turn a named test in host/test_status.py red. cmp-guarded: every file
# is restored and checked byte-identical after every arm. An anchor that isn't found exactly
# once is exit 3, never an arm.
set -u
cd "$(dirname "$0")/.."
export FRONTDESK_TEST_DESK=${FRONTDESK_TEST_DESK:-http://127.0.0.1:8018}
PY=${PY:-python3}
FILES="hearth/status.py hearth/host.py"
B=$(mktemp -d)
for f in $FILES; do cp -p $f $B/$(basename $f); done
restore() { for f in $FILES; do cp -p $B/$(basename $f) $f; cmp -s $B/$(basename $f) $f || { echo "RESTORE FAILED: $f"; return 1; }; done; }
trap 'restore; rm -rf $B' EXIT INT TERM
T="-q -p no:cacheprovider -c host/pytest.ini host/test_status.py"
timeout 600 $PY -m pytest $T >/dev/null 2>&1; brc=$?
[ $brc = 0 ] || { echo "not green unarmed (pytest rc=$brc)"; exit 2; }
echo "unarmed: green"
red=0; bad=0
arm() {
  local name="$1" file="$2" k="$3" old="$4" new="$5"
  $PY - "$file" "$old" "$new" <<'EOF' || { echo "ANCHOR NOT FOUND: $name"; restore; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
if s.count(old) != 1: sys.exit(1)
open(p, "w").write(s.replace(old, new))
EOF
  L=$(mktemp); timeout 300 $PY -m pytest $T -k "$k" >"$L" 2>&1; prc=$?
  out=$(tail -1 "$L"); rm -f "$L"
  restore || exit 2
  if [ $prc = 1 ]; then echo "ARM $name: RED ($out)"; red=$((red+1));
  else echo "ARM $name: NOT RED, pytest rc=$prc ($out)"; bad=$((bad+1)); fi
}
arm "reading the status refreshes the host (wakes what's pending)" hearth/status.py "never_starts_a_turn" \
  "    async def Get(self, request, context) -> pb.Report:
        return self.report()" \
  "    async def Get(self, request, context) -> pb.Report:
        await self.host.recover()
        return self.report()"
arm "a pending wake shows a preview of what's waiting" hearth/status.py "never_shows_what_was_said" \
  "                    waiting[channel[\"conversation\"]] = waiting.get(channel[\"conversation\"], 0) + n" \
  "                    waiting[channel[\"conversation\"] + \" \" + \" \".join(json.loads(x[\"arrival\"]).get(\"text\", \"\") for x in ledger.pending(channel[\"handle\"]))] = n"
arm "a status that can't be served stops the host" hearth/host.py "no_other_agent_can_read" \
  "        except Exception as exc:
            logger.error(\"status not served: %s\", exc)" \
  "        except ZeroDivisionError as exc:
            logger.error(\"status not served: %s\", exc)"
arm "a directory every user can enter is served" hearth/status.py "no_other_agent_can_read" \
  "    if st.st_mode & stat.S_IRWXO:
        raise" "    if False:
        raise"
echo "arms red: $red, arms bad: $bad"
[ $bad = 0 ]
