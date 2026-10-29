"""docs/interfaces/BOARD.md, Talk: the operator talks to an agent on a channel, as a sender like any
other (hearth.talk, hearth.board). Runs against a real desk: what a send is, who the desk says sent
it and which conversation it reaches are the homeserver's and the agent's desk's doing, which a
fake would only assert about itself. The board is reached the way the operator's proxy reaches it.

Run: FRONTDESK_TEST_DESK=http://127.0.0.1:8018 python -m pytest -q tests/test_talk.py
"""
import asyncio
import http.client
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from frontdesk import Desk

from hearth import board as hb
from hearth import talk as ht

pytestmark = pytest.mark.asyncio

DESK = os.environ.get("FRONTDESK_TEST_DESK", "http://127.0.0.1:8018")


def _desk_is_up() -> bool:
    try:
        return httpx.get(f"{DESK}/_matrix/client/versions", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(autouse=True)
def _a_desk():
    # No desk is a failure, never a skip: a skipped check reads as a pass.
    assert _desk_is_up(), f"no desk at {DESK}: start one with frontdesk's desk/up.sh --test"


class Agent:
    """An agent's side: its desk and a host that records what it was asked to start and wake."""

    def __init__(self, desk: Desk):
        self.desk, self.started, self.woken = desk, [], []
        agent = self

        class Host:
            async def wake(self, conversation):
                agent.woken.append(conversation)

            async def start(self, arrival):
                agent.started.append(f"fresh-{len(agent.started) + 1}")
                return agent.started[-1]
        desk.host = Host()

    async def until(self, condition, timeout=15.0):
        deadline = time.monotonic() + timeout
        while not condition():
            assert time.monotonic() < deadline, "timed out waiting for the desk"
            await self.desk.pump()
            await asyncio.sleep(0.1)

    async def quiet(self, seconds=2.0):
        """Look at the desk for a while, so anything sent has had its chance to arrive."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            await self.desk.pump()
            await asyncio.sleep(0.1)


class Fleet:
    def __init__(self, root: Path, namespace: str):
        self.root, self.namespace = root, namespace
        self.registry, self.run = root / "reg", root / "run"
        self.registry.mkdir()
        self.run.mkdir()
        self.operator = root / "board-state" / "operator.json"
        self.operator.parent.mkdir(mode=0o700)
        self.desks: list[Desk] = []
        self.servers: list = []

    async def join(self, name: str, **kw) -> Desk:
        desk = await Desk.join(DESK, name, self.root / "desks" / name, namespace=self.namespace, **kw)
        self.desks.append(desk)
        return desk

    def declare(self, name: str, uid: int) -> None:
        (self.registry / name).write_text(f"{uid}\n")

    def sign_in_as(self, desk: Desk) -> None:
        """The operator's sign-in file, written the way hearth.board sign-in writes it."""
        creds = json.loads((desk.state_dir / "credentials.json").read_text())
        fd = os.open(self.operator, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump({k: creds[k] for k in ("homeserver", "user_id", "access_token", "namespace")}, fh)

    def serve(self) -> "Served":
        board = hb.Board(self.registry, self.run, unit_state=lambda name: "active", timeout_s=1.0)
        d = self.root / "b"
        d.mkdir(mode=0o750, exist_ok=True)
        served = Served(board, d / "board.sock", ht.Talk(board.names, self.operator))
        self.servers.append(served)
        return served


class Served:
    def __init__(self, board, sock: Path, talk):
        self.sock = sock
        self.server = hb.serve(board, sock, uid=4242, talk=talk)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def request(self, method: str, path: str, body=None, headers=None) -> tuple[int, dict]:
        conn = http.client.HTTPConnection("board")
        conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.sock.connect(str(self.sock))
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        h = {"Content-Type": "application/json", "Sec-Fetch-Site": "same-origin"} if body is not None else {}
        h.update(headers or {})
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse()
        raw = r.read()
        conn.close()
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, {"raw": raw.decode(errors="replace")}

    def talk(self, name: str, text: str, **kw) -> tuple[int, dict]:
        return self.request("POST", f"/api/agents/{name}/talk", {"text": text}, **kw)

    def thread(self, name: str) -> list[dict]:
        code, body = self.request("GET", f"/api/agents/{name}/thread")
        assert code == 200, body
        return body["messages"]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest_asyncio.fixture
async def fleet():
    # AF_UNIX paths are short (104 bytes on macOS), so not under pytest's tmp_path.
    f = Fleet(Path(tempfile.mkdtemp(prefix="ht-")), f"test-{uuid.uuid4().hex[:8]}")
    yield f
    for s in f.servers:
        s.close()
    for d in f.desks:
        await d.close()
    shutil.rmtree(f.root, ignore_errors=True)


@pytest_asyncio.fixture
async def operator_and_agent(fleet):
    will = await fleet.join("will", kind="person")
    ember = Agent(await fleet.join("ember", answerable=will.me))
    fleet.declare("ember", 2001)
    fleet.sign_in_as(will)
    return will, ember, fleet.serve()


async def test_the_operator_talks_to_an_agent_on_a_channel_as_a_sender_like_any_other(operator_and_agent):
    will, ember, board = operator_and_agent
    code, body = board.talk("ember", "hello ember")
    assert code == 200, body

    # The agent's desk takes it like any person's message: verified as the operator, waking, and
    # the first one starts a fresh conversation. Whether a turn runs is the agent's host's call.
    await ember.until(lambda: ember.started)
    arrival, = await ember.desk.take("fresh-1")
    assert (arrival.sender, arrival.sender_kind, arrival.text) == (will.me, "person", "hello ember")
    assert ember.woken == ["fresh-1"]
    await ember.desk.commit("fresh-1")
    await ember.desk.send(will.me, "hello will", answers=arrival.ref, conversation="fresh-1")

    messages = board.thread("ember")
    assert [(m["from"], m["text"]) for m in messages] == [("operator", "hello ember"), ("agent", "hello will")]
    assert messages[0]["state"] == "taken_in", "what became of it is the agent's desk's account"

    # The rest of the thread carries the same conversation on: no second fresh one.
    assert board.talk("ember", "and again")[0] == 200
    await ember.until(lambda: len(ember.woken) == 2)
    assert ember.started == ["fresh-1"] and ember.woken == ["fresh-1", "fresh-1"]
    assert [a.text for a in await ember.desk.take("fresh-1")] == ["and again"]


async def test_what_serves_the_board_never_talks_as_an_agent(fleet):
    will = await fleet.join("will", kind="person")
    ember = Agent(await fleet.join("ember", answerable=will.me))
    wren = Agent(await fleet.join("wren", answerable=will.me))
    fleet.declare("ember", 2001)
    fleet.declare("wren", 2002)
    fleet.sign_in_as(ember.desk)
    board = fleet.serve()
    code, body = board.talk("wren", "it's me, will")
    assert code == 503 and "operator" in body["error"]
    await wren.quiet()
    assert wren.started == [] and wren.desk.waiting() == []
    creds = json.loads((ember.desk.state_dir / "credentials.json").read_text())
    with pytest.raises(ht.TalkError):
        ht.sign_in(DESK, ember.desk.me, creds["password"], ["ember", "wren"], fleet.root / "x.json", fleet.namespace)
    assert not (fleet.root / "x.json").exists()


async def test_only_the_operator_can_act_through_the_board(operator_and_agent, fleet):
    will, ember, board = operator_and_agent
    # Another site's page, through the operator's own browser and login.
    assert board.talk("ember", "from elsewhere", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert board.talk("ember", "from a sibling", headers={"Sec-Fetch-Site": "same-site"})[0] == 403
    assert board.request("POST", "/api/agents/ember/talk", b"text=a+form",
                         headers={"Content-Type": "application/x-www-form-urlencoded"})[0] == 403
    # What proves the operator, readable by another user on the host.
    fleet.operator.chmod(0o640)
    assert board.talk("ember", "with a token others can read")[0] == 503
    await ember.quiet()
    assert ember.started == [] and ember.desk.waiting() == []
    fleet.operator.chmod(0o600)
    assert board.talk("ember", "from the page")[0] == 200
    await ember.until(lambda: ember.started)


async def test_the_board_talks_only_to_declared_agents(operator_and_agent, fleet):
    will, ember, board = operator_and_agent
    mallory = Agent(await fleet.join("mallory", answerable=will.me))   # on the desk, never declared here
    code, body = board.talk("mallory", "hello")
    assert code == 404, body
    await mallory.quiet()
    assert mallory.started == [] and mallory.desk.waiting() == []
