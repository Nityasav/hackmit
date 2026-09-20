"""The shared schema must open an older database additively, without losing rows."""

import sqlite3

import pytest

from app import db

# app/db.py at user_version 2, long before the event tables joined the schema.
V2_SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY, config TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0
);
PRAGMA user_version = 2;
"""


def _v2_database(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(tmp_path / "schooltrace.sqlite3")
    connection.executescript(V2_SCHEMA)
    connection.execute("INSERT INTO workspaces VALUES ('ws-old', '{\"name\": \"Prior\"}', 4)")
    connection.commit()
    connection.close()


def test_opening_a_v2_database_upgrades_it_without_losing_rows(tmp_path, monkeypatch):
    _v2_database(tmp_path, monkeypatch)

    with db.connect() as connection:
        row = connection.execute("SELECT config, revision FROM workspaces WHERE id='ws-old'").fetchone()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    assert row["revision"] == 4, "an existing workspace row must survive the upgrade"
    assert version == db.SCHEMA_VERSION
    assert {"economic_events", "links", "agent_decisions", "approvals",
            "records", "snapshots"} <= tables


def test_a_newer_database_is_refused_rather_than_downgraded(tmp_path, monkeypatch):
    _v2_database(tmp_path, monkeypatch)
    connection = sqlite3.connect(tmp_path / "schooltrace.sqlite3")
    connection.executescript("PRAGMA user_version = 99;")
    connection.close()

    with pytest.raises(RuntimeError, match="refusing to downgrade"):
        with db.connect():
            pass


def test_an_older_database_gains_the_event_columns_it_lacks(tmp_path, monkeypatch):
    """`CREATE TABLE IF NOT EXISTS` cannot add a column to a table that exists.

    Without the explicit column migration an older database would keep its old shape
    and fail on the first write that names `records.event_id`.
    """
    _v2_database(tmp_path, monkeypatch)
    connection = sqlite3.connect(tmp_path / "schooltrace.sqlite3")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY, ws TEXT NOT NULL, role TEXT NOT NULL,
            system TEXT NOT NULL, record_key TEXT NOT NULL, version INTEGER NOT NULL,
            payload TEXT NOT NULL, source_id TEXT NOT NULL, locator INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
    """)
    connection.commit()
    connection.close()

    with db.connect() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(records)")}

    assert "event_id" in columns, "an existing records table must gain the new column"
