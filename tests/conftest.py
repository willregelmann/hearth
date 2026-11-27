"""Fixtures. The only things faked are the claude program and the clock; everything else is the real
gateway, talked to over its real socket."""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from hearth import agent as agents
from hearth import client, gateway
from hearth.home import Config, Home

FAKE = Path(__file__).parent / "fake_claude.py"
SECRET_REPLY = "SECRET-REPLY-TEXT"


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeClaude:
    def __init__(self, root: Path):
        self.dir = root / "fake"
        self.dir.mkdir()
        self.path = root / "claude"
        self.path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
        self.path.chmod(0o755)

    def mode(self, **values) -> None:
        (self.dir / "mode").write_text(json.dumps(values))

    def hold(self) -> None:
        (self.dir / "hold").touch()

    def release(self) -> None:
        (self.dir / "hold").unlink(missing_ok=True)

    def know_session(self, session_id: str) -> None:
        (self.dir / "sessions").mkdir(exist_ok=True)
        (self.dir / "sessions" / session_id).touch()

    def refuse_configure(self, *ids: str) -> None:
        (self.dir / "unconfigurable").write_text("\n".join(ids))

    def refuse_install(self, *ids: str) -> None:
        (self.dir / "unknown-plugins").write_text("\n".join(ids))

    def entries(self, event: str) -> list:
        try:
            lines = (self.dir / "log.jsonl").read_text().splitlines()
        except FileNotFoundError:
            return []
        return [e for e in map(json.loads, lines) if e["event"] == event]

    @property
    def starts(self) -> list:
        return self.entries("start")

    @property
    def ends(self) -> list:
        return self.entries("end")


@pytest.fixture
def root():
    d = Path(tempfile.mkdtemp(prefix="hr-"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def home(root) -> Home:
    return Home(root / "home")


@pytest.fixture
def fake(root, monkeypatch) -> FakeClaude:
    f = FakeClaude(root)
    monkeypatch.setenv("FAKE_CLAUDE_DIR", str(f.dir))
    monkeypatch.setenv("HEARTH_HOME", "")
    return f


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
async def start_gateway(home, fake, clock):
    """Starts a gateway on the home, on the fake clock. Stopping one and starting another is a restart."""
    running = []

    async def start(**config) -> gateway.Gateway:
        settings = dict(claude=str(fake.path), tick_s=0.02, retry_s=30.0, retry_max_s=1800.0, shutdown_grace_s=0.0)
        settings.update(config)
        gw = gateway.Gateway(home, clock=clock, config=Config(**settings))
        await gw.start()
        running.append(gw)
        return gw

    yield start
    for gw in running:
        if gw.ctx is not None:
            await gw.stop(grace=0)


async def ask(home: Home, **payload) -> dict:
    return await asyncio.to_thread(client.request, home, payload)


async def wait_until(condition, timeout: float = 15.0, what: str = "the condition"):
    """Poll until ``condition()`` is truthy (it may be a coroutine function), and return its value."""
    deadline = time.monotonic() + timeout
    while True:
        value = condition()
        if asyncio.iscoroutine(value):
            value = await value
        if value:
            return value
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        await asyncio.sleep(0.02)


async def quiet(seconds: float = 0.4) -> None:
    """Give the gateway time to do something it should not, so that its not doing it means something."""
    await asyncio.sleep(seconds)


def register(home: Home, name: str, root: Path, **manifest) -> agents.Agent:
    """Register an agent whose directories sit under ``root``. ``manifest`` is extra TOML, as lines."""
    work = root / f"{name}-work"
    work.mkdir(exist_ok=True)
    extra = "\n".join(manifest.get("lines", []))
    text = f'workdir = "{work}"\nconfig_dir = "{root / (name + "-claude")}"\n{extra}\n'
    return agents.add(home, name, text)


async def wakes(home: Home, **payload) -> list:
    return (await ask(home, op="wake.list", states="all", **payload))["wakes"]


async def push(home: Home, agent: str, conversation: str, key: str = None, **extra) -> dict:
    return await ask(home, op="wake", agent=agent, conversation=conversation, source="test",
                     key=key or str(uuid.uuid4()), **extra)


async def status(home: Home) -> dict:
    return await ask(home, op="status")


def agent_status(report: dict, name: str) -> dict:
    return next(a for a in report["agents"] if a["name"] == name)


def hearth_cli(home: Home, *args: str, stdin: str = "", env: dict = None) -> subprocess.CompletedProcess:
    base = {k: v for k, v in os.environ.items()
            if not k.startswith("HEARTH_") and k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PID")}
    full = dict(base, HEARTH_HOME=str(home.root), **(env or {}))
    return subprocess.run([sys.executable, "-m", "hearth", *args], input=stdin, capture_output=True, text=True,
                          env=full, timeout=60)
