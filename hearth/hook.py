"""What the plugin's hooks do (docs/interfaces/PLUGIN.md). They work from files alone, so they run
whether or not the gateway does, and a hook that goes wrong says so on standard error and exits
cleanly: it must never stop a session from starting or ending.
"""
import json
import os
import shlex
import sqlite3
import sys
import time
from typing import Mapping, Optional

from hearth import conversation, proc
from hearth.db import connect, connect_readonly, transaction
from hearth.home import Home

# How much of a session's opening context the list of pending wakes may take. Each wake shown is shown
# whole; what doesn't fit is counted, never dropped silently.
WAKES_BUDGET = 6000


def _session_id(stdin_text: str) -> Optional[str]:
    try:
        data = json.loads(stdin_text)
    except ValueError:
        return None
    sid = data.get("session_id") if isinstance(data, dict) else None
    return sid if isinstance(sid, str) and sid else None


def _claude_pid(env: Mapping[str, str]) -> int:
    """The Claude Code process the hook runs under: it names itself, and its child is the fallback."""
    given = env.get("CLAUDE_PID", "")
    if given.isdigit() and proc.exists(int(given)):
        return int(given)
    return os.getppid()


def _cli(env: Mapping[str, str]) -> str:
    return f"{shlex.quote(env.get('HEARTH_PYTHON') or sys.executable)} -m hearth"


def _when(not_before: Optional[float], now: float) -> str:
    if not_before is None or not_before <= now:
        return "due now"
    return "due " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(not_before))


def pending_wakes(home: Home, agent: str, session_id: str, cli: str = "hearth", now: Optional[float] = None) -> str:
    """The agent's pending wakes in all its conversations: what it has said it will come back to
    (docs/interfaces/PLUGIN.md). When they can't be read, it says so; it never reads as "none"."""
    now = time.time() if now is None else now
    if not home.db.exists():
        return "You have no pending wakes: Hearth has not accepted any wake in this home yet."
    try:
        conn = connect_readonly(home.db)
        try:
            rows = conn.execute(
                "SELECT w.id, w.source, w.note, w.not_before, c.name, c.session_id FROM wakes w "
                "JOIN conversations c ON c.id = w.conversation_id WHERE w.agent=? AND w.state='pending' "
                "ORDER BY COALESCE(w.not_before, 0), w.id", (agent,)).fetchall()
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        return (f"Your pending wakes could not be read ({exc}). This is not a list of them, and it does not mean "
                f"you have none: run `{cli} wake list --agent {agent}` to see them.")
    if not rows:
        return "You have no pending wakes."
    lines = [f"Your pending wakes, in all your conversations ({len(rows)}). Each is something you or someone "
             "else asked to come back to:"]
    used = 0
    for shown, r in enumerate(rows):
        where = r["name"] or r["session_id"] or "a new conversation"
        if r["session_id"] and r["session_id"] == session_id.lower():
            where += ", this conversation"
        line = f"- wake {r['id']} from {r['source']}, in {where}, {_when(r['not_before'], now)}"
        if r["note"]:
            line += f": {r['note']}"
        if used and used + len(line) > WAKES_BUDGET:
            lines.append(f"- and {len(rows) - shown} more, not shown here: run `{cli} wake list "
                         f"--agent {agent}` to see them all.")
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)


def guidance(env: Mapping[str, str], session_id: str, wakes: str = "") -> str:
    cli = _cli(env)
    return (
        f"You are the agent {env['HEARTH_AGENT']!r}, run by Hearth, a gateway that wakes agents. "
        f"This conversation's id is {session_id}.\n"
        "To wait for a time, an answer or a result, set a wake for this conversation and end your turn; never hold a "
        "turn open. Hearth runs a new turn here when the wake is due, once nobody has this conversation open, and "
        "tells you what woke it.\n"
        f"  {cli} wake --source self --conversation {session_id} --in 30m --note 'what you are waiting for'\n"
        f"  {cli} wake --source self --conversation {session_id} --at '<ISO 8601 time>' --note '...'\n"
        "A wake is a label and a note, not the content. Put in the note what your later self will need.\n"
        f"When a wake is no longer wanted, cancel it and say why: {cli} wake cancel ID --reason '...'\n"
        + (f"\n{wakes}" if wakes else "")
    )


def _record_turn_session(home: Home, turn_id: int, session_id: str) -> None:
    """A gateway turn's session is mapped to its conversation now, before the model runs, so a wake the
    agent sets for this session lands in this conversation (docs/primitives/CONVERSATION.md)."""
    conn = connect(home.db)
    try:
        with transaction(conn):
            said = conversation.record_turn_session(conn, turn_id, session_id)
    finally:
        conn.close()
    if said:
        print(f"hearth hook session-start: {said}", file=sys.stderr)


def session_start(stdin_text: str, env: Mapping[str, str], home: Home, record_only: bool = False) -> Optional[str]:
    """Record the session: as open, or for a gateway turn as that turn's conversation. Then return what
    the agent is told (a JSON document for Claude Code), if it is one of Hearth's agents and this is
    not the record-only copy of the hook in its configuration directory."""
    session_id = _session_id(stdin_text)
    if session_id is None:
        return None
    if env.get("HEARTH_TURN"):
        turn = env.get("HEARTH_TURN_ID", "")
        if turn.isdigit():
            try:
                _record_turn_session(home, int(turn), session_id)
            except (sqlite3.Error, OSError) as exc:
                print(f"hearth hook session-start: could not map turn {turn} to its session, so it will be "
                      f"mapped when the turn ends: {exc}", file=sys.stderr)
    else:
        pid = _claude_pid(env)
        conversation.record_open(home.sessions, session_id, pid, proc.start_time(pid), env.get("HEARTH_AGENT"))
    agent = env.get("HEARTH_AGENT")
    if record_only or not agent:
        return None
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                              "additionalContext": guidance(env, session_id,
                                                                            pending_wakes(home, agent, session_id, _cli(env)))}})


def session_end(stdin_text: str, env: Mapping[str, str], home: Home) -> None:
    session_id = _session_id(stdin_text)
    if session_id is None or env.get("HEARTH_TURN"):
        return
    conversation.clear_open(home.sessions, session_id, _claude_pid(env))


def run(event: str, stdin_text: str, env: Mapping[str, str] = os.environ, record_only: bool = False) -> int:
    try:
        home = Home.from_env(env)
        if event == "session-start":
            out = session_start(stdin_text, env, home, record_only)
            if out:
                print(out)
        elif event == "session-end":
            session_end(stdin_text, env, home)
        else:
            print(f"hearth hook: unknown event {event!r}", file=sys.stderr)
    except Exception as exc:
        print(f"hearth hook {event}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 0
