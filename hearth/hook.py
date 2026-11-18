"""What the plugin's hooks do (docs/interfaces/PLUGIN.md). They work from files alone, so they run
whether or not the gateway does, and a hook that goes wrong says so on standard error and exits
cleanly: it must never stop a session from starting or ending.
"""
import json
import os
import shlex
import sys
from typing import Mapping, Optional

from hearth import conversation, proc
from hearth.home import Home


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


def guidance(env: Mapping[str, str], session_id: str) -> str:
    cli = _cli(env)
    return (
        f"You are the agent {env['HEARTH_AGENT']!r}, run by Hearth, a gateway that wakes agents. "
        f"This conversation's id is {session_id}.\n"
        "To wait for a time, an answer or a result, set a wake for this conversation and end your turn; never hold a "
        "turn open. Hearth runs a new turn here when the wake is due, once nobody has this conversation open, and "
        "tells you what woke it.\n"
        f"  {cli} wake --source self --conversation {session_id} --in 30m --note 'what you are waiting for'\n"
        f"  {cli} wake --source self --conversation {session_id} --at '<ISO 8601 time>' --note '...'\n"
        "A wake is a label and a note, not the content. Put in the note what your later self will need."
    )


def session_start(stdin_text: str, env: Mapping[str, str], home: Home) -> Optional[str]:
    """Record the session as open, unless it is a turn the gateway runs, and return what the agent is
    told (a JSON document for Claude Code), if it is one of Hearth's agents."""
    session_id = _session_id(stdin_text)
    if session_id is None:
        return None
    if not env.get("HEARTH_TURN"):
        pid = _claude_pid(env)
        conversation.record_open(home.sessions, session_id, pid, proc.start_time(pid), env.get("HEARTH_AGENT"))
    if not env.get("HEARTH_AGENT"):
        return None
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                              "additionalContext": guidance(env, session_id)}})


def session_end(stdin_text: str, env: Mapping[str, str], home: Home) -> None:
    session_id = _session_id(stdin_text)
    if session_id is None or env.get("HEARTH_TURN"):
        return
    conversation.clear_open(home.sessions, session_id, _claude_pid(env))


def run(event: str, stdin_text: str, env: Mapping[str, str] = os.environ) -> int:
    home = Home.from_env(env)
    try:
        if event == "session-start":
            out = session_start(stdin_text, env, home)
            if out:
                print(out)
        elif event == "session-end":
            session_end(stdin_text, env, home)
        else:
            print(f"hearth hook: unknown event {event!r}", file=sys.stderr)
    except Exception as exc:
        print(f"hearth hook {event}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 0
