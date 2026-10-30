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
  - It reads status and never writes it: status is read-only (hearth.status). What it does is
    send the operator's message to an agent, on the desk (hearth.talk), and restart one agent's
    host. Anything else but GET is refused.
  - A restart names one declared agent's host unit and nothing else, and needs no privilege of
    the board's own: systemd asks polkit, whose rule (home/hearth-board.rules) lets the board's
    user restart agents' host units and do nothing else to any unit. The agent is shown the
    restart at its next wake by its own host (hearth.host).
  - It runs as neither root nor any agent, and refuses to start as either.
  - Only the operator reaches it: it refuses a socket directory every user can enter. The
    operator's proxy is granted the directory's group. Nothing another site's page sends through
    the operator's browser is acted on: a send must be same-origin JSON.
  - What an agent reports is filed under the name the registry gives that agent's socket, never
    the name it reports, and the page writes every value as text.

    python -I -m hearth.board --socket /run/hearth-board/board.sock     as hearth-board
    python -I -m hearth.board sign-in --desk URL --user @will:desk     as hearth-board, once
"""
import argparse
import getpass
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

from hearth import status, talk as talking
from hearth import status_pb2 as pb
from hearth import status_pb2_grpc as rpc

logger = logging.getLogger("hearth.board")

REGISTRY = Path("/var/lib/hearth/tenants")
RUN = Path("/run/hearth")
INTERVAL_S = 5.0
MAX_BODY = 64 * 1024
STALE_AFTER = 3   # read intervals without a full read before the board calls itself stale
WATCH = {"built": False, "reason": "no agent records a sweep yet, so no ledger can be judged unattended"}


class Refused(Exception):
    pass


class RestartError(Exception):
    pass


def unit_state(agent: str) -> str:
    """systemd's ActiveState for the agent's host, or "unknown" when systemd can't say."""
    try:
        out = subprocess.run(["systemctl", "show", f"hearth-host@{agent}.service", "-p", "ActiveState", "--value"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def systemctl_restart(agent: str) -> None:
    """Ask systemd to restart the agent's host, without waiting for it to come back up."""
    try:
        out = subprocess.run(["systemctl", "--no-ask-password", "--no-block", "restart", f"hearth-host@{agent}.service"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RestartError(f"systemctl couldn't be run: {exc}") from exc
    if out.returncode != 0:
        raise RestartError(out.stderr.strip() or f"systemctl exited {out.returncode}")


class Board:
    def __init__(self, registry: Path = REGISTRY, run: Path = RUN, *,
                 unit_state: Callable[[str], str] = unit_state, interval_s: float = INTERVAL_S,
                 timeout_s: float = 2.0, clock: Callable[[], float] = time.time,
                 restart: Callable[[str], None] = systemctl_restart):
        self.registry, self.run, self.unit_state = Path(registry), Path(run), unit_state
        self._restart, self.restarts = restart, {}   # agent: when the board last restarted its host
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

    def names(self) -> list[str]:
        return [name for name, _, _ in self.declared()]

    def restart(self, name: str) -> None:
        """Restart one declared agent's host. Raises KeyError for any other name."""
        if name not in self.names():
            raise KeyError(name)
        self._restart(name)
        self.restarts[name] = self.clock()
        logger.info("restarted %s's host", name)

    def snapshot(self) -> dict:
        with self._changed:
            snap = dict(self._snapshot)
        now = self.clock()
        snap["age_s"] = None if snap["checked_at"] is None else round(now - snap["checked_at"], 1)
        snap["stale"] = snap["age_s"] is None or snap["age_s"] > STALE_AFTER * self.interval_s
        snap["interval_s"], snap["watch"] = self.interval_s, WATCH
        snap["agents"] = [{**a, "restarted": self.restarts.get(a["name"])} for a in snap["agents"]]
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


def _route(path: str) -> tuple[Optional[str], str]:
    """``/api/agents/<name>/<what>`` as (name, what); anything else as (None, path)."""
    parts = path.split("/")
    if len(parts) == 5 and parts[:3] == ["", "api", "agents"] and parts[3]:
        return parts[3], parts[4]
    return None, path


def handler(board: Board, talk: Optional[talking.Talk] = None):
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

        def _json(self, code: int, value) -> None:
            self._send(code, json.dumps(value).encode(), "application/json")

        def _snapshot(self) -> dict:
            snap = board.snapshot()
            snap["talk"] = {"ready": False, "reason": "not served by this board"} if talk is None else \
                {"ready": (why := talk.ready()) is None, "reason": why}
            return snap

        def do_GET(self):
            name, what = _route(self.path)
            if self.path == "/":
                self._send(200, PAGE, "text/html; charset=utf-8")
            elif self.path == "/api/agents":
                self._json(200, self._snapshot())
            elif self.path == "/api/events":
                self._events()
            elif name and what == "thread" and talk is not None:
                self._talk(lambda: {"messages": talk.thread(name)})
            else:
                self._send(404, b"not found\n", "text/plain")

        def do_POST(self):
            name, what = _route(self.path)
            if not (name and (what == "restart" or what in ("talk", "read") and talk is not None)):
                return self._refuse()
            # Another site's page can make the operator's browser POST here, with the proxy's login
            # attached. A browser marks it cross-site, and can't send it as JSON without asking first,
            # which nothing here answers.
            if self.headers.get("Sec-Fetch-Site", "same-origin") != "same-origin" \
                    or self.headers.get_content_type() != "application/json":
                return self._json(403, {"error": "only the board's own page can send"})
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._json(413, {"error": "too long"})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json(400, {"error": "not JSON"})
            if not isinstance(body, dict):
                return self._json(400, {"error": "not a JSON object"})
            if what == "restart":
                self._restart(name)
            elif what == "talk":
                self._talk(lambda: {"sent": talk.say(name, body.get("text"))})
            else:
                self._talk(lambda: talk.read(name, body.get("up_to")) or {"read": True})

        def _restart(self, name: str) -> None:
            try:
                board.restart(name)
            except KeyError:
                return self._json(404, {"error": f"{name!r} isn't a declared agent"})
            except RestartError as exc:
                return self._json(502, {"error": f"not restarted: {exc}"})
            self._json(200, {"restarted": name})

        def _talk(self, act) -> None:
            try:
                self._json(200, act())
            except talking.TalkError as exc:
                self._json(exc.code, {"error": exc.reason})

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    self.wfile.write(b"data: " + json.dumps(self._snapshot()).encode() + b"\n\n")
                    self.wfile.flush()
                    board.wait(board.interval_s)
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True

        def _refuse(self):
            self.send_response(405)
            self.send_header("Allow", "GET, POST")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_PUT = do_PATCH = do_DELETE = _refuse

    return Handler


class UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def get_request(self):
        conn, _ = super().get_request()
        return conn, ("operator", 0)   # BaseHTTPRequestHandler expects a (host, port) address


def serve(board: Board, sock: Path, *, uid: Optional[int] = None,
          talk: Optional[talking.Talk] = None) -> UnixHTTPServer:
    """Check who this is and where it serves, then bind. The caller runs serve_forever."""
    board.refuse_to_run_as(os.getuid() if uid is None else uid)
    try:
        status.private_dir(sock.parent)
    except status.StatusError as exc:
        raise Refused(str(exc)) from exc
    if sock.is_socket():
        sock.unlink()
    server = UnixHTTPServer(str(sock), handler(board, talk))
    sock.chmod(0o660)   # the directory's group is the operator's proxy
    return server


def sign_in(argv) -> int:
    ap = argparse.ArgumentParser(prog="hearth.board sign-in",
                                 description="Sign the board in as the operator. Asks for the password, or reads it from stdin.")
    ap.add_argument("--desk", required=True, help="the desk's URL")
    ap.add_argument("--user", required=True, help="the operator's full identity, e.g. @will:desk")
    ap.add_argument("--operator", type=Path, default=talking.OPERATOR)
    ap.add_argument("--registry", type=Path, default=REGISTRY)
    ap.add_argument("--namespace", default="", help="a trial's namespace, never the main register")
    a = ap.parse_args(argv)
    password = getpass.getpass("password: ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n")
    try:
        who = talking.sign_in(a.desk, a.user, password, Board(a.registry).names(), a.operator, a.namespace)
    except talking.TalkError as exc:
        print(f"hearth.board: {exc}", file=sys.stderr)
        return 78
    print(f"the board talks as {who} ({a.operator})")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["sign-in"]:
        return sign_in(argv[1:])
    ap = argparse.ArgumentParser(prog="hearth.board")
    ap.add_argument("--socket", type=Path, required=True)
    ap.add_argument("--registry", type=Path, default=REGISTRY)
    ap.add_argument("--run", type=Path, default=RUN)
    ap.add_argument("--operator", type=Path, default=talking.OPERATOR)
    a = ap.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    board = Board(a.registry, a.run)
    try:
        server = serve(board, a.socket, talk=talking.Talk(board.names, a.operator))
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
