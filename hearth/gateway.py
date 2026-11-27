"""The gateway: one process that knows the registered agents, takes wakes in over a socket and from
checks, and runs the turns that deliver them.

It owns the process-level facts: one gateway per home, the socket, the loop that starts work when it
is due, and the registry of loaded agents. What a turn, a wake or a conversation must satisfy is held
in deliver, wake and conversation.
"""
import asyncio
import fcntl
import json
import math
import os
import signal
import time
from dataclasses import dataclass
from typing import Callable, Optional

from hearth import agent as agents
from hearth import claude, conversation, deliver, poll, proc, wake
from hearth.context import Context, log
from hearth.db import connect, transaction
from hearth.home import Config, Home

MAX_REQUEST = 1 << 20
REQUEST_TIMEOUT_S = 10.0
RECENT_TURNS = 10
PRUNE_EVERY_S = 3600.0


class GatewayError(Exception):
    pass


class RequestError(Exception):
    """A request that can't be honoured. Its message goes back to the caller as the answer."""


@dataclass
class CheckRuntime:
    definition: agents.Check
    next_run: float = 0.0
    task: Optional[asyncio.Task] = None


def _number(req: dict, field: str) -> Optional[float]:
    value = req.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise RequestError(f"{field} must be a number of seconds, zero or more")
    return float(value)


def _text(req: dict, field: str, required: bool = True) -> Optional[str]:
    value = req.get(field)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value:
        raise RequestError(f"{field} is required and must be a string")
    return value


