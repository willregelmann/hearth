#!/bin/bash
# Mutation arms for the board (docs/interfaces/BOARD.md, hearth/board.py): each breaks one guarantee
# and must turn a named test in tests/test_board.py red. cmp-guarded: the source is restored and
# checked byte-identical after every arm. An anchor that isn't found exactly once is exit 3.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-python3}
F=hearth/board.py
B=$(mktemp); cp -p $F $B
trap 'cp -p $B $F; cmp -s $B $F || echo "RESTORE FAILED (trap)"; rm -f $B' EXIT INT TERM
T="-q -p no:cacheprovider tests/test_board.py"
$PY -m pytest $T >/dev/null 2>&1 || { echo "not green unarmed"; exit 2; }
echo "unarmed: green"
red=0; bad=0
arm() {
  local name="$1" k="$2" old="$3" new="$4"
  $PY - "$F" "$old" "$new" <<'EOF' || { echo "ANCHOR NOT FOUND: $name"; cp -p $B $F; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
if s.count(old) != 1: sys.exit(1)
open(p, "w").write(s.replace(old, new))
EOF
  L=$(mktemp); timeout 120 $PY -m pytest $T -k "$k" >"$L" 2>&1; prc=$?
  out=$(tail -1 "$L"); rm -f "$L"
  cp -p $B $F; cmp -s $B $F || { echo "RESTORE FAILED"; exit 2; }
  if [ $prc = 1 ]; then echo "ARM $name: RED ($out)"; red=$((red+1));
  else echo "ARM $name: NOT RED, pytest rc=$prc ($out)"; bad=$((bad+1)); fi
}
arm "agents found under /run, not the declared ones" "every_declared_agent" \
  "        for f in sorted(self.registry.iterdir()):" "        for f in sorted(self.run.iterdir()):"
arm "an agent that can't be read is left out" "every_declared_agent" \
  "            entry[\"unreachable\"] = f\"{sock}: {exc.code().name.lower()}: {exc.details()}\"
            return entry" \
  "            return None"
arm "a board that never read looks fresh" "own_freshness" \
  "        snap[\"stale\"] = snap[\"age_s\"] is None or snap[\"age_s\"] > STALE_AFTER * self.interval_s" \
  "        snap[\"stale\"] = snap[\"age_s\"] is not None and snap[\"age_s\"] > STALE_AFTER * self.interval_s"
arm "freshness by the last request, not the last read" "own_freshness" \
  "        snap[\"age_s\"] = None if snap[\"checked_at\"] is None else round(now - snap[\"checked_at\"], 1)" \
  "        snap[\"age_s\"] = None if snap[\"checked_at\"] is None else 0.0"
arm "the board takes writes" "never_starts_a_turn" \
  "        do_PUT = do_PATCH = do_DELETE = _refuse" "        do_PUT = do_PATCH = do_DELETE = do_GET"
arm "the board takes a POST that isn't the operator talking" "never_starts_a_turn" \
  "                return self._refuse()" "                return self.do_GET()"
arm "the board runs as an agent" "neither_root_nor_any_agent" \
  "            if agent_uid == uid:" "            if False:"
arm "the board serves from a directory anyone can enter" "only_the_operator" \
  "        status.private_dir(sock.parent)" "        pass"
arm "an agent's report is filed under the name it reports" "cant_change_what_the_board_shows" \
  "        r.pop(\"agent\", None)   # the registry names the agent, not the agent
        entry.update(reachable=True, status=r)" \
  "        entry.update(reachable=True, status=r, name=r.get(\"agent\") or name)"
echo "arms red: $red, arms bad: $bad"
[ $bad = 0 ]
