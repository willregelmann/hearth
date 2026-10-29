#!/bin/sh
# The status and board sockets' real permissions, on Linux as root in a throwaway container:
#   podman run --rm -v $PWD:/src:ro -v <frontdesk checkout>:/fd:ro -v $PWD/tests/linux-grants.sh:/run.sh:ro python:3.12-slim sh /run.sh
# Expected: alice and board READ alice's status, mallory REFUSED; the board refuses root and alice
# (rc 78); caddy (in hearth-operators) opens the board, mallory is denied.
# mallory is another agent. Only alice and board may read alice's status.
set -e
groupadd -r hearth-board; useradd -m alice; useradd -m mallory; useradd -r -g hearth-board board
python -m venv /v >/dev/null && cp -R /fd /fdc && /v/bin/pip -q install /fdc "grpcio>=1.85,<2" "protobuf>=7.36,<8" >/dev/null 2>&1
cp -R /src /h; /v/bin/pip -q install --no-deps /h >/dev/null 2>&1; mkdir -p /run/hearth/alice; chown alice:alice /run/hearth/alice; chmod 0750 /run/hearth/alice
chgrp hearth-board /run/hearth/alice && chmod g+s /run/hearth/alice   # the unit's two ExecStartPre=-+ lines
cat > /srv.py <<'P'
import asyncio, sys
sys.path.insert(0, "/h")
from hearth import status
class H: live, deferred, failed = {}, set(), {}
class D:
    class ledger:
        live_channels = staticmethod(lambda: [])
H.desk = D
async def main():
    s = await status.serve(status.Reporter(H, "alice", "/nonexistent"), "/run/hearth/alice/status.sock")
    await asyncio.sleep(30)
asyncio.run(main())
P
cat > /cli.py <<'P'
import sys, grpc
sys.path.insert(0, "/h")
from hearth import status_pb2 as pb, status_pb2_grpc as rpc
try:
    with grpc.insecure_channel("unix:/run/hearth/alice/status.sock") as ch:
        print(sys.argv[1], "READ", rpc.StatusStub(ch).Get(pb.GetRequest(), timeout=3).agent)
except grpc.RpcError as e:
    print(sys.argv[1], "REFUSED", e.code().name)
P
su alice -s /bin/sh -c "/v/bin/python /srv.py" & sleep 4
ls -la /run/hearth/alice
for u in alice board mallory; do su $u -s /bin/sh -c "/v/bin/python /cli.py $u"; done
# The board itself, as board, behind a proxy user in hearth-operators.
groupadd -r hearth-operators; useradd -r -G hearth-operators caddy
mkdir -p /var/lib/hearth/tenants /run/hearth-board
id -u alice > /var/lib/hearth/tenants/alice; id -u mallory > /var/lib/hearth/tenants/mallory
chown board:hearth-board /run/hearth-board; chmod 0750 /run/hearth-board
chgrp hearth-operators /run/hearth-board && chmod g+s /run/hearth-board   # hearth-board.service's ExecStartPre
cd /h && /v/bin/python -I -m hearth.board --socket /run/hearth-board/root.sock || echo "as root: rc $?"
su alice -s /bin/sh -c "cd /h && /v/bin/python -I -m hearth.board --socket /run/hearth-board/a.sock" || echo "as alice: rc $?"
su board -s /bin/sh -c "cd /h && /v/bin/python -I -m hearth.board --socket /run/hearth-board/board.sock" 2>/dev/null & sleep 4
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
for u in caddy mallory; do su $u -s /bin/sh -c "/v/bin/python /get.py $u"; done
