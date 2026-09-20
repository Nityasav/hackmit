"""Coordinator run checkpoints, stored beside the intake tables.

`cfo_runs` lives in the shared schema (`app/db.py`) so one transaction can read a
coordinator run and the snapshot, records and triage runs it was derived from.
Passing an explicit `path` keeps a run store isolated in a temporary file, which
is how the tests and the scripted CLI demo use it.
"""

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from .. import db
from .schemas import Run, now

TABLE = ("CREATE TABLE IF NOT EXISTS cfo_runs (id TEXT PRIMARY KEY, workspace TEXT NOT NULL, "
         "created_at TEXT NOT NULL, payload TEXT NOT NULL)")


class RunRepository:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path) if path is not None else None
        if self.path is None:
            return
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(TABLE)

    @contextmanager
    def _connect(self):
        if self.path is None:
            with db.connect() as connection:
                yield connection
            return
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, run: Run) -> None:
        run.updated_at = now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO cfo_runs VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (run.id, run.request.workspace, run.created_at, run.model_dump_json()))

    def get(self, run_id: str) -> Run:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM cfo_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return Run.model_validate_json(row[0])

    def latest(self, workspace: str) -> Run | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM cfo_runs WHERE workspace=? ORDER BY created_at DESC LIMIT 1",
                (workspace,)).fetchone()
        return Run.model_validate_json(row[0]) if row else None

    def interrupt_pending(self) -> None:
        """Call once at process startup, with one API worker owning this database."""
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM cfo_runs").fetchall()
        for row in rows:
            run = Run.model_validate_json(row[0])
            if run.status in {"queued", "planning", "running"}:
                run.status = "interrupted"
                run.unresolved.append("Server restarted during this run. Start a new run against the current snapshot.")
                run.briefing = "Run interrupted. No final report was published."
                self.save(run)
