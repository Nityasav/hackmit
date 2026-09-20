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


SCHEMA_VERSION = 10

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
    active INTEGER NOT NULL DEFAULT 1, event_id TEXT,
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
CREATE TABLE IF NOT EXISTS cfo_runs (
    id TEXT PRIMARY KEY, workspace TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    snapshot_id TEXT, run_id TEXT, finding_id TEXT, task_id TEXT,
    agent TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL,
    journal TEXT, effects TEXT, verified INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
    decided_at TEXT, decided_by TEXT
);
CREATE INDEX IF NOT EXISTS active_records ON records(ws, active);
CREATE INDEX IF NOT EXISTS workspace_sources ON sources(ws, committed);
CREATE INDEX IF NOT EXISTS workspace_agent_runs ON agent_runs(ws, created_at);
CREATE INDEX IF NOT EXISTS workspace_cfo_runs ON cfo_runs(workspace, created_at);
CREATE INDEX IF NOT EXISTS workspace_approvals ON approvals(ws, status);
CREATE TABLE IF NOT EXISTS review_scans (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    snapshot_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_actions (
    ws TEXT NOT NULL REFERENCES workspaces(id), snapshot_id TEXT NOT NULL,
    finding_id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY(ws, snapshot_id, finding_id)
);
CREATE TABLE IF NOT EXISTS extraction_items (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
-- Reviewed precedent: what a human decided, in a form a later run can check.
-- Written only by approvals.decide(), so a precedent can never exist without a
-- human decision behind it. `status` is how a precedent is retired when its
-- governing evidence changes; nothing is ever deleted, so the history of what
-- the agent was told stays auditable.
CREATE TABLE IF NOT EXISTS precedents (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    pattern TEXT NOT NULL, verdict TEXT NOT NULL, guidance TEXT NOT NULL,
    scope TEXT NOT NULL, source_finding_id TEXT, source_approval_id TEXT,
    decided_by TEXT NOT NULL, created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active', uses INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS extraction_workspace ON extraction_items(ws, kind);
CREATE TABLE IF NOT EXISTS extraction_documents (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    name TEXT NOT NULL, sha256 TEXT NOT NULL, original BLOB NOT NULL,
    payload TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(ws, sha256)
);
CREATE TABLE IF NOT EXISTS extraction_active (
    ws TEXT PRIMARY KEY REFERENCES workspaces(id), model_id TEXT NOT NULL,
    version INTEGER NOT NULL, evaluation_id TEXT NOT NULL
);
-- Invariant 1: one transaction, one identity. An economic event is the thing that
-- happened in the business; the invoice, the receipt, the payment, the bank line and
-- the journal entries are all *views* of it. Every artifact carries this id, so
-- "what else touched this?" is an indexed lookup rather than a reconstruction, and
-- two agents cannot end up holding different opinions about the same transaction.
-- An event is identified by (workspace, reference), not by reference alone. The id is
-- whatever the source called it, and two companies can each have an "INV-1001" without
-- being the same transaction. A global primary key here made the second workspace to
-- import the same pack fail on a UNIQUE constraint.
CREATE TABLE IF NOT EXISTS economic_events (
    id TEXT NOT NULL, ws TEXT NOT NULL REFERENCES workspaces(id),
    kind TEXT NOT NULL, title TEXT NOT NULL, occurred_on TEXT NOT NULL,
    period TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL, created_by TEXT NOT NULL,
    PRIMARY KEY (ws, id)
);
-- Typed edges, carrying HOW each was established. `method` is the honest part: an
-- exact reference match and a fuzzy description match are both links, and a reader
-- must be able to tell them apart. `confidence` is computed by a rubric in code
-- (see accounting/match.py); no model writes this column.
CREATE TABLE IF NOT EXISTS links (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    event_id TEXT,
    from_type TEXT NOT NULL, from_id TEXT NOT NULL,
    to_type TEXT NOT NULL, to_id TEXT NOT NULL,
    kind TEXT NOT NULL, method TEXT NOT NULL,
    confidence INTEGER NOT NULL DEFAULT 100, rationale TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(ws, from_type, from_id, to_type, to_id, kind)
);
-- The defensible decision trail (Invariant 2). One row per material action: what an
-- agent did, on what evidence, with what confidence, who reviewed it, and whether a
-- human was asked. This is what an evidence pack is assembled from, so it is written
-- as the work happens rather than reconstructed afterwards.
CREATE TABLE IF NOT EXISTS agent_decisions (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    event_id TEXT,
    thread_id TEXT, run_id TEXT, agent TEXT NOT NULL, parent_agent TEXT,
    action TEXT NOT NULL, summary TEXT NOT NULL, why TEXT NOT NULL DEFAULT '',
    confidence INTEGER, evidence TEXT NOT NULL DEFAULT '[]',
    reviewer TEXT, review_verdict TEXT, escalated INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL DEFAULT '', cost_cents INTEGER NOT NULL DEFAULT 0,
    memory_checks TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
-- A document someone asked for, frozen at the moment they asked.
-- `payload` holds the figures as they stood, not a pointer to recompute them later. A
-- deliverable is a document of a moment: regenerating it next week from the same books
-- gives a different document under the same title, and two of those saying different
-- things is the failure this table exists to prevent. `snapshot_id` records which
-- version of the records it was drawn from, so a reader can tell when it went stale.
CREATE TABLE IF NOT EXISTS deliverables (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    kind TEXT NOT NULL, title TEXT NOT NULL,
    requested_by TEXT NOT NULL DEFAULT '', thread_id TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL, snapshot_id TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS workspace_deliverables ON deliverables(ws, created_at);
-- What was asked and what came back, written as it happens. A turn is recorded before
-- its run starts and updated when it ends, so a run that crashed or is still going leaves
-- the question on the record: a turn that only appears once it succeeds makes a failure
-- look like something nobody ever asked.
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    thread_id TEXT NOT NULL, role TEXT NOT NULL, body TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS workspace_conversations ON conversations(ws, thread_id);
-- A precedent is never applied, only checked, and every check is recorded — including
-- the ones that decline. A precedent silently dropped because it no longer fits is
-- indistinguishable from one nobody looked at, and the difference is the whole point of
-- carrying a decision between periods at all.
CREATE TABLE IF NOT EXISTS precedent_checks (
    id TEXT PRIMARY KEY, ws TEXT NOT NULL REFERENCES workspaces(id),
    precedent_id TEXT NOT NULL REFERENCES precedents(id),
    applies INTEGER NOT NULL, reason TEXT NOT NULL,
    matched TEXT NOT NULL DEFAULT '[]', changed_sources TEXT NOT NULL DEFAULT '[]',
    checked_by TEXT NOT NULL, checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS workspace_precedent_checks ON precedent_checks(ws, precedent_id);
CREATE INDEX IF NOT EXISTS workspace_events ON economic_events(ws, period);
CREATE INDEX IF NOT EXISTS event_links ON links(ws, event_id);
CREATE INDEX IF NOT EXISTS link_endpoints ON links(ws, from_type, from_id);
CREATE INDEX IF NOT EXISTS event_decisions ON agent_decisions(ws, event_id);
CREATE INDEX IF NOT EXISTS thread_decisions ON agent_decisions(ws, thread_id);
""" + f"PRAGMA user_version = {SCHEMA_VERSION};"

#: Columns added to tables that predate them. `CREATE TABLE IF NOT EXISTS` cannot add a
#: column to a table that already exists, so an older database would silently keep the
#: old shape and fail on first write. Each entry is idempotent and additive.
ADDED_COLUMNS = (
    ("records", "event_id", "TEXT"),
    ("sources", "event_hint", "TEXT"),
    # What a run did with the precedent it was offered. Stored on the decision
    # rather than in a side table: it is part of the reasoning that produced
    # that decision, and a reviewer reading the row should see it there.
    ("agent_decisions", "memory_checks", "TEXT NOT NULL DEFAULT '[]'"),
)


def _add_missing_columns(connection) -> None:
    for table, column, kind in ADDED_COLUMNS:
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if existing and column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
    _rekey_events(connection)


def _rekey_events(connection) -> None:
    """Move `economic_events` onto a per-workspace key if it predates that fix.

    `CREATE TABLE IF NOT EXISTS` cannot change a primary key, so a database created
    while the key was global keeps it and fails the first time two workspaces share an
    event reference. Rebuilding is safe here because the rows carry their own workspace.
    """
    columns = list(connection.execute("PRAGMA table_info(economic_events)"))
    if not columns:
        return
    key_columns = {row["name"] for row in columns if row["pk"]}
    if key_columns == {"ws", "id"}:
        return
    connection.executescript("""
        ALTER TABLE economic_events RENAME TO economic_events_old;
        CREATE TABLE economic_events (
            id TEXT NOT NULL, ws TEXT NOT NULL REFERENCES workspaces(id),
            kind TEXT NOT NULL, title TEXT NOT NULL, occurred_on TEXT NOT NULL,
            period TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL, created_by TEXT NOT NULL,
            PRIMARY KEY (ws, id)
        );
        INSERT INTO economic_events SELECT id, ws, kind, title, occurred_on, period,
            status, created_at, created_by FROM economic_events_old;
        DROP TABLE economic_events_old;
    """)


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
    if version > SCHEMA_VERSION:
        connection.close()
        raise RuntimeError("Database is newer than this application; refusing to downgrade")
    connection.executescript(SCHEMA)
    _add_missing_columns(connection)
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
