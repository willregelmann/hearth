#!/usr/bin/env bash
# Run inside deploy/systemd/test/Containerfile, as root. Each check is named after what it shows.
set -uo pipefail
failed=0
pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1: $2"; failed=1; }
as() { local u=$1; shift; runuser -u "$u" -- env -i HOME="/home/$u" PATH=/opt/hearth/bin:/usr/local/bin:/usr/bin:/bin \
         FAKE_CLAUDE_DIR="/home/$u/fake" "$@"; }
hearth() { local u=$1; shift; as "$u" /opt/hearth/bin/hearth "$@"; }
log() { cat "/home/$1/fake/log.jsonl" 2>/dev/null; }
wait_for() { local n=$1; shift; for _ in $(seq 1 "$n"); do "$@" >/dev/null 2>&1 && return 0; sleep 0.5; done; return 1; }
ended() { python3 -c "import json,sys; sys.exit(0 if sum(json.loads(l)['event']=='end' for l in open('/home/$1/fake/log.jsonl'))>=$2 else 1)"; }

for u in ash wren; do
  useradd --create-home --shell /bin/bash "$u" && chmod 700 "/home/$u"
  printf 'turn_timeout = 60\n' | hearth "$u" agent add "$u" --manifest - >/dev/null
  printf 'tick_s = 0.2\nshutdown_grace_s = 5.0\n' > "/home/$u/.hearth/config.toml" && chown "$u:$u" "/home/$u/.hearth/config.toml"
  hearth "$u" agent install "$u" >/dev/null
  as "$u" /opt/hearth/bin/hearth gateway > "/tmp/$u.log" 2>&1 &
  echo $! > "/tmp/$u.pid"
done
sleep 2

# 1. Each agent's turns run as its own user.
hearth ash wake --agent ash --conversation c --note one >/dev/null
hearth wren wake --agent wren --conversation c --note one >/dev/null
if wait_for 40 ended ash 1 && wait_for 40 ended wren 1 \
   && [ "$(log ash | python3 -c 'import json,sys; print({e["uid"] for e in map(json.loads, sys.stdin) if e["event"] == "start"})')" = "{$(id -u ash)}" ] \
   && [ "$(log wren | python3 -c 'import json,sys; print({e["uid"] for e in map(json.loads, sys.stdin) if e["event"] == "start"})')" = "{$(id -u wren)}" ]; then
  pass "each agent's turns run as its own user"
else fail "each agent's turns run as its own user" "$(log ash | head -c 300)"; fi

# 2. Another agent can't read an agent's state or transcripts, or push to its gateway.
if as wren cat /home/ash/.hearth/hearth.db >/dev/null 2>&1 || as wren ls /home/ash >/dev/null 2>&1; then
  fail "another agent can't read an agent's home" "wren read /home/ash"
else pass "another agent can't read an agent's home"; fi
out=$(as wren env HEARTH_HOME=/home/ash/.hearth /opt/hearth/bin/hearth wake --agent ash --conversation x --note sneaky 2>&1)
if [ $? -ne 0 ] && ! grep -q sneaky <(hearth ash wake list --all 2>/dev/null); then
  pass "another agent can't push a wake to an agent's gateway"
else fail "another agent can't push a wake to an agent's gateway" "$out"; fi

# 3. Restarting one agent's gateway leaves another's running turn alone.
touch /home/wren/fake/hold && chown wren:wren /home/wren/fake/hold
hearth wren wake --agent wren --conversation c --note held >/dev/null
wait_for 40 python3 -c "import json,sys; sys.exit(0 if sum(json.loads(l)['event']=='start' for l in open('/home/wren/fake/log.jsonl'))>=2 else 1)"
wren_pid=$(cat /tmp/wren.pid)
kill -TERM "$(cat /tmp/ash.pid)"; wait "$(cat /tmp/ash.pid)" 2>/dev/null
as ash /opt/hearth/bin/hearth gateway >> /tmp/ash.log 2>&1 & echo $! > /tmp/ash.pid
sleep 2; rm -f /home/wren/fake/hold
if wait_for 40 ended wren 2 && kill -0 "$wren_pid" 2>/dev/null \
   && hearth wren wake list --all | grep -q "done .*held"; then
  pass "restarting one agent's gateway leaves another's running turn alone"
else fail "restarting one agent's gateway leaves another's running turn alone" "$(tail -3 /tmp/wren.log)"; fi

# 4. systemd accepts the unit for an agent.
if out=$(systemd-analyze verify /etc/systemd/system/hearth@.service hearth@wren.service 2>&1) && ! grep -qiE "error|invalid|unknown" <<<"$out"; then
  pass "systemd accepts hearth@<agent>.service"
else fail "systemd accepts hearth@<agent>.service" "$out"; fi

for u in ash wren; do kill -TERM "$(cat /tmp/$u.pid)" 2>/dev/null; done
[ $failed = 0 ] && echo "== all checks passed" || echo "== some checks failed"
exit $failed
