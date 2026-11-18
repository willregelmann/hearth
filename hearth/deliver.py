"""Deliver: put the wakes that are due for a conversation in front of its agent, in one turn
(docs/capabilities/DELIVER.md). The wakes count as done only if that turn finishes.
"""
import asyncio
import time
from typing import Optional

from hearth import agent as agents
from hearth import claude, conversation, proc, wake
from hearth.context import Context, LiveTurn, log
from hearth.db import transaction

NOT_DELIVERED = ("Your reply text is not delivered to anyone: whatever someone should see, send it through a "
                 "tool that reaches them.")
LABEL_AND_NOTE = ("A wake is a label and a note, not the content. Use the source's own tools to see what it is "
                  "about.")
MAY_BE_SEEN = "This wake may have been shown to an earlier turn that did not finish, so some of it may be done."
LATE_AFTER_S = 1.0


def stamp(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h {s % 3600 // 60}m"
    return f"{s // 86400}d {s % 86400 // 3600}h"


def compose_prompt(wakes: list, conv: conversation.Conversation, now: float, missing: list) -> str:
    """What the turn is told. It names every wake's source and note, says which may have been shown
    before and which are late, and says nobody reads the reply."""
    plural = "wakes" if len(wakes) != 1 else "wake"
    lines = [f"Hearth started this turn because {len(wakes)} {plural} came for this conversation."]
    if conv.session_id is None and conv.name:
        lines.append(f"This is the first turn of the conversation named {conv.name!r}.")
    lines.append("")
    for w in wakes:
        item = f"- {w.source}"
        if w.note:
            item += f": {w.note}"
        lines.append(item)
        if w.attempts > 1:
            lines.append(f"  {MAY_BE_SEEN}")
        if w.not_before is not None and now - w.not_before >= LATE_AFTER_S:
            lines.append(f"  It was due at {stamp(w.not_before)} and this turn started {duration(now - w.not_before)} late.")
    lines += ["", LABEL_AND_NOTE, NOT_DELIVERED]
    if missing:
        lines += ["", "Plugins this agent declares that are not available in this turn: " + ", ".join(missing) + "."]
    return "\n".join(lines)


def _finish_turn(ctx: Context, turn_id: int, outcome: str, detail: str, session_id: Optional[str]) -> None:
    ctx.conn.execute("UPDATE turns SET ended_at=?, outcome=?, detail=?, session_id=COALESCE(?, session_id) WHERE id=?",
                     (ctx.clock(), outcome, detail, session_id, turn_id))


def _settle(ctx: Context, conv_id: int, turn_id: int, outcome: str, detail: str, session_id: Optional[str]) -> None:
    """Record how the turn ended, and what that means for the wakes it was shown. Interrupted is not a
    failure of the conversation: the gateway stopped, nothing was wrong with it."""
    with transaction(ctx.conn):
        _finish_turn(ctx, turn_id, outcome, detail, session_id)
        conversation.record_session(ctx.conn, conv_id, session_id)
        if outcome == "ok":
            wake.finish(ctx.conn, turn_id, ctx.clock())
            conversation.note_success(ctx.conn, conv_id)
        else:
            wake.release(ctx.conn, turn_id)
            if outcome != "interrupted":
                conversation.note_failure(ctx.conn, conv_id, ctx.clock(), ctx.config.retry_s, ctx.config.retry_max_s)


async def deliver(ctx: Context, agent: agents.Agent, conv_id: int) -> None:
    now = ctx.clock()
    with transaction(ctx.conn):
        conv = conversation.get(ctx.conn, conv_id)
        turn_id = ctx.conn.execute(
            "INSERT INTO turns(agent, conversation_id, session_id, source, started_at) VALUES (?,?,?,?,?)",
            (agent.name, conv_id, conv.session_id, "", now)).lastrowid
        wakes = wake.take(ctx.conn, conv_id, now, turn_id)
        if wakes:
            sources = ",".join(dict.fromkeys(w.source for w in wakes))[:200]
            ctx.conn.execute("UPDATE turns SET source=? WHERE id=?", (sources, turn_id))
        else:
            ctx.conn.execute("DELETE FROM turns WHERE id=?", (turn_id,))
    if not wakes:
        return
    ctx.live[conv_id] = LiveTurn(agent.name, conv_id, conv.label, sources, now)
    try:
        outcome, detail, session_id = await _run(ctx, agent, conv, wakes, turn_id, now)
    except asyncio.CancelledError:
        _settle(ctx, conv_id, turn_id, "interrupted", "the gateway stopped during the turn", None)
        raise
    except Exception as exc:
        log.exception("turn %d for %s could not be run", turn_id, agent.name)
        outcome, detail, session_id = "failed", f"internal error ({type(exc).__name__})", None
    finally:
        ctx.live.pop(conv_id, None)
    _settle(ctx, conv_id, turn_id, outcome, detail, session_id)
    if outcome == "ok":
        log.info("agent %s: turn %d finished (%d wake%s)", agent.name, turn_id, len(wakes), "" if len(wakes) == 1 else "s")
    else:
        after = conversation.get(ctx.conn, conv_id)
        log.error("agent %s: turn %d %s: %s; %d wake%s stay pending, next try at %s", agent.name, turn_id, outcome,
                  detail, len(wakes), "" if len(wakes) == 1 else "s", stamp(after.retry_at or ctx.clock()))
    ctx.poke()


async def _run(ctx: Context, agent: agents.Agent, conv: conversation.Conversation, wakes: list, turn_id: int,
               now: float) -> tuple:
    agent.prepare()
    env = agent.environment(ctx.home, turn=True)
    try:
        installed = await asyncio.to_thread(agents.installed_plugins, ctx.claude, env)
    except RuntimeError as exc:
        return "failed", str(exc), None
    missing = [s.declared for s in agents.plugin_states(agent, installed, None) if not s.loaded]
    prompt = compose_prompt(wakes, conv, now, missing)
    cmd = claude.turn_command(ctx.claude, agent, agents.plugin_settings(agent, installed), conv.session_id, prompt)

    def started(pid: int) -> None:
        ctx.conn.execute("UPDATE turns SET pid=?, pstart=? WHERE id=?", (pid, proc.start_time(pid), turn_id))

    ran = await proc.run(cmd, cwd=str(agent.workdir), env=env, timeout=agent.turn_timeout, on_start=started)
    if ran.error:
        return "failed", ran.error, None
    if ran.timed_out:
        return "timeout", f"killed after {agent.turn_timeout:g}s", None
    result = claude.outcome(ran.rc, ran.stdout)
    return ("ok" if result.ok else "failed"), result.detail, result.session_id
