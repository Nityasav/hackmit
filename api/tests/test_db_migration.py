"""The shared schema must open an older database additively, without losing rows."""

import sqlite3

import pytest

from app import db
from app.cfo.repository import RunRepository
from app.cfo.schemas import Run, RunRequest

# app/db.py at user_version 2, before cfo_runs joined the schema.
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
    assert {"cfo_runs", "approvals", "agent_runs", "records", "snapshots"} <= tables


def test_a_newer_database_is_refused_rather_than_downgraded(tmp_path, monkeypatch):
    _v2_database(tmp_path, monkeypatch)
    connection = sqlite3.connect(tmp_path / "schooltrace.sqlite3")
    connection.executescript("PRAGMA user_version = 99;")
    connection.close()

    with pytest.raises(RuntimeError, match="refusing to downgrade"):
        with db.connect():
            pass


def test_coordinator_runs_and_intake_share_one_transaction(tmp_path, monkeypatch):
    """The point of the move: one connection can read a run and the workspace it names."""
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    with db.connect() as connection:
        connection.execute("INSERT INTO workspaces VALUES ('ws-1', '{}', 0)")

    repository = RunRepository()
    run = Run(id="CFO-1", request=RunRequest(workspace="ws-1"))
    repository.save(run)

    with db.connect() as connection:
        joined = connection.execute(
            "SELECT r.id, w.revision FROM cfo_runs r JOIN workspaces w ON w.id = r.workspace"
        ).fetchall()
    assert [tuple(row) for row in joined] == [("CFO-1", 0)]
    assert repository.latest("ws-1").id == "CFO-1"


def test_an_explicit_path_keeps_a_run_store_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path / "shared"))
    repository = RunRepository(tmp_path / "isolated.sqlite3")
    repository.save(Run(id="CFO-2", request=RunRequest(workspace="test-workspace")))

    assert repository.get("CFO-2").id == "CFO-2"
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM cfo_runs").fetchone()[0] == 0
