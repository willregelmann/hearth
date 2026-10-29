"""docs/interfaces/BOARD.md, the read-only part: the agent list and the board's own freshness
(hearth.board). Each agent's status is a fake gRPC server on its socket, the system boundary;
the board is read the way the operator's proxy reads it, over HTTP on its Unix socket."""
import http.client
import json
import shutil
import socket
import tempfile
import threading
import time
from concurrent import futures
from pathlib import Path

import grpc
import pytest

from hearth import board as hb
from hearth import status_pb2 as pb
from hearth import status_pb2_grpc as rpc


class FakeStatus(rpc.StatusServicer):
    def __init__(self, report: pb.Report):
        self.report, self.calls = report, 0

    def Get(self, request, context):
        self.calls += 1
        return self.report


class Host:
    """A fake fleet: a registry, a run directory, and a status server per agent that's up."""

    def __init__(self):
        # AF_UNIX paths are short (104 bytes on macOS), so not under pytest's tmp_path.
        self.root = Path(tempfile.mkdtemp(prefix="hb-"))
        self.registry, self.run = self.root / "reg", self.root / "run"
        self.registry.mkdir()
        self.run.mkdir()
        self.servers, self.fakes = [], {}

    def declare(self, name: str, uid: int) -> None:
        (self.registry / name).write_text(f"{uid}\n")

    def up(self, name: str, report: pb.Report) -> FakeStatus:
        d = self.run / name
        d.mkdir(mode=0o750, exist_ok=True)
        fake = FakeStatus(report)
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        rpc.add_StatusServicer_to_server(fake, server)
        server.add_insecure_port(f"unix:{d / 'status.sock'}")
        server.start()
        self.servers.append(server)
        self.fakes[name] = fake
        return fake

    def board(self, **kw) -> hb.Board:
        kw.setdefault("unit_state", lambda name: "active")
        return hb.Board(self.registry, self.run, timeout_s=1.0, **kw)

    def close(self):
        for s in self.servers:
            s.stop(0)
        shutil.rmtree(self.root, ignore_errors=True)


@pytest.fixture
def fleet():
    h = Host()
    yield h
    h.close()


class Served:
    def __init__(self, board: hb.Board, sock: Path):
        self.sock = sock
        self.server = hb.serve(board, sock, uid=4242)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def request(self, method: str, path: str) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("board")
        conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.sock.connect(str(self.sock))
        conn.request(method, path)
        r = conn.getresponse()
        body = r.read()
        conn.close()
        return r.status, body

    def agents(self) -> dict:
        code, body = self.request("GET", "/api/agents")
        assert code == 200
        return json.loads(body)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def serve_board(fleet):
    made = []

    def start(board):
        d = fleet.root / "board"
        d.mkdir(mode=0o750)
        made.append(Served(board, d / "board.sock"))
        return made[-1]

    yield start
    for s in made:
        s.close()


def report(**kw) -> pb.Report:
    r = pb.Report(agent=kw.pop("agent", "x"), as_of=time.time())
    for thread in kw.pop("live", []):
        r.live_turns.add(thread=thread, started=time.time())
    return r


def test_every_declared_agent_is_listed_and_one_that_cant_be_read_shows_unreachable(fleet, serve_board):
    fleet.declare("alice", 2001)
    fleet.declare("bob", 2002)        # declared, host down: no socket at all
    fleet.declare("carol", 2003)      # declared, a socket file nothing listens on
    (fleet.run / "carol").mkdir(mode=0o750)
    (fleet.run / "carol" / "status.sock").write_text("")
    (fleet.registry / "dave").write_text("not a uid\n")
    fleet.up("alice", report(live=["sess-1"]))
    fleet.up("mallory", report())     # serving, but nobody declared it
    board = fleet.board()
    board.read_all()
    agents = {a["name"]: a for a in serve_board(board).agents()["agents"]}
    assert sorted(agents) == ["alice", "bob", "carol", "dave"]
    assert agents["alice"]["reachable"] and agents["alice"]["status"]["live_turns"][0]["thread"] == "sess-1"
    for name in ("bob", "carol", "dave"):
        a = agents[name]
        assert a["reachable"] is False and a["unreachable"] and "status" not in a, name


def test_the_board_shows_its_own_freshness(fleet, serve_board):
    fleet.declare("alice", 2001)
    fleet.declare("bob", 2002)
    fleet.up("alice", report())
    now = [1000.0]
    board = fleet.board(interval_s=5.0, clock=lambda: now[0])
    served = serve_board(board)
    first = served.agents()
    assert first["checked_at"] is None and first["stale"], "a board that never read must not look fresh"
    board.read_all()
    fresh = served.agents()
    assert (fresh["declared"], fresh["read"], fresh["stale"]) == (2, 1, False)
    now[0] += 5.0 * hb.STALE_AFTER + 1   # the reading loop stopped; the server still answers
    stale = served.agents()
    assert stale["stale"] and stale["age_s"] > 15


def test_the_board_never_starts_a_turn_or_writes_into_a_home(fleet, serve_board):
    fleet.declare("alice", 2001)
    fake = fleet.up("alice", report())
    board = fleet.board()
    board.read_all()
    served = serve_board(board)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        for path in ("/", "/api/agents", "/api/agents/alice", "/api/events"):
            code, _ = served.request(method, path)
            assert code == 405, (method, path)
    assert fake.calls == 1   # the one read; refused requests reached no agent


def test_what_serves_the_board_runs_as_neither_root_nor_any_agent(fleet):
    fleet.declare("alice", 2001)
    board = fleet.board()
    d = fleet.root / "b"
    d.mkdir(mode=0o750)
    for uid in (0, 2001):
        with pytest.raises(hb.Refused):
            hb.serve(board, d / "board.sock", uid=uid)
        assert not (d / "board.sock").exists()


def test_only_the_operator_can_open_the_board(fleet):
    board = fleet.board()
    d = fleet.root / "open"
    d.mkdir()
    d.chmod(0o755)
    with pytest.raises(hb.Refused):
        hb.serve(board, d / "board.sock", uid=4242)
    assert not (d / "board.sock").exists()


def test_what_an_agent_reports_cant_change_what_the_board_shows_about_another(fleet, serve_board):
    fleet.declare("alice", 2001)
    fleet.declare("bob", 2002)
    fleet.up("alice", report(agent="bob", live=["<img src=x onerror=alert(1)>"]))
    board = fleet.board()
    board.read_all()
    served = serve_board(board)
    agents = {a["name"]: a for a in served.agents()["agents"]}
    assert agents["bob"]["reachable"] is False, "alice's report was filed as bob's"
    assert "agent" not in agents["alice"]["status"]
    assert agents["alice"]["status"]["live_turns"][0]["thread"] == "<img src=x onerror=alert(1)>"
