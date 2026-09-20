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
CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    agent TEXT NOT NULL, snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
    status TEXT NOT NULL, model TEXT NOT NULL, focus TEXT NOT NULL,
    created_at TEXT NOT NULL, completed_at TEXT,
    output TEXT NOT NULL DEFAULT '{}', error TEXT
);
CREATE TABLE IF NOT EXISTS agent_requests (
    ws TEXT NOT NULL REFERENCES workspaces(id), request_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    PRIMARY KEY(ws, request_id)
);
CREATE INDEX IF NOT EXISTS active_records ON records(ws, active);
CREATE INDEX IF NOT EXISTS workspace_sources ON sources(ws, committed);
CREATE INDEX IF NOT EXISTS workspace_agent_runs ON agent_runs(ws, created_at);
CREATE TABLE IF NOT EXISTS review_scans (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    snapshot_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_actions (
    ws TEXT NOT NULL REFERENCES workspaces(id), snapshot_id TEXT NOT NULL,
    finding_id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY(ws, snapshot_id, finding_id)
);
PRAGMA user_version = 2;
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
    root.chmod(0o700)
    connection = sqlite3.connect(root / "schooltrace.sqlite3", timeout=15)
    (root / "schooltrace.sqlite3").chmod(0o600)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > 2:
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


def event(connection, ws: str, kind: str, payload: dict, actor: str = "local-reviewer") -> None:
    connection.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
        (uid("event"), ws, kind, actor, now(), encode(payload)),
    )
