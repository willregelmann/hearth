#!/bin/bash
# Mutation arms for host/hearth_host.py: each breaks one guarantee and must turn a named test red.
# cmp-guarded: the source is restored and checked byte-identical after every arm.
set -u
cd "$(dirname "$0")/.."
export FRONTDESK_TEST_DESK=http://127.0.0.1:8018
PY=${PY:-python3}
F=host/hearth_host.py
B=$(mktemp); cp -p $F $B
red=0; bad=0
arm() {
  local name="$1" old="$2" new="$3"
  $PY - "$F" "$old" "$new" <<'EOF'
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
assert s.count(old) == 1, f"anchor not unique: {old!r}"; open(p, "w").write(s.replace(old, new))
EOF
  out=$(timeout 200 $PY -m pytest -q -p no:cacheprovider host/test_hearth_host.py 2>&1 | tail -1)
  cp -p $B $F; cmp -s $B $F || { echo "RESTORE FAILED"; exit 2; }
  if echo "$out" | grep -q failed; then echo "ARM $name: RED ($out)"; red=$((red+1)); else echo "ARM $name: GREEN ($out)"; bad=$((bad+1)); fi
}
arm "today's host: only the open session (no turn for a closed one)" \
  "        task = asyncio.get_running_loop().create_task(self._turn(conversation))" \
  "        return
        task = asyncio.get_running_loop().create_task(self._turn(conversation))"
arm "commit even when the turn failed" \
  "            if rc != 0:" "            if False:"
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
  "            await self.desk.commit(conversation, also=[a.ref for a in arrivals])" \
  "            pass"
rm -f $B
echo "arms red: $red, arms green: $bad"
