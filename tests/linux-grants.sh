#!/bin/bash
# Who can reach what, on Linux under real systemd and polkit, as root in a throwaway container
# (tests/linux.Containerfile says how to start one). The real units, the real home/board and the
# real polkit rule; only the agents' status servers are stand-ins, since a real host needs a desk.
# Expected, each line as marked:
#   alice's status dir is alice:hearth-board, setgid; the board's is hearth-board:hearth-operators
#   alice and hearth-board READ alice's status, mallory REFUSED
#   the board refuses root and alice (rc 78)
#   caddy (in hearth-operators) OPENS the board and sees alice reachable; mallory is denied
#   hearth-board may restart an agent's host and nothing else; no one else may
#   a restart through the board restarts alice's host and leaves mallory's alone
set -u
python -m venv /opt/hearth/venv >/dev/null && cp -R /fd /fdc && cp -R /src /h
rm -rf /h/build /fdc/build   # a checkout's old build output would be installed instead of its source
/opt/hearth/venv/bin/pip -q install /fdc "grpcio>=1.85,<2" "protobuf>=7.36,<8" >/dev/null 2>&1
/opt/hearth/venv/bin/pip -q install --no-deps /h >/dev/null 2>&1 || { echo "hearth didn't install"; exit 2; }
PY=/opt/hearth/venv/bin/python
useradd -m alice; useradd -m mallory; useradd -m caddy
mkdir -p /var/lib/hearth/tenants; id -u alice > /var/lib/hearth/tenants/alice; id -u mallory > /var/lib/hearth/tenants/mallory
bash /h/home/board >/tmp/board.out 2>&1 || { echo "home/board failed:"; cat /tmp/board.out; exit 2; }
usermod -aG hearth-operators caddy
install -m 644 /h/home/hearth-host@.service /etc/systemd/system/ && systemctl daemon-reload
# No desk here, so each host stops at its check (rc 78) after its ExecStartPre made its directory.
systemctl start hearth-host@alice hearth-host@mallory 2>/dev/null; sleep 2
stat -c '%n %U:%G %A' /run/hearth/alice /run/hearth-board /run/hearth-board/board.sock

cat > /srv.py <<'P'
import asyncio
from hearth import status
class H: live, deferred, failed, started, restarted = {}, set(), {}, 0.0, None
class D:
    class ledger:
        live_channels = staticmethod(lambda: [])
H.desk = D
async def main():
    server = await status.serve(status.Reporter(H, "alice", "/nonexistent"), "/run/hearth/alice/status.sock")  # kept, or it is collected
    await asyncio.sleep(3600)
asyncio.run(main())
P
cat > /cli.py <<'P'
import sys, grpc
from hearth import status_pb2 as pb, status_pb2_grpc as rpc
try:
    with grpc.insecure_channel("unix:/run/hearth/alice/status.sock") as ch:
        print(sys.argv[1], "READ", rpc.StatusStub(ch).Get(pb.GetRequest(), timeout=3).agent)
except grpc.RpcError as e:
    print(sys.argv[1], "REFUSED", e.code().name)
P
systemd-run -q --uid=alice --unit=alice-status $PY -I /srv.py; sleep 4
for u in alice hearth-board mallory; do runuser -u $u -- $PY -I /cli.py $u; done

$PY -I -m hearth.board --socket /run/hearth-board/root.sock 2>/dev/null; echo "board as root: rc $?"
runuser -u alice -- $PY -I -m hearth.board --socket /tmp/a.sock 2>/dev/null; echo "board as alice: rc $?"
sleep 6   # the board's next read finds alice's status
cat > /get.py <<'P'
import http.client, json, socket, sys
c = http.client.HTTPConnection("x"); c.sock = socket.socket(socket.AF_UNIX)
try:
    c.sock.connect("/run/hearth-board/board.sock")
except OSError as e:
    print(sys.argv[1], "REFUSED", e.strerror); sys.exit()
c.request("GET", "/api/agents"); d = json.loads(c.getresponse().read())
print(sys.argv[1], "OPENED:", [(a["name"], a["reachable"]) for a in d["agents"]], "read", d["read"], "of", d["declared"])
P
for u in caddy mallory; do runuser -u $u -- $PY -I /get.py $u; done

try() { local who=$1; shift
  if runuser -u $who -- systemctl --no-ask-password "$@" >/dev/null 2>&1; then echo "  $who $*: ALLOWED"; else echo "  $who $*: denied"; fi; }
systemctl start polkit
echo "polkit:"
try hearth-board restart hearth-host@alice.service
for cmd in "stop hearth-host@alice.service" "start hearth-host@alice.service" "restart hearth-board.service" \
           "restart dbus.service"; do try hearth-board $cmd; done
try alice restart hearth-host@mallory.service
try caddy restart hearth-host@alice.service
inv() { systemctl show -p InvocationID --value hearth-host@$1; }
a=$(inv alice); m=$(inv mallory)
echo "through the board: $(runuser -u caddy -- curl -s --unix-socket /run/hearth-board/board.sock -X POST \
  -H 'Content-Type: application/json' -H 'Sec-Fetch-Site: same-origin' -d '{}' http://board/api/agents/alice/restart)"
sleep 2
echo "  alice's host restarted: $([ "$(inv alice)" != "$a" ] && echo yes || echo NO)"
echo "  mallory's host left alone: $([ "$(inv mallory)" = "$m" ] && echo yes || echo NO)"
