"""Small SQLite store for intake. Original bytes and all revisions live together.

No ORM, migration package or separate file-storage service yet. Set
SCHOOLTRACE_DATA_DIR to isolate tests or another local installation.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4


SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY, config TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
    base_revision INTEGER NOT NULL, created_at TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT '{}', snapshot_id TEXT
);
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    batch_id TEXT NOT NULL REFERENCES batches(id), name TEXT NOT NULL,
    sha256 TEXT NOT NULL, original BLOB NOT NULL, options TEXT NOT NULL,
    parsed TEXT NOT NULL DEFAULT '{}', committed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    role TEXT NOT NULL, system TEXT NOT NULL, record_key TEXT NOT NULL,
    version INTEGER NOT NULL, payload TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(id), locator INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(ws, role, system, record_key, version)
);
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    revision INTEGER NOT NULL, created_at TEXT NOT NULL, manifest TEXT NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0, UNIQUE(ws, revision)
);
CREATE TABLE IF NOT EXISTS evidence_requests (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    title TEXT NOT NULL, role TEXT NOT NULL, task_id TEXT,
    status TEXT NOT NULL DEFAULT 'open', source_id TEXT REFERENCES sources(id),
    snapshot_id TEXT, version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    kind TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS active_records ON records(ws, active);
CREATE INDEX IF NOT EXISTS workspace_sources ON sources(ws, committed);
PRAGMA user_version = 1;
"""


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16]}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@contextmanager
def connect():
    root = Path(os.environ.get("SCHOOLTRACE_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
    root.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(root / "schooltrace.sqlite3", timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > 1:
        connection.close()
        raise RuntimeError("Database is newer than this application; refusing to downgrade")
    connection.executescript(SCHEMA)
    try:
        # Serialize preview/mapping/commit changes, including revision checks.
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def event(connection, ws: str, kind: str, payload: dict) -> None:
    connection.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
        (uid("event"), ws, kind, "local-reviewer", now(), encode(payload)),
    )
