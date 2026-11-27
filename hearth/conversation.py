"""Conversation: a Claude Code session of one agent, and the rules about who may write to it
(docs/primitives/CONVERSATION.md).

Also here: the records of which sessions a person has open. They are written by the plugin's hooks and
read by the gateway before it resumes anything.
"""
import json
import os
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from hearth import proc

SESSION_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
MAX_NAME = 128


class ConversationError(Exception):
    pass


@dataclass(frozen=True)
class Conversation:
    id: int
    agent: str
    name: Optional[str]
    session_id: Optional[str]
    failures: int
    retry_at: Optional[float]

    @property
    def label(self) -> str:
        return self.name or self.session_id or f"#{self.id}"


def _row(row: sqlite3.Row) -> Conversation:
    return Conversation(row["id"], row["agent"], row["name"], row["session_id"], row["failures"], row["retry_at"])


def check_reference(ref) -> str:
    if not isinstance(ref, str) or not ref.strip():
        raise ConversationError("a conversation is named by a session id or a name, and none was given")
    if len(ref) > MAX_NAME or any(ord(c) < 32 for c in ref) or ref != ref.strip():
        raise ConversationError(f"a conversation name is at most {MAX_NAME} characters, with no control "
                                "characters and no space at either end")
    return ref


def resolve(conn: sqlite3.Connection, agent: str, ref: str) -> Conversation:
    """The conversation ``ref`` means for ``agent``, made if it is new. Call inside a transaction."""
    ref = check_reference(ref)
    row = conn.execute("SELECT * FROM conversations WHERE agent=? AND name=?", (agent, ref)).fetchone()
    if row is None and SESSION_ID_RE.match(ref):
        ref = ref.lower()
        row = conn.execute("SELECT * FROM conversations WHERE agent=? AND session_id=?", (agent, ref)).fetchone()
        if row is None:
            cur = conn.execute("INSERT INTO conversations(agent, session_id) VALUES (?, ?)", (agent, ref))
            row = conn.execute("SELECT * FROM conversations WHERE id=?", (cur.lastrowid,)).fetchone()
    elif row is None:
        cur = conn.execute("INSERT INTO conversations(agent, name) VALUES (?, ?)", (agent, ref))
        row = conn.execute("SELECT * FROM conversations WHERE id=?", (cur.lastrowid,)).fetchone()
    return _row(row)


def lookup(conn: sqlite3.Connection, agent: str, ref: str) -> Optional[str]:
    """The session id ``ref`` stands for, without making anything. None for a name with no session yet."""
    ref = check_reference(ref)
    row = conn.execute("SELECT session_id FROM conversations WHERE agent=? AND name=?", (agent, ref)).fetchone()
    if row is not None:
        return row["session_id"]
    return ref.lower() if SESSION_ID_RE.match(ref) else None


def get(conn: sqlite3.Connection, conversation_id: int) -> Conversation:
    return _row(conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone())


def record_session(conn: sqlite3.Connection, conversation_id: int, session_id: Optional[str]) -> Optional[str]:
    """Map a conversation with no session yet to the session its turn is in: that is how a name's
    first turn becomes the session the name stands for. A session is exactly one conversation, so if
    another conversation already holds this session (a wake named it by its id before it was mapped
    here), that one is merged into this one. Call inside a transaction.

    Returns None when nothing needed doing or it was done quietly, and otherwise a sentence for the log
    saying what was merged or why the session could not be mapped."""
    if not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
        return None
    session_id = session_id.lower()
    mine = conn.execute("SELECT agent, session_id FROM conversations WHERE id=?", (conversation_id,)).fetchone()
    if mine is None or mine["session_id"] is not None:
        return None
    other = conn.execute("SELECT id, name FROM conversations WHERE agent=? AND session_id=? AND id<>?",
                         (mine["agent"], session_id, conversation_id)).fetchone()
    note = None
    if other is not None:
        if other["name"] is not None or conn.execute(
                "SELECT 1 FROM wakes WHERE conversation_id=? AND state='running'", (other["id"],)).fetchone():
            return (f"session {session_id} is already conversation {other['name'] or other['id']}; "
                    f"conversation {conversation_id} was left without it")
        conn.execute("UPDATE wakes SET conversation_id=? WHERE conversation_id=?", (conversation_id, other["id"]))
        conn.execute("UPDATE turns SET conversation_id=? WHERE conversation_id=?", (conversation_id, other["id"]))
        conn.execute("DELETE FROM conversations WHERE id=?", (other["id"],))
        note = f"session {session_id} was also conversation {other['id']}; merged into conversation {conversation_id}"
    conn.execute("UPDATE conversations SET session_id=? WHERE id=?", (session_id, conversation_id))
    return note


