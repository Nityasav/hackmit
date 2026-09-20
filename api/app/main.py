"""SchoolTrace API.

Run: uv run uvicorn app.main:app --reload --port 8000
Point the web app at it with NEXT_PUBLIC_API_URL=http://localhost:8000
"""

from __future__ import annotations

import json
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import quote
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool

from . import approvals, ingestion, projection, store
from .agents import cfo
from .models import ApprovalDecision, Bundle, WorkspaceId
from .cfo.api import router as cfo_router

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if hasattr(app.state, "cfo_runtime"):
        await app.state.cfo_runtime.close()


app = FastAPI(title="SchoolTrace API", version="0.1.0", lifespan=lifespan)
app.include_router(cfo_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def intake_write_guard(request: Request, call_next):
    # /api/approvals is a write path into intake data too, now that a decision on an
    # intake workspace is recorded rather than refused.
    guarded = ("/api/workspaces", "/api/approvals")
    if request.method in {"POST", "PATCH"} and request.url.path.startswith(guarded):
        if request.headers.get("X-SchoolTrace-Reviewer") != "local-reviewer":
            return JSONResponse(status_code=403, content={"detail": {"code": "reviewer_required", "message": "Confirm the local reviewer before changing intake data"}})
    length = request.headers.get("content-length")
    if length:
        try:
            oversized = int(length) > ingestion.MAX_BATCH + 1024 * 1024
        except ValueError:
            oversized = True
        if oversized:
            return JSONResponse(status_code=413, content={"detail": {"code": "batch_limit", "message": "Request exceeds 51 MB including upload metadata"}})
    return await call_next(request)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/workspaces/{ws}/bundle", response_model=Bundle)
def get_bundle(ws: WorkspaceId) -> Bundle:
    """Everything the dashboard renders, in one payload. The web app polls this."""
    try:
        return projection.bundle(ws)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"unknown workspace {ws}")


@app.post("/api/approvals/{approval_id}/decision", response_model=Bundle)
def decide(approval_id: str, body: ApprovalDecision) -> Bundle:
    """Human approval. The only path that may apply a change to a scenario.

    Agents propose; nothing they can call reaches this endpoint.
    """
    if body.workspace in projection.RECORDED:
        try:
            return store.decide_approval(body.workspace, approval_id, body.decision)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown approval {approval_id}")
    approvals.decide(body.workspace, approval_id, body.decision)
    return projection.bundle(body.workspace)


@app.post("/api/demo/{action}", response_model=Bundle)
def demo(action: str, ws: WorkspaceId = "sandbox") -> Bundle:
    """Demo controls: reset, inject_issue, add_evidence, next_month.

    TODO(workflows): drive these from app/workflows/scenarios.py.
    """
    if ws not in {"sandbox", "mit"}:
        raise HTTPException(409, "Reset is only available for demo workspaces")
    if action == "reset":
        store.reset(ws)
        return store.get_bundle(ws)
    raise HTTPException(status_code=501, detail=f"demo action '{action}' not implemented yet")


@app.get("/api/workspaces")
def workspaces():
    return ingestion.list_workspaces()


@app.post("/api/workspaces", status_code=201)
def create_workspace(body: ingestion.WorkspaceCreate):
    return ingestion.create_workspace(body)


@app.post("/api/workspaces/{ws}/imports", status_code=201)
async def upload(ws: str, request: Request):
    # Limit the entire body even when the client omits Content-Length.
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > ingestion.MAX_BATCH + 1024 * 1024:
            ingestion.fail("batch_limit", "Request exceeds 51 MB including upload metadata", 413)
    # Starlette can parse the cached, bounded body without trusting file paths.
    request._body = bytes(content)
    async with request.form(max_files=ingestion.MAX_FILES, max_fields=1, max_part_size=64 * 1024) as form:
        files = form.getlist("files")
        try:
            options = json.loads(str(form.get("metadata", "[]")))
            if not isinstance(options, list) or len(options) != len(files):
                raise ValueError("Provide one metadata object per file")
            metadata = [ingestion.FileOptions.model_validate(item) for item in options]
        except (ValueError, ValidationError) as exc:
            ingestion.fail("invalid_metadata", str(exc))
        uploads = []
        for file, meta in zip(files, metadata):
            if not isinstance(file, UploadFile):
                ingestion.fail("invalid_file", "The files field must contain file uploads")
            uploads.append((file.filename or "", await file.read(ingestion.MAX_FILE + 1), meta))
        return await run_in_threadpool(ingestion.stage, ws, uploads)


@app.get("/api/workspaces/{ws}/imports")
def imports(ws: str):
    return ingestion.list_batches(ws)


@app.get("/api/workspaces/{ws}/imports/{bid}")
def import_detail(ws: str, bid: str):
    return ingestion.get_batch(ws, bid)


@app.patch("/api/workspaces/{ws}/imports/{bid}/mapping")
def mapping(ws: str, bid: str, body: ingestion.MappingUpdate):
    return ingestion.update_mapping(ws, bid, body)


@app.post("/api/workspaces/{ws}/imports/{bid}/commit")
def commit(ws: str, bid: str, body: ingestion.CommitRequest):
    return ingestion.commit(ws, bid, body)


@app.get("/api/workspaces/{ws}/coverage")
def coverage(ws: str):
    return ingestion.coverage(ws)


@app.get("/api/workspaces/{ws}/sources/{sid}")
def source(ws: str, sid: str, start: int = Query(default=1, ge=1), limit: int = Query(default=100, ge=1, le=200)):
    return ingestion.source_view(ws, sid, start, limit)


@app.get("/api/workspaces/{ws}/sources/{sid}/spans/{line}")
def span(ws: str, sid: str, line: int):
    if line < 1:
        ingestion.fail("invalid_locator", "Line numbers start at 1")
    result = ingestion.source_view(ws, sid, line, 1)
    if not result["lines"]:
        ingestion.fail("span_not_found", "Line does not exist", 404)
    return result


@app.get("/api/workspaces/{ws}/sources/{sid}/download")
def original(ws: str, sid: str):
    name, content = ingestion.source_bytes(ws, sid)
    return Response(content, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    })


@app.post("/api/workspaces/{ws}/evidence-requests", status_code=201)
def evidence_request(ws: str, body: ingestion.EvidenceCreate):
    return ingestion.create_evidence_request(ws, body)


@app.post("/api/workspaces/{ws}/evidence-requests/{rid}/responses")
def evidence_response(ws: str, rid: str, body: ingestion.EvidenceResponse):
    return ingestion.respond(ws, rid, body)


@app.get("/api/workspaces/{ws}/agent-runs")
def agent_runs(ws: str):
    return cfo.list_runs(ws)


@app.post("/api/workspaces/{ws}/agent-runs", status_code=201)
async def run_snapshot_agent(ws: str, body: cfo.RunRequest):
    """Run an allowlisted read-only agent against the current immutable snapshot."""
    return await run_in_threadpool(cfo.run, ws, body)
