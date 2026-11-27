#!/usr/bin/env bash
# End-to-end on a kind cluster: the real gateway image and manifests, with the test suite's stand-in
# for Claude Code. Each check is named after the invariant it shows holding in a pod.
#   deploy/test/kind-e2e.sh           build, deploy, check, and delete the cluster
#   deploy/test/kind-e2e.sh --keep    leave the cluster for a look afterwards
set -uo pipefail
cd "$(dirname "$0")/../.."
CLUSTER=hearth-e2e NS=hearth-e2e POD=hearth-0 KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1
failed=0
say()  { printf '%s\n' "$*"; }
pass() { say "PASS  $1"; }
fail() { say "FAIL  $1: $2"; failed=1; }
k()    { kubectl --context "kind-$CLUSTER" -n "$NS" "$@"; }
in_pod() { k exec "$POD" -c gateway -- "$@"; }
log_lines() { in_pod sh -c 'cat "$FAKE_CLAUDE_DIR/log.jsonl" 2>/dev/null' ; }
# wait_for SECONDS DESCRIPTION COMMAND...: true once COMMAND succeeds
wait_for() {
  local limit=$1 what=$2; shift 2
  local end=$((SECONDS + limit))
  until "$@" >/dev/null 2>&1; do
    [ $SECONDS -ge $end ] && { say "timed out after ${limit}s waiting for $what"; return 1; }
    sleep 1
  done
}
ready() { k wait --for=condition=Ready "pod/$POD" --timeout=180s >/dev/null; }
ended_for() { log_lines | python3 -c "
import json,sys
want=sys.argv[1]; n=int(sys.argv[2])
starts=[json.loads(l) for l in sys.stdin if l.strip()]
print(sum(1 for e in starts if e['event']=='start' and want in e['prompt']))
sys.exit(0 if sum(1 for e in starts if e['event']=='start' and want in e['prompt'])>=n else 1)" "$1" "${2:-1}"; }
wake_state() { in_pod hearth wake list --all --json | python3 -c "
import json,sys
w=[x for x in json.load(sys.stdin) if x['note']==sys.argv[1]]
print(w[0]['state'] if w else 'missing')" "$1"; }

say "== cluster"
kind get clusters 2>/dev/null | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER" --wait 120s || exit 2
cleanup() { [ $KEEP = 1 ] || kind delete cluster --name "$CLUSTER" >/dev/null 2>&1; }
trap cleanup EXIT

say "== images"
docker build -q -f deploy/gateway/Containerfile --build-arg INSTALL_CLAUDE=0 -t hearth-gateway:e2e . >/dev/null || exit 2
docker build -q -f deploy/test/Containerfile -t hearth-gateway-fake:e2e . >/dev/null || exit 2
kind load docker-image --name "$CLUSTER" hearth-gateway-fake:e2e >/dev/null || exit 2

say "== deploy"
# Start from nothing: an earlier run's volume would carry its wakes into this one.
kubectl --context "kind-$CLUSTER" delete namespace "$NS" --ignore-not-found --wait=true >/dev/null
kubectl --context "kind-$CLUSTER" apply -k deploy/test/overlay >/dev/null || exit 2
wait_for 180 "the pod to exist" k get pod "$POD" && ready || { k describe pod "$POD" | tail -30; exit 2; }

say "== checks"
# 1. A wake raised in the pod becomes a turn in the conversation it names.
in_pod hearth wake --conversation build --note "e2e: hello" >/dev/null
if wait_for 60 "the first turn" ended_for "e2e: hello" && [ "$(wake_state 'e2e: hello')" = done ]; then
  pass "a wake reaches the conversation it names"
else fail "a wake reaches the conversation it names" "no finished turn showed it"; fi

# 2. A wake outlives its pod being killed in the middle of its turn, and runs again, told so.
in_pod sh -c 'touch "$FAKE_CLAUDE_DIR/hold"'
in_pod hearth wake --conversation build --note "e2e: survive" >/dev/null
wait_for 60 "the held turn to start" ended_for "e2e: survive" 1
k delete pod "$POD" --grace-period=0 --force >/dev/null 2>&1
sleep 3; wait_for 180 "the pod to come back" k get pod "$POD"; ready
in_pod sh -c 'rm -f "$FAKE_CLAUDE_DIR/hold"'
if wait_for 90 "the wake to run again" ended_for "e2e: survive" 2 \
   && [ "$(wake_state 'e2e: survive')" = done ] \
   && log_lines | grep -q "may have been shown to an earlier turn"; then
  pass "a wake survives its pod being killed mid-turn, and the next turn is told"
else fail "a wake survives its pod being killed mid-turn" "state $(wake_state 'e2e: survive')"; fi

# 3. A not-before wake never fires early, across the pod being rescheduled.
due=$(( $(date +%s) + 45 ))
in_pod hearth wake --conversation later --in 45s --note "e2e: not before" >/dev/null
k delete pod "$POD" >/dev/null 2>&1
sleep 3; wait_for 180 "the pod to come back" k get pod "$POD"; ready
early=0
while [ "$(date +%s)" -lt $((due - 3)) ]; do
  ended_for "e2e: not before" >/dev/null 2>&1 && { early=1; break; }
  sleep 2
done
if [ $early = 0 ] && wait_for 90 "the not-before wake" ended_for "e2e: not before"; then
  ran_at=$(log_lines | python3 -c "
import json,sys
print(int(min(json.loads(l)['t'] for l in sys.stdin if l.strip() and json.loads(l)['event']=='start' and 'e2e: not before' in json.loads(l)['prompt'])))")
  if [ "$ran_at" -ge "$due" ]; then pass "a not-before wake never fires early, across a reschedule"
  else fail "a not-before wake never fires early" "ran at $ran_at, due $due"; fi
else fail "a not-before wake never fires early, across a reschedule" "early=$early"; fi

# 4. A second gateway on the same home refuses to start.
out=$(in_pod timeout 20 hearth gateway 2>&1); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q "another gateway is already running"; then
  pass "at most one gateway delivers for a Hearth home"
else fail "at most one gateway delivers for a Hearth home" "rc=$rc: $out"; fi

# 5. The record-only session hooks are in the agent's configuration directory.
if in_pod sh -c 'grep -q -- "--record-only" "$CLAUDE_CONFIG_DIR/settings.json"'; then
  pass "a session started without Hearth in the pod is recorded (hooks installed)"
else fail "a session started without Hearth in the pod is recorded" "no record-only hooks in settings.json"; fi

[ $failed = 0 ] && say "== all checks passed" || { say "== some checks failed"; k logs "$POD" --tail=40; }
exit $failed
