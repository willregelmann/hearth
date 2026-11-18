"""The socket refuses nothing silently (docs/interfaces/PUSH.md)."""
import asyncio
import json
import os
import socket
import sqlite3
import stat

import pytest

from conftest import ask, push, register, wakes


def raw(home, data: bytes, timeout: float = 15.0) -> dict:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(home.socket))
        sock.sendall(data)
        out = b""
        while not out.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            out += chunk
        return json.loads(out)
    finally:
        sock.close()


async def send_raw(home, data: bytes) -> dict:
    return await asyncio.to_thread(raw, home, data)


@pytest.fixture
async def gateway_with_agent(home, fake, root, start_gateway):
    register(home, "ash", root)
    return await start_gateway()


@pytest.mark.parametrize("request_bytes, says", [
    (b"this is not json\n", "not valid JSON"),
    (b"[1, 2, 3]\n", '"op"'),
    (b"{}\n", '"op"'),
    (b"\n", "empty request"),
    (b'{"op": "no-such-op"}\n', "unknown op"),
    (b'{"op": "wake"}\n', "agent is required"),
    (b'{"op": "wake", "agent": "ghost", "conversation": "c", "source": "s", "key": "k"}\n', "no agent named 'ghost'"),
    (b'{"op": "wake", "agent": "ash", "source": "s", "key": "k"}\n', "conversation"),
    (b'{"op": "wake", "agent": "ash", "conversation": "c", "key": "k"}\n', "source is required"),
    (b'{"op": "wake", "agent": "ash", "conversation": "c", "source": "bad source", "key": "k"}\n', "source"),
    (b'{"op": "wake", "agent": "ash", "conversation": "c", "source": "s", "key": "k", "delay": -5}\n', "delay"),
    (b'{"op": "wake", "agent": "ash", "conversation": "c", "source": "s", "key": "k", "delay": "soon"}\n', "delay"),
    (b'{"op": "wake", "agent": "ash", "conversation": "c", "source": "s", "key": "k", "delay": 1, "not_before": 2}\n',
     "not both"),
    (b'{"op": "wake.list", "states": ["lost"]}\n', "states"),
])
async def test_a_request_that_cannot_be_honoured_gets_an_error_that_says_why_and_changes_nothing(
        home, gateway_with_agent, request_bytes, says):
    response = await send_raw(home, request_bytes)
    assert response["ok"] is False
    assert says in response["error"]
    assert await wakes(home) == []


async def test_a_note_that_is_too_long_is_refused_not_cut_short(home, gateway_with_agent):
    response = await push(home, "ash", "c", note="x" * 5000)
    assert response["ok"] is False and "note" in response["error"]
    assert await wakes(home) == []


async def test_a_request_that_is_too_large_gets_an_error(home, gateway_with_agent):
    response = await send_raw(home, b'{"op": "ping", "pad": "' + b"x" * (2 << 20) + b'"}\n')
    assert response["ok"] is False and "too large" in response["error"]


async def test_the_socket_is_for_its_owner_alone(home, gateway_with_agent):
    assert stat.S_IMODE(os.stat(home.socket).st_mode) == 0o600


async def test_a_wake_is_on_disk_by_the_time_it_is_acknowledged(home, gateway_with_agent):
    ack = await push(home, "ash", "c", note="durable", delay=3600)
    conn = sqlite3.connect(home.db)
    try:
        row = conn.execute("SELECT note, state FROM wakes WHERE id=?", (ack["id"],)).fetchone()
    finally:
        conn.close()
    assert row == ("durable", "pending")


async def test_the_gateway_still_answers_while_a_turn_is_running(home, fake, gateway_with_agent):
    fake.hold()
    await push(home, "ash", "c")
    for _ in range(100):
        if fake.starts:
            break
        await asyncio.sleep(0.02)
    assert (await ask(home, op="ping"))["ok"]
    fake.release()
