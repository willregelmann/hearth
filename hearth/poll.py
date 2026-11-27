"""Poll: raise wakes for a source that doesn't push (docs/capabilities/POLL.md).

A check is edge-triggered on its keys. What it last printed is stored with the wakes it raised, in one
transaction, so a restart can neither raise a key again nor forget that it did.
"""
import json
from dataclasses import dataclass
from typing import Optional

from hearth import agent as agents
from hearth import conversation, proc, wake
from hearth.context import Context, log
from hearth.db import transaction


class CheckFailed(Exception):
    pass


@dataclass(frozen=True)
class Line:
    conversation: str
    key: str
    note: Optional[str]


def parse(name: str, stdout: bytes) -> list:
    """The wakes a check printed, one per key. A line that can't be understood fails the whole run,
    and the error says which line but never quotes it."""
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError:
        raise CheckFailed("the output is not UTF-8") from None
    lines, seen = [], set()
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            raise CheckFailed(f"line {number} is not JSON") from None
        if not isinstance(obj, dict):
            raise CheckFailed(f"line {number} is not a JSON object")
        unknown = sorted(set(obj) - {"conversation", "key", "note"})
        if unknown:
            raise CheckFailed(f"line {number} has unknown field {unknown[0]!r}")
        try:
            conv = conversation.check_reference(obj.get("conversation"))
            wake.check_fields(name, obj.get("key"), obj.get("note"))
        except (conversation.ConversationError, wake.WakeError) as exc:
            raise CheckFailed(f"line {number}: {exc}") from None
        if obj["key"] not in seen:
            seen.add(obj["key"])
            lines.append(Line(conv, obj["key"], obj.get("note")))
    return lines


def _record_failure(ctx: Context, agent: str, name: str, error: str) -> None:
    with transaction(ctx.conn):
        ctx.conn.execute("INSERT OR IGNORE INTO check_state(agent, name) VALUES (?,?)", (agent, name))
        ctx.conn.execute("UPDATE check_state SET last_run=?, last_ok=0, last_error=?, last_error_at=? "
                         "WHERE agent=? AND name=?", (ctx.clock(), error, ctx.clock(), agent, name))
    log.error("agent %s: check %s failed: %s", agent, name, error)


def _record_success(ctx: Context, agent: str, name: str, lines: list, parent: Optional[str] = None) -> int:
    """Raise a wake for each key that wasn't there last time, and keep this output as the new last."""
    now = ctx.clock()
    raised = 0
    with transaction(ctx.conn):
        ctx.conn.execute("INSERT OR IGNORE INTO check_state(agent, name) VALUES (?,?)", (agent, name))
        state = ctx.conn.execute("SELECT keys, seq FROM check_state WHERE agent=? AND name=?", (agent, name)).fetchone()
        before, seq = set(json.loads(state["keys"])), state["seq"]
        for line in lines:
            if line.key in before or wake.has_open(ctx.conn, agent, name, line.key):
                continue
            seq += 1
            conv = conversation.resolve(ctx.conn, agent, line.conversation)
            span = ctx.telemetry.wake(agent=agent, source=name, route="poll", conversation=conv.label, parent=parent)
            wake_id, duplicate = wake.accept(ctx.conn, agent=agent, conversation_id=conv.id, source=name,
                                             key=line.key, idem=f"poll:{line.key}#{seq}", note=line.note,
                                             not_before=None, now=now, traceparent=span.traceparent)
            span.accepted(wake_id, duplicate)
            raised += 1
        ctx.conn.execute("UPDATE check_state SET keys=?, seq=?, last_run=?, last_ok=1, last_error=NULL "
                         "WHERE agent=? AND name=?", (json.dumps([l.key for l in lines]), seq, now, agent, name))
    return raised


async def run_check(ctx: Context, agent: agents.Agent, check: agents.Check) -> None:
    started = ctx.clock()
    span = ctx.telemetry.check(agent=agent.name, check=check.name, started=started)
    error, raised = await _run(ctx, agent, check, span.traceparent)
    span.end(error is None, raised, ctx.clock() - started, error)


async def _run(ctx: Context, agent: agents.Agent, check: agents.Check, parent: Optional[str]) -> tuple:
    """Run a check once. Returns (the failure, or None, and how many wakes it raised)."""
    agent.prepare()
    argv = ["/bin/sh", "-c", check.command] if isinstance(check.command, str) else list(check.command)
    ran = await proc.run(argv, cwd=str(agent.workdir), env=agent.environment(ctx.home, turn=False),
                         timeout=check.timeout)
    error = (ran.error or (f"timed out after {check.timeout:g}s" if ran.timed_out else None)
             or (f"exited {ran.rc}" if ran.rc != 0 else None))
    lines = []
    if error is None:
        try:
            lines = parse(check.name, ran.stdout)
        except CheckFailed as exc:
            error = str(exc)
    if error is not None:
        _record_failure(ctx, agent.name, check.name, error)
        return error, 0
    raised = _record_success(ctx, agent.name, check.name, lines, parent)
    if raised:
        log.info("agent %s: check %s raised %d wake%s", agent.name, check.name, raised, "" if raised == 1 else "s")
        ctx.poke()
    return None, raised
