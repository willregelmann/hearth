"""The gateway's one database. The tables belong to the primitives that read them (agent, conversation,
wake) and to poll; this module only opens the file and says what is in it."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    agent TEXT NOT NULL,
    name TEXT,
    session_id TEXT,
    failures INTEGER NOT NULL DEFAULT 0,
    retry_at REAL,
    UNIQUE (agent, name),
    UNIQUE (agent, session_id)
);

CREATE TABLE IF NOT EXISTS wakes (
    id INTEGER PRIMARY KEY,
    agent TEXT NOT NULL,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    source TEXT NOT NULL,
    key TEXT NOT NULL,
    idem TEXT NOT NULL,
    note TEXT,
    not_before REAL,
    created_at REAL NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    turn_id INTEGER,
    finished_at REAL,
    cancel_reason TEXT,
    canceled_by TEXT,
    traceparent TEXT,
    UNIQUE (agent, source, idem)
);
CREATE INDEX IF NOT EXISTS wakes_by_state ON wakes (agent, state, conversation_id);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY,
    agent TEXT NOT NULL,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    session_id TEXT,
    source TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL,
    outcome TEXT,
    detail TEXT,
    pid INTEGER,
    pstart TEXT
);
CREATE INDEX IF NOT EXISTS turns_by_agent ON turns (agent, id);

CREATE TABLE IF NOT EXISTS check_state (
    agent TEXT NOT NULL,
    name TEXT NOT NULL,
    keys TEXT NOT NULL DEFAULT '[]',
    seq INTEGER NOT NULL DEFAULT 0,
    last_run REAL,
    last_ok INTEGER,
    last_error TEXT,
    last_error_at REAL,
    PRIMARY KEY (agent, name)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    """Autocommit connection: every change is made inside ``transaction``, so it is on disk before
    anything is acknowledged."""
    conn = sqlite3.connect(path, isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    have = {r["name"] for r in conn.execute("PRAGMA table_info(wakes)")}
    for column in ("cancel_reason", "canceled_by", "traceparent"):
        if column not in have:
            conn.execute(f"ALTER TABLE wakes ADD COLUMN {column} TEXT")
    return conn


def connect_readonly(path: Path) -> sqlite3.Connection:
    """For readers outside the gateway, such as the plugin's hooks: never creates or changes the file."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
