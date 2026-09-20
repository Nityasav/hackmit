"""Withdraw a source from active books; retain originals and prior snapshots."""
from pydantic import BaseModel
from fastapi import APIRouter
from . import db, ingestion

router = APIRouter(prefix="/api/workspaces/{ws}")


class Removal(BaseModel):
    expected_revision: int
    confirmation: str


@router.delete("/sources/{sid}")
def remove(ws: str, sid: str, body: Removal):
    with db.connect() as connection:
        config = ingestion.workspace(connection, ws)
        source = connection.execute("SELECT * FROM sources WHERE ws=? AND id=? AND committed=1", (ws, sid)).fetchone()
        if not source:
            ingestion.fail("source_not_found", "Committed source not found", 404)
        if body.confirmation != source["name"]:
            ingestion.fail("confirmation_required", "Confirm the source name")
        if config["revision"] != body.expected_revision:
            ingestion.fail("stale_revision", "Books changed. Refresh before removing a file.", 409)
        active = connection.execute("SELECT id FROM records WHERE ws=? AND source_id=? AND active=1", (ws, sid)).fetchall()
        if not active:
            ingestion.fail("inactive_source", "This source no longer supplies active records", 409)
        connection.execute("UPDATE records SET active=0 WHERE ws=? AND source_id=?", (ws, sid))
        records = ingestion.active_records(connection, ws)
        revision = config["revision"] + 1
        snapshot = db.uid("snapshot")
        manifest = {"record_ids": [r["id"] for r in records],
                    "source_ids": sorted({r["source_id"] for r in records}),
                    "profile": config["profile"], "scope": config["scope"],
                    "period": [config["start"], config["end"]]}
        connection.execute("UPDATE snapshots SET stale=1 WHERE ws=?", (ws,))
        connection.execute("INSERT INTO snapshots(id,ws,revision,created_at,manifest) VALUES(?,?,?,?,?)",
                           (snapshot, ws, revision, db.now(), db.encode(manifest)))
        connection.execute("UPDATE workspaces SET revision=? WHERE id=?", (revision, ws))
        connection.execute("UPDATE evidence_requests SET status='needs_review',version=version+1 WHERE ws=? AND source_id=?",
                           (ws, sid))
        db.event(connection, ws, "source_removed", {"source_id": sid, "name": source["name"],
                 "record_ids": [r["id"] for r in active], "snapshot_id": snapshot, "revision": revision})
    return {"snapshot_id": snapshot, "removed_records": len(active),
            "note": "Removed from active books. Original bytes and historical snapshots remain available."}
