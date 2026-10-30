"""Talk (docs/interfaces/BOARD.md): the operator's thread with one agent, carried on a Front Desk
channel. The board is one more chat client for the operator. It sends what a person types into any
chat client, a plain message from the operator's own identity, in the operator's direct room with
the agent: the same room the operator's other chat clients list as their direct chat with it. The
agent's desk takes it like any person's message: the sender is what the desk verified, it wakes
the agent, the first one starts a fresh conversation and the rest carry it on.

What holds:
  - The board talks only as the operator, never as an agent: an identity that is a declared
    agent's is refused, at sign-in and at every send.
  - It reaches only declared agents, by the name the registry gives them. An agent's name on the
    desk is its tenant name, as provision has it join.
  - It never starts a turn or writes into a home. It sends on the desk, and whether a turn runs is
    the agent's host's call, on the message's wake.
  - What proves the operator is a sign-in of the board's own (a token, never the password), in a
    file only the board's user can read. One others can read is refused.
  - What became of each message the operator sent is the agent's desk's account of it, and no
    one else's.

    python -I -m hearth.board sign-in --desk URL --user @will:desk     as hearth-board, once
"""
import asyncio
import json
import os
import stat
import threading
import uuid
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import quote

import httpx
from frontdesk import wire
from frontdesk.desk import localpart
from frontdesk.matrix import Matrix, MatrixError

OPERATOR = Path("/var/lib/hearth-board/operator.json")
TIMEOUT_S = 10.0
MAX_TEXT = 20_000
HISTORY = 100


def _q(value: str) -> str:
    return quote(value, safe="")


class TalkError(Exception):
    """Talking can't happen, and says why. ``code`` is what the board answers with."""

    def __init__(self, code: int, reason: str):
        super().__init__(reason)
        self.code, self.reason = code, reason


def agent_id(name: str, operator: str, namespace: str = "") -> str:
    return f"@{localpart(name, namespace)}:{operator.split(':', 1)[1]}"


def refuse_an_agent(user_id: str, namespace: str, declared: Iterable[str]) -> None:
    if user_id in {agent_id(n, user_id, namespace) for n in declared}:
        raise TalkError(503, f"{user_id} is a declared agent's identity; the board talks only as the operator")


