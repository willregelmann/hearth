"""The board (docs/interfaces/BOARD.md): the operator's page, listing every agent on the host with
its status as last read. Served over HTTP on a Unix socket, for a proxy that does the operator's
login (docs/decisions/0013).

What holds:
  - Every declared agent is listed. Declared means in the tenant registry provision writes
    (root's, outside every home), never what happens to be found under /run. One whose status
    can't be read is listed as unreachable, with why.
  - The board shows its own freshness: every reply says when the last full read finished, how
    many of the declared agents it read, and whether that is stale by the board's own clock. A
    page that stops hearing from the board says so too.
  - It only reads. Status is read-only (hearth.status), and anything but GET is refused.
  - It runs as neither root nor any agent, and refuses to start as either.
  - Only the operator reaches it: it refuses a socket directory every user can enter. The
    operator's proxy is granted the directory's group.
  - What an agent reports is filed under the name the registry gives that agent's socket, never
    the name it reports, and the page writes every value as text.

    python -I -m hearth.board --socket /run/hearth-board/board.sock     as hearth-board
"""
import argparse
import json
import logging
import os
import socketserver
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Callable, Optional

import grpc
from google.protobuf.json_format import MessageToDict

from hearth import status
from hearth import status_pb2 as pb
from hearth import status_pb2_grpc as rpc

logger = logging.getLogger("hearth.board")

REGISTRY = Path("/var/lib/hearth/tenants")
RUN = Path("/run/hearth")
INTERVAL_S = 5.0
STALE_AFTER = 3   # read intervals without a full read before the board calls itself stale
WATCH = {"built": False, "reason": "no agent records a sweep yet, so no ledger can be judged unattended"}


class Refused(Exception):
    pass


def unit_state(agent: str) -> str:
    """systemd's ActiveState for the agent's host, or "unknown" when systemd can't say."""
    try:
        out = subprocess.run(["systemctl", "show", f"hearth-host@{agent}.service", "-p", "ActiveState", "--value"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


class Board:
    def __init__(self, registry: Path = REGISTRY, run: Path = RUN, *,
                 unit_state: Callable[[str], str] = unit_state, interval_s: float = INTERVAL_S,
                 timeout_s: float = 2.0, clock: Callable[[], float] = time.time):
        self.registry, self.run, self.unit_state = Path(registry), Path(run), unit_state
        self.interval_s, self.timeout_s, self.clock = interval_s, timeout_s, clock
        self._snapshot = {"checked_at": None, "declared": 0, "read": 0, "agents": []}
        self._changed = threading.Condition()

    def declared(self) -> list[tuple[str, Optional[int], Optional[str]]]:
        """(name, uid, problem) for every entry in the registry. An unreadable entry is still listed."""
        out = []
        for f in sorted(self.registry.iterdir()):
            try:
                out.append((f.name, int(f.read_text().strip()), None))
            except (OSError, ValueError) as exc:
                out.append((f.name, None, f"its registry entry can't be read: {exc}"))
        return out

    def refuse_to_run_as(self, uid: int) -> None:
        if uid == 0:
            raise Refused("the board never runs as root (docs/decisions/0013)")
        for name, agent_uid, _ in self.declared():
            if agent_uid == uid:
                raise Refused(f"the board never runs as an agent, and this is {name}'s user")

    def read_one(self, name: str) -> dict:
        entry = {"name": name, "host": self.unit_state(name), "reachable": False}
        sock = self.run / name / "status.sock"
        try:
            with grpc.insecure_channel(f"unix:{sock}") as ch:
                report = rpc.StatusStub(ch).Get(pb.GetRequest(), timeout=self.timeout_s)
        except grpc.RpcError as exc:
            entry["unreachable"] = f"{sock}: {exc.code().name.lower()}: {exc.details()}"
            return entry
        r = MessageToDict(report, preserving_proto_field_name=True, always_print_fields_with_no_presence=True)
        r.pop("agent", None)   # the registry names the agent, not the agent
        entry.update(reachable=True, status=r)
        return entry

    def read_all(self) -> dict:
        agents = []
        for name, _, problem in self.declared():
            if problem:
                agents.append({"name": name, "host": "unknown", "reachable": False, "unreachable": problem})
            else:
                agents.append(self.read_one(name))
        snap = {"checked_at": self.clock(), "declared": len(agents),
                "read": sum(a["reachable"] for a in agents), "agents": agents}
        with self._changed:
            self._snapshot = snap
            self._changed.notify_all()
        return snap

    def snapshot(self) -> dict:
        with self._changed:
            snap = dict(self._snapshot)
        now = self.clock()
        snap["age_s"] = None if snap["checked_at"] is None else round(now - snap["checked_at"], 1)
        snap["stale"] = snap["age_s"] is None or snap["age_s"] > STALE_AFTER * self.interval_s
        snap["interval_s"], snap["watch"] = self.interval_s, WATCH
        return snap

    def wait(self, timeout: float) -> None:
        with self._changed:
            self._changed.wait(timeout)

    def loop(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.read_all()
            except Exception:
                logger.exception("reading the fleet failed")   # the snapshot ages, and says so
            stop.wait(self.interval_s)


PAGE = (Path(__file__).parent / "board.html").read_bytes()


def handler(board: Board):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            logger.info("%s", fmt % args)

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self._send(200, PAGE, "text/html; charset=utf-8")
            elif self.path == "/api/agents":
                self._send(200, json.dumps(board.snapshot()).encode(), "application/json")
            elif self.path == "/api/events":
                self._events()
            else:
                self._send(404, b"not found\n", "text/plain")

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    self.wfile.write(b"data: " + json.dumps(board.snapshot()).encode() + b"\n\n")
                    self.wfile.flush()
                    board.wait(board.interval_s)
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True

        def _refuse(self):
            self.send_response(405)
            self.send_header("Allow", "GET")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_POST = do_PUT = do_PATCH = do_DELETE = _refuse

    return Handler


class UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def get_request(self):
        conn, _ = super().get_request()
        return conn, ("operator", 0)   # BaseHTTPRequestHandler expects a (host, port) address


def serve(board: Board, sock: Path, *, uid: Optional[int] = None) -> UnixHTTPServer:
    """Check who this is and where it serves, then bind. The caller runs serve_forever."""
    board.refuse_to_run_as(os.getuid() if uid is None else uid)
    try:
        status.private_dir(sock.parent)
    except status.StatusError as exc:
        raise Refused(str(exc)) from exc
    if sock.is_socket():
        sock.unlink()
    server = UnixHTTPServer(str(sock), handler(board))
    sock.chmod(0o660)   # the directory's group is the operator's proxy
    return server


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hearth.board")
    ap.add_argument("--socket", type=Path, required=True)
    ap.add_argument("--registry", type=Path, default=REGISTRY)
    ap.add_argument("--run", type=Path, default=RUN)
    a = ap.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    board = Board(a.registry, a.run)
    try:
        server = serve(board, a.socket)
    except Refused as exc:
        print(f"hearth.board: {exc}", file=sys.stderr)
        return 78   # EX_CONFIG: a person owes a step; systemd doesn't loop on it
    stop = threading.Event()
    threading.Thread(target=board.loop, args=(stop,), daemon=True).start()
    try:
        server.serve_forever()
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