class Gateway:
    def __init__(self, home: Home, *, clock: Callable[[], float] = time.time, config: Optional[Config] = None,
                 claude_path: Optional[str] = None):
        self.home = home
        self.clock = clock
        self.config = config or home.config()
        self.claude = claude.program(claude_path or self.config.claude)
        self.agents: dict = {}
        self.broken: dict = {}
        self.manifest_errors: dict = {}
        self.plugins: dict = {}
        self.checks: dict = {}
        self.started_at: Optional[float] = None
        self._deferred: dict = {}
        self._server: Optional[asyncio.AbstractServer] = None
        self._loop_task: Optional[asyncio.Task] = None
        self._turn_tasks: set = set()
        self._poke = asyncio.Event()
        self._lock_fd: Optional[int] = None
        self._last_prune = 0.0
        self.ctx: Optional[Context] = None

    async def start(self) -> None:
        self.home.ensure()
        self._lock()
        try:
            conn = connect(self.home.db)
            self.ctx = Context(self.home, conn, self.clock, self.config, self.claude, self._poke.set)
            self._recover()
            self.started_at = self.clock()
            await self.reload_all()
            await self._listen()
        except BaseException:
            self._release()
            raise
        self._loop_task = asyncio.get_running_loop().create_task(self._loop())
        log.info("gateway started for %s with %d agent%s", self.home.root, len(self.agents),
                 "" if len(self.agents) == 1 else "s")

    async def stop(self, grace: Optional[float] = None) -> None:
        grace = self.config.shutdown_grace_s if grace is None else grace
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._loop_task is not None:
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)
            self._loop_task = None
        turns = set(self._turn_tasks)
        if turns and grace > 0:
            _, turns = await asyncio.wait(turns, timeout=grace)
        for task in list(turns) + [r.task for r in self.checks.values() if r.task and not r.task.done()]:
            task.cancel()
        await asyncio.gather(*self._turn_tasks, *[r.task for r in self.checks.values() if r.task],
                             return_exceptions=True)
        if self.ctx is not None:
            self.ctx.conn.close()
            self.ctx = None
        self.home.socket.unlink(missing_ok=True)
        self._release()
        log.info("gateway stopped")

    def _lock(self) -> None:
        fd = os.open(self.home.lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise GatewayError(f"another gateway is already running for {self.home.root}") from None
        self._lock_fd = fd

    def _release(self) -> None:
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    def _recover(self) -> None:
        """Pick up after a gateway that stopped, however it stopped. A turn it left running is still
        a claude process unless it was killed with the gateway: it is killed here, because it would
        write to the transcript beside the turn that replaces it."""
        conn = self.ctx.conn
        for row in conn.execute("SELECT id, pid, pstart FROM turns WHERE outcome IS NULL").fetchall():
            if row["pid"] and proc.is_recorded_process(row["pid"], row["pstart"]):
                proc.kill_group(row["pid"])
                log.warning("killed turn %d, left running by an earlier gateway", row["id"])
        now = self.clock()
        with transaction(conn):
            conn.execute("UPDATE turns SET ended_at=?, outcome='interrupted', detail=? WHERE outcome IS NULL",
                         (now, "the gateway stopped during the turn"))
            again = wake.recover(conn)
            wake.forget_old(conn, now)
        if again:
            log.info("%d wake%s were mid-turn when the gateway stopped and will run again", again,
                     "" if again == 1 else "s")

    async def _listen(self) -> None:
        self.home.socket.unlink(missing_ok=True)
        old = os.umask(0o177)
        try:
            self._server = await asyncio.start_unix_server(self._client, path=str(self.home.socket), limit=MAX_REQUEST)
        except OSError as exc:
            raise GatewayError(f"cannot listen on {self.home.socket}: {exc.strerror or exc}") from exc
        finally:
            os.umask(old)
        os.chmod(self.home.socket, 0o600)

    # Agents ---------------------------------------------------------------------------------------

    async def reload_all(self) -> None:
        on_disk = agents.names(self.home)
        for name in list(self.agents) + list(self.broken):
            if name not in on_disk:
                self._unload(name)
        for name in on_disk:
            await self._load(name)

    def _unload(self, name: str) -> None:
        self.agents.pop(name, None)
        self.broken.pop(name, None)
        self.manifest_errors.pop(name, None)
        self.plugins.pop(name, None)
        self._forget_checks(name, keep=())

    def _forget_checks(self, name: str, keep) -> None:
        for key in [k for k in self.checks if k[0] == name and k[1] not in keep]:
            rt = self.checks[key]
            if rt.task is None or rt.task.done():
                del self.checks[key]

    async def _load(self, name: str) -> Optional[str]:
        """Read an agent's manifest and put it into service. A manifest that can't be read leaves a
        loaded agent as it was. Returns the problem, if any."""
        try:
            agent = agents.load(self.home, name)
        except agents.ManifestError as exc:
            if name in self.agents:
                self.manifest_errors[name] = str(exc)
            else:
                self.broken[name] = str(exc)
            log.error("agent %s: %s", name, exc)
            return str(exc)
        self.broken.pop(name, None)
        self.manifest_errors.pop(name, None)
        self.agents[name] = agent
        for check in agent.checks:
            current = self.checks.get((name, check.name))
            if current is None or current.definition != check:
                self.checks[(name, check.name)] = CheckRuntime(check, 0.0, current.task if current else None)
        self._forget_checks(name, keep={c.name for c in agent.checks})
        await self.inspect(agent)
        return None

    async def inspect(self, agent: agents.Agent) -> None:
        """Find out which of an agent's declared plugins will load."""
        installed, problem = [], None
        if any(p.id for p in agent.plugins):
            try:
                installed = await asyncio.to_thread(agents.installed_plugins, self.claude,
                                                    agent.environment(self.home, turn=False))
            except RuntimeError as exc:
                installed, problem = None, str(exc)
        self.plugins[agent.name] = agents.plugin_states(agent, installed, problem)

    def known(self, name: str) -> bool:
        return name in self.agents or name in self.broken

    # The loop -------------------------------------------------------------------------------------

    async def _loop(self) -> None:
        while True:
            try:
                self._dispatch()
            except Exception:
                log.exception("the dispatch loop failed; it carries on")
            self._poke.clear()
            try:
                await asyncio.wait_for(self._poke.wait(), self.config.tick_s)
            except asyncio.TimeoutError:
                pass

    def _dispatch(self) -> None:
        now = self.clock()
        deferred: dict = {}
        for agent in list(self.agents.values()):
            for conv_id in wake.due_conversations(self.ctx.conn, agent.name, now):
                if conv_id in self.ctx.exclusion:
                    continue
                conv = conversation.get(self.ctx.conn, conv_id)
                if conv.retry_at is not None and conv.retry_at > now:
                    continue
                if conv.session_id and conversation.is_open(self.home.sessions, conv.session_id):
                    deferred[conv_id] = conv.label
                    continue
                self._start_turn(agent, conv_id)
            for check in agent.checks:
                rt = self.checks.get((agent.name, check.name))
                if rt and (rt.task is None or rt.task.done()) and rt.next_run <= now:
                    rt.next_run = now + check.interval
                    rt.task = asyncio.get_running_loop().create_task(self._check_task(agent, rt.definition))
        self._deferred = deferred
        if now - self._last_prune > PRUNE_EVERY_S:
            self._last_prune = now
            with transaction(self.ctx.conn):
                wake.forget_old(self.ctx.conn, now)

    def _start_turn(self, agent: agents.Agent, conv_id: int) -> None:
        if not self.ctx.exclusion.enter(conv_id):
            return
        task = asyncio.get_running_loop().create_task(self._turn_task(agent, conv_id))
        self._turn_tasks.add(task)
        task.add_done_callback(self._turn_tasks.discard)

    async def _turn_task(self, agent: agents.Agent, conv_id: int) -> None:
        try:
            await deliver.deliver(self.ctx, agent, conv_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("agent %s: delivering to conversation %d failed", agent.name, conv_id)
        finally:
            self.ctx.exclusion.leave(conv_id)

    async def _check_task(self, agent: agents.Agent, check: agents.Check) -> None:
        try:
            await poll.run_check(self.ctx, agent, check)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("agent %s: check %s failed to run", agent.name, check.name)

    # The socket -----------------------------------------------------------------------------------

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            response = await self._read_and_answer(reader)
            writer.write((json.dumps(response) + "\n").encode())
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def _read_and_answer(self, reader: asyncio.StreamReader) -> dict:
        try:
            line = await asyncio.wait_for(reader.readline(), REQUEST_TIMEOUT_S)
        except asyncio.TimeoutError:
            return {"ok": False, "error": "no request arrived in time: send one JSON object and a newline"}
        except ValueError:
            await self._discard(reader)
            return {"ok": False, "error": f"the request is too large (the limit is {MAX_REQUEST} bytes)"}
        if not line.strip():
            return {"ok": False, "error": "empty request: send one JSON object and a newline"}
        try:
            request = json.loads(line)
        except ValueError:
            return {"ok": False, "error": "the request is not valid JSON"}
        if not isinstance(request, dict) or not isinstance(request.get("op"), str):
            return {"ok": False, "error": 'the request must be a JSON object with an "op"'}
        try:
            return {"ok": True, **(await self._handle(request))}
        except (RequestError, wake.WakeError, conversation.ConversationError) as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            log.exception("request %r failed", request.get("op"))
            return {"ok": False, "error": "internal error: the gateway could not handle the request; see its log"}

    @staticmethod
    async def _discard(reader: asyncio.StreamReader) -> None:
        """Read off what a sender of an oversized request is still sending, for a little while, so that
        it is still there to read the refusal."""
        async def drain() -> None:
            while await reader.read(65536):
                pass
        try:
            await asyncio.wait_for(drain(), 2.0)
        except (asyncio.TimeoutError, ConnectionError):
            pass

    async def _handle(self, req: dict) -> dict:
        op = req["op"]
        handler = {
            "ping": self._ping, "wake": self._wake, "wake.list": self._wake_list, "wake.cancel": self._wake_cancel,
            "agent.reload": self._agent_reload, "agent.list": self._agent_list, "status": self._status,
        }.get(op)
        if handler is None:
            raise RequestError(f"unknown op {op!r}")
        return await handler(req)

    async def _ping(self, req: dict) -> dict:
        return {"pid": os.getpid()}

    async def _wake(self, req: dict) -> dict:
        agent = _text(req, "agent")
        if not self.known(agent):
            raise RequestError(f"no agent named {agent!r} is registered")
        source, key = _text(req, "source"), _text(req, "key")
        note = req.get("note")
        wake.check_fields(source, key, note)
        delay, not_before = _number(req, "delay"), _number(req, "not_before")
        if delay is not None and not_before is not None:
            raise RequestError("give a delay or a not_before time, not both")
        now = self.clock()
        if delay is not None:
            not_before = now + delay
        with transaction(self.ctx.conn):
            conv = conversation.resolve(self.ctx.conn, agent, _text(req, "conversation"))
            wake_id, duplicate = wake.accept(self.ctx.conn, agent=agent, conversation_id=conv.id, source=source,
                                             key=key, idem=f"push:{key}", note=note, not_before=not_before, now=now)
        state = self.ctx.conn.execute("SELECT state FROM wakes WHERE id=?", (wake_id,)).fetchone()["state"]
        if not duplicate:
            self._poke.set()
        return {"id": wake_id, "duplicate": duplicate, "state": state, "conversation": conv.label,
                "not_before": not_before}

    def _wake_view(self, row, now: float) -> dict:
        label = row["conv_name"] or row["conv_session"] or f"#{row['conversation_id']}"
        next_try = None
        if row["state"] == wake.PENDING:
            t = max(row["not_before"] or 0.0, row["conv_retry_at"] or 0.0)
            next_try = t if t > now else None
        failure = None
        if row["conv_failures"]:
            last = self.ctx.conn.execute("SELECT detail FROM turns WHERE conversation_id=? AND outcome IS NOT NULL "
                                         "AND outcome NOT IN ('ok','interrupted') ORDER BY id DESC LIMIT 1",
                                         (row["conversation_id"],)).fetchone()
            failure = last["detail"] if last else None
        return {"id": row["id"], "agent": row["agent"], "conversation": label, "source": row["source"],
                "key": row["key"], "note": row["note"], "state": row["state"], "not_before": row["not_before"],
                "created_at": row["created_at"], "attempts": row["attempts"], "next_try": next_try,
                "failures": row["conv_failures"], "last_failure": failure,
                "deferred": row["conversation_id"] in self._deferred,
                "cancel_reason": row["cancel_reason"], "canceled_by": row["canceled_by"]}

    async def _wake_list(self, req: dict) -> dict:
        states = req.get("states")
        if states is None:
            states = [wake.PENDING, wake.RUNNING]
        elif states == "all":
            states = list(wake.STATES)
        if not isinstance(states, list) or not states or any(s not in wake.STATES for s in states):
            raise RequestError(f"states must be a list drawn from {', '.join(wake.STATES)}, or \"all\"")
        agent = _text(req, "agent", required=False)
        now = self.clock()
        rows = wake.listing(self.ctx.conn, agent=agent, states=states)
        return {"wakes": [self._wake_view(r, now) for r in rows]}

    async def _wake_cancel(self, req: dict) -> dict:
        """An operator cancels any pending wake; an agent, naming itself as ``agent``, only its own."""
        wake_id = req.get("id")
        agent = _text(req, "agent", required=False)
        with transaction(self.ctx.conn):
            wake.cancel(self.ctx.conn, wake_id if isinstance(wake_id, int) and not isinstance(wake_id, bool) else None,
                        self.clock(), reason=req.get("reason"), by=agent or "operator", agent=agent)
        return {"id": wake_id, "state": wake.CANCELED}

    async def _agent_reload(self, req: dict) -> dict:
        name = _text(req, "agent", required=False)
        if name is None:
            await self.reload_all()
            return {"agents": sorted(self.agents)}
        if not agents.exists(self.home, name):
            if not self.known(name):
                raise RequestError(f"no agent named {name!r} is registered")
            self._unload(name)
            return {"agent": name, "state": "removed"}
        problem = await self._load(name)
        if problem:
            raise RequestError(f"{problem}; the agent is left as it was")
        self._poke.set()
        return {"agent": name, "state": "loaded"}

    async def _agent_list(self, req: dict) -> dict:
        out = []
        for name in sorted(set(self.agents) | set(self.broken)):
            error = self.broken.get(name) or self.manifest_errors.get(name)
            out.append({"name": name, "state": "error" if name in self.broken else "loaded", "error": error})
        return {"agents": out}

    # Status ---------------------------------------------------------------------------------------

    async def _status(self, req: dict) -> dict:
        await asyncio.gather(*(self.inspect(a) for a in list(self.agents.values())))
        now = self.clock()
        view = []
        for name in sorted(set(self.agents) | set(self.broken)):
            view.append(self._agent_status(name, now))
        return {"started": self.started_at, "now": now, "pid": os.getpid(), "agents": view}

    def _agent_status(self, name: str, now: float) -> dict:
        conn = self.ctx.conn
        agent = self.agents.get(name)
        out: dict = {"name": name, "error": self.broken.get(name) or self.manifest_errors.get(name)}
        if agent is None:
            return out
        belongs = {r[0] for r in conn.execute("SELECT session_id FROM conversations WHERE agent=? AND session_id "
                                              "IS NOT NULL", (name,))}
        checks = []
        for check in agent.checks:
            row = conn.execute("SELECT * FROM check_state WHERE agent=? AND name=?", (name, check.name)).fetchone()
            checks.append({"name": check.name, "interval": check.interval,
                           "last_run": row["last_run"] if row else None,
                           "last_ok": None if not row or row["last_ok"] is None else bool(row["last_ok"]),
                           "last_error": row["last_error"] if row else None,
                           "last_error_at": row["last_error_at"] if row else None})
        turns = conn.execute("SELECT t.*, c.name AS conv_name, c.session_id AS conv_session FROM turns t "
                             "JOIN conversations c ON c.id = t.conversation_id WHERE t.agent=? AND t.outcome IS NOT "
                             "NULL ORDER BY t.id DESC LIMIT ?", (name, RECENT_TURNS)).fetchall()
        out.update({
            "manifest": str(agent.manifest), "workdir": str(agent.workdir), "config_dir": str(agent.config_dir),
            "plugins": [{"declared": s.declared, "loaded": s.loaded, "detail": s.detail}
                        for s in self.plugins.get(name, [])],
            "checks": checks,
            "live_turns": [{"conversation": t.conversation, "source": t.source, "started": t.started}
                           for t in self.ctx.live.values() if t.agent == name],
            "open_sessions": [{"session": s.session_id, "pid": s.pid}
                              for s in conversation.open_sessions(self.home.sessions)
                              if s.agent == name or s.session_id in belongs],
            "wakes": [self._wake_view(r, now) for r in wake.listing(conn, agent=name)],
            "recent_turns": [{"id": t["id"], "conversation": t["conv_name"] or t["conv_session"] or t["conversation_id"],
                              "session_id": t["session_id"], "source": t["source"], "started": t["started_at"],
                              "ended": t["ended_at"], "outcome": t["outcome"], "detail": t["detail"]} for t in turns],
        })
        return out


async def serve(home: Home) -> None:
    """Run a gateway until it is told to stop."""
    gateway = Gateway(home)
    await gateway.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await stop.wait()
    finally:
        await gateway.stop()
