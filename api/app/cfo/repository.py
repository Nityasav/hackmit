"""CFO-only checkpoints; does not own or mutate Maxim's financial database."""

import sqlite3
from pathlib import Path

from .schemas import Run, now


class RunRepository:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS cfo_runs (id TEXT PRIMARY KEY, workspace TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
        Path(path).chmod(0o600)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def save(self, run: Run) -> None:
        run.updated_at = now()
        with self._connect() as db:
            db.execute("INSERT INTO cfo_runs VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (run.id, run.request.workspace, run.created_at, run.model_dump_json()))

    def get(self, run_id: str) -> Run:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM cfo_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return Run.model_validate_json(row[0])

    def latest(self, workspace: str) -> Run | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM cfo_runs WHERE workspace=? ORDER BY created_at DESC LIMIT 1", (workspace,)).fetchone()
        return Run.model_validate_json(row[0]) if row else None

    def interrupt_pending(self) -> None:
        """Call once at process startup, with one API worker owning this database."""
        with self._connect() as db:
            rows = db.execute("SELECT payload FROM cfo_runs").fetchall()
        for row in rows:
            run = Run.model_validate_json(row[0])
            if run.status in {"queued", "planning", "running"}:
                run.status = "interrupted"
                run.unresolved.append("Server restarted during this run. Start a new run against the current snapshot.")
                run.briefing = "Run interrupted. No final report was published."
                self.save(run)