class Talk:
    def __init__(self, declared: Callable[[], Iterable[str]], operator: Path = OPERATOR):
        self.declared, self.path = declared, Path(operator)
        self._lock = threading.Lock()   # one direct room per agent, even when two sends race

    def _creds(self) -> dict:
        try:
            mode = self.path.stat().st_mode
        except FileNotFoundError:
            raise TalkError(503, f"no operator is signed in ({self.path}): run hearth.board sign-in") from None
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise TalkError(503, f"{self.path} can be read by users other than the board's; chmod 600 it")
        creds = json.loads(self.path.read_text())
        refuse_an_agent(creds["user_id"], creds.get("namespace", ""), self.declared())
        return creds

    def ready(self) -> Optional[str]:
        """Why talking can't happen right now, or None. Reads only the file, never the desk."""
        try:
            self._creds()
        except (TalkError, OSError, ValueError, KeyError) as exc:
            return getattr(exc, "reason", None) or f"{self.path} can't be read: {exc}"
        return None

    def _agent(self, name: str, creds: dict) -> str:
        if name not in set(self.declared()):
            raise TalkError(404, f"{name!r} isn't a declared agent")
        return agent_id(name, creds["user_id"], creds.get("namespace", ""))

    def _run(self, name: str, act):
        creds = self._creds()
        agent = self._agent(name, creds)

        async def go():
            matrix = Matrix(creds["homeserver"], creds["access_token"])
            try:
                return await act(matrix, creds["user_id"], agent)
            finally:
                await matrix.close()
        try:
            return asyncio.run(go())
        except (MatrixError, httpx.HTTPError) as exc:
            raise TalkError(502, f"the desk didn't take it: {exc}") from exc

    async def _direct(self, matrix: Matrix, me: str) -> dict:
        try:
            return await matrix.call("GET", f"/v3/user/{_q(me)}/account_data/m.direct", timeout=TIMEOUT_S)
        except MatrixError as exc:
            if exc.status == 404:
                return {}
            raise

    async def _room(self, matrix: Matrix, me: str, agent: str, direct: dict) -> Optional[str]:
        """The operator's direct room with the agent that both are still in."""
        for room in direct.get(agent, []):
            try:
                mine = await matrix.get_state(room, "m.room.member", me)
                theirs = await matrix.get_state(room, "m.room.member", agent)
            except MatrixError:
                continue
            if (mine or {}).get("membership") == "join" and (theirs or {}).get("membership") in ("join", "invite"):
                return room
        return None

    def say(self, name: str, text: str) -> str:
        """Send ``text`` to the agent as the operator. Returns the message's id on the desk."""
        if not isinstance(text, str) or not text.strip():
            raise TalkError(400, "say something")
        if len(text) > MAX_TEXT:
            raise TalkError(400, f"longer than {MAX_TEXT} characters")

        async def act(matrix: Matrix, me: str, agent: str) -> str:
            direct = await self._direct(matrix, me)
            room = await self._room(matrix, me, agent, direct)
            if room is None:
                room = await matrix.create_room(preset="private_chat", invite=[agent], is_direct=True)
                direct = {**direct, agent: [*direct.get(agent, []), room]}
                await matrix.call("PUT", f"/v3/user/{_q(me)}/account_data/m.direct", direct, timeout=TIMEOUT_S)
            sent = await matrix.send(room, "m.room.message", uuid.uuid4().hex, {"msgtype": "m.text", "body": text})
            return sent["event_id"]
        with self._lock:
            return self._run(name, act)

    def thread(self, name: str) -> list[dict]:
        """The latest of the thread, oldest first. Each of the operator's messages carries what the
        agent's desk last said became of it."""
        async def act(matrix: Matrix, me: str, agent: str) -> list[dict]:
            room = await self._room(matrix, me, agent, await self._direct(matrix, me))
            if room is None:
                return []
            data = await matrix.call("GET", f"/v3/rooms/{_q(room)}/messages", dir="b", limit=HISTORY,
                                     timeout=TIMEOUT_S)
            states, messages = {}, []
            for event in reversed(data.get("chunk", [])):
                content = event.get("content") or {}
                if event["type"] == wire.EV_STATUS and event["sender"] == agent:
                    states[(content.get("m.relates_to") or {}).get("event_id")] = content.get("state")
                elif event["type"] == "m.room.message":
                    block = content.get(wire.NS) if isinstance(content.get(wire.NS), dict) else {}
                    who = "operator" if event["sender"] == me else "agent" if event["sender"] == agent else event["sender"]
                    messages.append({"id": event["event_id"], "from": who, "text": str(content.get("body") or ""),
                                     "at": event["origin_server_ts"] / 1000, "kind": str(block.get("kind") or wire.MESSAGE)})
            for message in messages:
                if message["from"] == "operator":
                    message["state"] = states.get(message["id"], wire.ACCEPTED)
            return messages
        return self._run(name, act)

    def read(self, name: str, up_to: str) -> None:
        """The operator has read the thread up to ``up_to``: for a person, that is taken in."""
        if not isinstance(up_to, str) or not up_to.startswith("$"):
            raise TalkError(400, "up_to is a message id")

        async def act(matrix: Matrix, me: str, agent: str) -> None:
            room = await self._room(matrix, me, agent, await self._direct(matrix, me))
            if room is None:
                raise TalkError(404, "no thread with that agent yet")
            await matrix.read_receipt(room, up_to)
        self._run(name, act)


def sign_in(desk: str, user_id: str, password: str, declared: Iterable[str], operator: Path = OPERATOR,
            namespace: str = "") -> str:
    """Sign the board in as the operator and keep only the token, readable by the board's user alone."""
    refuse_an_agent(user_id, namespace, declared)

    async def go() -> dict:
        matrix = Matrix(desk)
        try:
            return await matrix.call("POST", "/v3/login", {
                "type": "m.login.password", "identifier": {"type": "m.id.user", "user": user_id},
                "password": password, "initial_device_display_name": "Hearth board"}, timeout=TIMEOUT_S)
        finally:
            await matrix.close()
    data = asyncio.run(go())
    refuse_an_agent(data["user_id"], namespace, declared)   # the desk's name for who signed in, too
    operator = Path(operator)
    tmp = operator.with_name(f".{operator.name}.{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump({"homeserver": desk, "user_id": data["user_id"], "access_token": data["access_token"],
                   "device_id": data.get("device_id"), "namespace": namespace}, fh)
    os.replace(tmp, operator)
    return data["user_id"]