def record_turn_session(conn: sqlite3.Connection, turn_id: int, session_id: Optional[str]) -> Optional[str]:
    """What a gateway turn's session-start hook calls: the turn is in ``session_id``, so its
    conversation is mapped to it before the agent can act. Call inside a transaction."""
    row = conn.execute("SELECT conversation_id FROM turns WHERE id=? AND outcome IS NULL", (turn_id,)).fetchone()
    if row is None or not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
        return None
    conn.execute("UPDATE turns SET session_id=? WHERE id=?", (session_id.lower(), turn_id))
    return record_session(conn, row["conversation_id"], session_id)


def note_failure(conn: sqlite3.Connection, conversation_id: int, now: float, retry_s: float,
                 retry_max_s: float) -> float:
    """A turn failed. The conversation waits twice as long as after the failure before, up to a cap.
    Returns when it may be tried again."""
    failures = conn.execute("SELECT failures FROM conversations WHERE id=?", (conversation_id,)).fetchone()[0] + 1
    retry_at = now + min(retry_s * 2 ** min(failures - 1, 60), retry_max_s)
    conn.execute("UPDATE conversations SET failures=?, retry_at=? WHERE id=?", (failures, retry_at, conversation_id))
    return retry_at


def note_success(conn: sqlite3.Connection, conversation_id: int) -> None:
    conn.execute("UPDATE conversations SET failures=0, retry_at=NULL WHERE id=?", (conversation_id,))


class Exclusion:
    """The conversations that have a turn running. A conversation is entered by at most one turn."""

    def __init__(self):
        self._inside: set = set()

    def enter(self, conversation_id: int) -> bool:
        if conversation_id in self._inside:
            return False
        self._inside.add(conversation_id)
        return True

    def leave(self, conversation_id: int) -> None:
        self._inside.discard(conversation_id)

    def __contains__(self, conversation_id: int) -> bool:
        return conversation_id in self._inside


@dataclass(frozen=True)
class OpenSession:
    session_id: str
    pid: int
    started: Optional[str]
    agent: Optional[str]


def record_open(sessions_dir: Path, session_id: str, pid: int, started: Optional[str], agent: Optional[str]) -> None:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"session": session_id, "pid": pid, "started": started, "agent": agent})
    fd, tmp = tempfile.mkstemp(dir=sessions_dir, prefix=".record-")
    with os.fdopen(fd, "w") as f:
        f.write(body)
    os.replace(tmp, sessions_dir / f"{session_id}.{pid}.json")


def clear_open(sessions_dir: Path, session_id: str, pid: Optional[int] = None) -> None:
    pattern = f"{session_id}.{pid}.json" if pid is not None else f"{session_id}.*.json"
    for path in sessions_dir.glob(pattern):
        path.unlink(missing_ok=True)


def _records(sessions_dir: Path):
    try:
        entries = sorted(sessions_dir.glob("*.json"))
    except OSError:
        return
    for path in entries:
        try:
            data = json.loads(path.read_text())
            yield path, OpenSession(data["session"], int(data["pid"]), data.get("started"), data.get("agent"))
        except (OSError, ValueError, KeyError, TypeError):
            continue


def open_sessions(sessions_dir: Path, session_id: Optional[str] = None) -> list:
    """The sessions a person has open: recorded, and still running as the process that was recorded.
    A record whose process has gone is removed. With ``session_id``, only that session is looked at."""
    found = []
    for path, record in _records(sessions_dir):
        if session_id is not None and record.session_id.lower() != session_id.lower():
            continue
        if proc.is_same_process(record.pid, record.started):
            found.append(record)
        else:
            path.unlink(missing_ok=True)
    return found


def is_open(sessions_dir: Path, session_id: str) -> bool:
    return bool(open_sessions(sessions_dir, session_id))
