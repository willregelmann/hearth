"""Wake: a durable request for an agent's attention (docs/primitives/WAKE.md).

Every function that changes wakes is called inside a ``db.transaction``, so a wake is on disk before
anyone is told it was accepted, and a wake and whatever else changes with it change together.
"""
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

PENDING, RUNNING, DONE, CANCELED = "pending", "running", "done", "canceled"
STATES = (PENDING, RUNNING, DONE, CANCELED)

SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
MAX_KEY = 256
MAX_NOTE = 2000
# Long enough that a source retrying a push can't be mistaken for a new one; the only rows ever dropped.
FORGET_AFTER_S = 180 * 24 * 3600.0


class WakeError(Exception):
    pass


@dataclass(frozen=True)
class Wake:
    id: int
    agent: str
    conversation_id: int
    source: str
    key: str
    note: Optional[str]
    not_before: Optional[float]
    created_at: float
    state: str
    attempts: int


def _wake(row: sqlite3.Row) -> Wake:
    return Wake(row["id"], row["agent"], row["conversation_id"], row["source"], row["key"], row["note"],
                row["not_before"], row["created_at"], row["state"], row["attempts"])


def check_fields(source, key, note) -> None:
    """Refuse what is malformed or too long. Nothing is cut short to fit."""
    if not isinstance(source, str) or not SOURCE_RE.match(source):
        raise WakeError("a wake's source is a label of letters, digits, . : - and _, at most 64 characters")
    if not isinstance(key, str) or not key or len(key) > MAX_KEY or any(ord(c) < 32 for c in key):
        raise WakeError(f"a wake's key is a non-empty string of at most {MAX_KEY} characters, with no control characters")
    if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE):
        raise WakeError(f"a wake's note is a string of at most {MAX_NOTE} characters")


def accept(conn: sqlite3.Connection, *, agent: str, conversation_id: int, source: str, key: str, idem: str,
           note: Optional[str], not_before: Optional[float], now: float) -> tuple:
    """Persist a wake. Returns (id, duplicate): a wake from the same source for the same agent with
    the same ``idem`` is the one already accepted, however long ago."""
    row = conn.execute("SELECT id FROM wakes WHERE agent=? AND source=? AND idem=?", (agent, source, idem)).fetchone()
    if row is not None:
        return row["id"], True
    cur = conn.execute(
        "INSERT INTO wakes(agent, conversation_id, source, key, idem, note, not_before, created_at, state) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (agent, conversation_id, source, key, idem, note, not_before, now, PENDING))
    return cur.lastrowid, False


def has_open(conn: sqlite3.Connection, agent: str, source: str, key: str) -> bool:
    """Whether a wake with this source and key is still pending or running."""
    return conn.execute("SELECT 1 FROM wakes WHERE agent=? AND source=? AND key=? AND state IN (?,?)",
                        (agent, source, key, PENDING, RUNNING)).fetchone() is not None


def due_conversations(conn: sqlite3.Connection, agent: str, now: float) -> list:
    rows = conn.execute("SELECT DISTINCT conversation_id FROM wakes WHERE agent=? AND state=? "
                        "AND (not_before IS NULL OR not_before <= ?) ORDER BY conversation_id",
                        (agent, PENDING, now)).fetchall()
    return [r[0] for r in rows]


def take(conn: sqlite3.Connection, conversation_id: int, now: float, turn_id: int) -> list:
    """Every due wake pending for the conversation, now running under ``turn_id``."""
    rows = conn.execute("SELECT * FROM wakes WHERE conversation_id=? AND state=? "
                        "AND (not_before IS NULL OR not_before <= ?) ORDER BY id",
                        (conversation_id, PENDING, now)).fetchall()
    for row in rows:
        conn.execute("UPDATE wakes SET state=?, attempts=attempts+1, turn_id=? WHERE id=?", (RUNNING, turn_id, row["id"]))
    return [_wake(r) for r in conn.execute("SELECT * FROM wakes WHERE turn_id=? ORDER BY id", (turn_id,))]


def finish(conn: sqlite3.Connection, turn_id: int, now: float) -> None:
    """The turn finished successfully: what it was shown is done."""
    conn.execute("UPDATE wakes SET state=?, finished_at=? WHERE turn_id=? AND state=?", (DONE, now, turn_id, RUNNING))


def release(conn: sqlite3.Connection, turn_id: int) -> None:
    """The turn failed or was interrupted: what it was shown is owed again."""
    conn.execute("UPDATE wakes SET state=? WHERE turn_id=? AND state=?", (PENDING, turn_id, RUNNING))


def recover(conn: sqlite3.Connection) -> int:
    """After a restart, wakes whose turn was running are pending again. Returns how many."""
    return conn.execute("UPDATE wakes SET state=? WHERE state=?", (PENDING, RUNNING)).rowcount


def cancel(conn: sqlite3.Connection, wake_id, now: float) -> None:
    row = conn.execute("SELECT state FROM wakes WHERE id=?", (wake_id,)).fetchone() if isinstance(wake_id, int) else None
    if row is None:
        raise WakeError(f"no wake {wake_id}")
    if row["state"] == RUNNING:
        raise WakeError(f"wake {wake_id} is running: a turn has it, and it can't be cancelled")
    if row["state"] != PENDING:
        raise WakeError(f"wake {wake_id} is already {row['state']}")
    conn.execute("UPDATE wakes SET state=?, finished_at=? WHERE id=?", (CANCELED, now, wake_id))


def forget_old(conn: sqlite3.Connection, now: float) -> int:
    return conn.execute("DELETE FROM wakes WHERE state IN (?,?) AND finished_at < ?",
                        (DONE, CANCELED, now - FORGET_AFTER_S)).rowcount


def listing(conn: sqlite3.Connection, *, agent: Optional[str] = None, states=(PENDING, RUNNING),
            limit: int = 500) -> list:
    """Wakes with the conversation they are for, oldest first."""
    marks = ",".join("?" * len(states))
    sql = (f"SELECT w.*, c.name AS conv_name, c.session_id AS conv_session, c.failures AS conv_failures, "
           f"c.retry_at AS conv_retry_at FROM wakes w JOIN conversations c ON c.id = w.conversation_id "
           f"WHERE w.state IN ({marks})")
    args: list = list(states)
    if agent is not None:
        sql += " AND w.agent=?"
        args.append(agent)
    sql += " ORDER BY w.id LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()
