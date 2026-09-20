"""Incremental snapshot change summaries and explicit five-agent rescans."""
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import db, ingestion
from .cfo.api import runtime
from .cfo.schemas import RunRequest
from .reviews import scan

router = APIRouter(prefix="/api/workspaces/{ws}/updates", tags=["Ongoing file updates"])


def change_view(c, ws):
    ingestion.workspace(c, ws)
    snapshots = c.execute("SELECT * FROM snapshots WHERE ws=? ORDER BY revision DESC LIMIT 2", (ws,)).fetchall()
    current = snapshots[0] if snapshots else None
    previous = snapshots[1] if len(snapshots) > 1 else None
    now = set(json.loads(current["manifest"])["record_ids"]) if current else set()
    before = set(json.loads(previous["manifest"])["record_ids"]) if previous else set()
    records = {r["id"]: dict(r) for r in c.execute("SELECT id,role,record_key,version,source_id FROM records WHERE ws=?", (ws,))}
    return {"snapshot_id": current["id"] if current else None, "previous_snapshot_id": previous["id"] if previous else None,
            "revision": current["revision"] if current else 0,
            "added_or_revised": [records[x] for x in sorted(now - before)],
            "superseded": [records[x] for x in sorted(before - now)], "total_records": len(now)}


@router.get("")
def view(ws: str):
    with db.connect() as c:
        result = change_view(c, ws)
        scans = c.execute("SELECT snapshot_id,created_at FROM review_scans WHERE ws=? ORDER BY rowid DESC LIMIT 1", (ws,)).fetchone()
        result["rules_scan_current"] = bool(scans and scans["snapshot_id"] == result["snapshot_id"])
        result["recent_reviews"] = [json.loads(r[0]) for r in c.execute("SELECT payload FROM events WHERE ws=? AND kind='updates.review' ORDER BY rowid DESC LIMIT 10", (ws,))]
        return result


class Rescan(BaseModel):
    snapshot_id: str
    live: bool = False


@router.post("/scan")
async def rescan(ws: str, body: Rescan, request: Request):
    with db.connect() as c:
        changes = change_view(c, ws)
        if changes["snapshot_id"] != body.snapshot_id:
            raise HTTPException(409, "New files were committed; reload the change summary before scanning")
        previous = [json.loads(r[0]) for r in c.execute("SELECT payload FROM events WHERE ws=? AND kind='updates.review'", (ws,))]
        if body.live:
            prior = next((x for x in reversed(previous) if x["snapshot_id"] == body.snapshot_id and x.get("run_id")), None)
            if prior:
                saved = runtime(request).repository.get(prior["run_id"])
                if saved.status not in {"failed", "interrupted", "stale"}:
                    return {**prior, "reused": True}
    rules = scan(ws)
    if rules["snapshot_id"] != body.snapshot_id:
        raise HTTPException(409, "Snapshot changed while scanning; reload before starting paid agents")
    result = {"snapshot_id": body.snapshot_id, "scan_id": rules["id"], "run_id": None}
    if body.live:
        # No awaits between runtime.start and event persistence: duplicate browser
        # clicks serialize on the API event loop; CFORuntime also locks workspaces.
        objective = (f"Review snapshot {body.snapshot_id}. Since the previous snapshot, "
                     f"{len(changes['added_or_revised'])} records were added/revised and {len(changes['superseded'])} superseded. "
                     "Investigate the new evidence and its effects using all five agents. Recheck related unchanged records; "
                     "do not assume earlier findings remain valid. Distinguish resolved gaps from unverified claims.")
        run = runtime(request).start(RunRequest(workspace=ws, workflow="five_agent", mode="live", objective=objective))
        result["run_id"] = run.id
    with db.connect() as c:
        db.event(c, ws, "updates.review", result, request.state.user["name"])
    return result
