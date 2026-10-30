#!/bin/bash
# Mutation arms for Talk (docs/interfaces/BOARD.md; hearth/talk.py, hearth/board.py): each breaks one
# guarantee and must turn a named test in tests/test_talk.py red. Needs a desk (FRONTDESK_TEST_DESK).
# cmp-guarded: every file is restored and checked byte-identical after every arm. An anchor that
# isn't found exactly once is exit 3.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-python3}
FILES="hearth/talk.py hearth/board.py"
B=$(mktemp -d); for f in $FILES; do cp -p $f $B/$(basename $f); done
restore() { for f in $FILES; do cp -p $B/$(basename $f) $f; cmp -s $B/$(basename $f) $f || echo "RESTORE FAILED: $f"; done; }
trap 'restore; rm -rf $B' EXIT INT TERM
T="-q -p no:cacheprovider tests/test_talk.py"
$PY -m pytest $T >/dev/null 2>&1 || { echo "not green unarmed"; exit 2; }
echo "unarmed: green"
red=0; bad=0
arm() {
  local name="$1" f="$2" k="$3" old="$4" new="$5"
  $PY - "$f" "$old" "$new" <<'PYEOF' || { echo "ANCHOR NOT FOUND: $name"; restore; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
if s.count(old) != 1: sys.exit(1)
open(p, "w").write(s.replace(old, new))
PYEOF
  L=$(mktemp); timeout 300 $PY -m pytest $T -k "$k" >"$L" 2>&1; prc=$?
  out=$(tail -1 "$L"); rm -f "$L"
  restore
  if [ $prc = 1 ]; then echo "ARM $name: RED ($out)"; red=$((red+1));
  else echo "ARM $name: NOT RED, pytest rc=$prc ($out)"; bad=$((bad+1)); fi
}
arm "the board talks as an agent" hearth/talk.py "never_talks_as_an_agent" \
  "    if user_id in {agent_id(n, user_id, namespace) for n in declared}:" "    if False:"
arm "another site's page talks through the operator's browser" hearth/board.py "only_the_operator" \
  "            if self.headers.get(\"Sec-Fetch-Site\", \"same-origin\") != \"same-origin\" \\
                    or self.headers.get_content_type() != \"application/json\":" \
  "            if self.headers.get_content_type() != \"application/json\":"
arm "a form post talks" hearth/board.py "only_the_operator" \
  "            if self.headers.get(\"Sec-Fetch-Site\", \"same-origin\") != \"same-origin\" \\
                    or self.headers.get_content_type() != \"application/json\":" \
  "            if self.headers.get(\"Sec-Fetch-Site\", \"same-origin\") != \"same-origin\":"
arm "a token others can read is used" hearth/talk.py "only_the_operator" \
  "        if mode & (stat.S_IRWXG | stat.S_IRWXO):" "        if False:"
arm "an undeclared agent is talked to" hearth/talk.py "declared_agents" \
  "        if name not in set(self.declared()):" "        if False:"
arm "every message opens a new thread" hearth/talk.py "sender_like_any_other" \
  "            room = await self._room(matrix, me, agent, direct)
            if room is None:" \
  "            room = None
            if room is None:"
arm "the operator's message doesn't wake the agent" hearth/talk.py "sender_like_any_other" \
  "{\"msgtype\": \"m.text\", \"body\": text}" "{\"msgtype\": \"m.text\", \"body\": text, wire.NS: {\"arrive\": wire.WAIT}}"
arm "what became of a message isn't shown" hearth/talk.py "sender_like_any_other" \
  "                    message[\"state\"] = states.get(message[\"id\"], wire.ACCEPTED)" \
  "                    message[\"state\"] = wire.ACCEPTED"
echo "arms red: $red, arms bad: $bad"
[ $bad = 0 ]
