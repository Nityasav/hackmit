"""Sherlock API.

Run: uv run uvicorn app.main:app --reload --port 8000
Point the web app at it with NEXT_PUBLIC_API_URL=http://localhost:8000
"""

from __future__ import annotations

import json
import os
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

from . import approvals, ingestion, projection, roles
from .agents import api as agents_api
from .models import ApprovalDecision, Bundle, WorkspaceId
from .agents.chat import router as chat_router
from .reviews import router as review_router
from . import security
from .extraction import router as extraction_router
from .updates import router as updates_router

# .env.local first, matching the web app's convention and the .gitignore rule
# that already covers it. Both are ignored; neither is ever committed.
for _env_file in (".env.local", ".env"):
    load_dotenv(Path(__file__).resolve().parents[1] / _env_file, override=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .extraction import interrupt_jobs
    interrupt_jobs()
    yield


app = FastAPI(title="Sherlock API", version="0.1.0", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(review_router)
app.include_router(security.router)
app.include_router(extraction_router)
app.include_router(updates_router)
app.include_router(agents_api.router)

# A hosted web app is a different origin from a hosted API, so the browser blocks every call
# until that origin is named here. Local development keeps working with no configuration.
# SCHOOLTRACE_ALLOWED_ORIGINS is a comma-separated list; SCHOOLTRACE_ALLOWED_ORIGIN_REGEX covers
# Vercel's per-deployment preview URLs, which change on every push.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "SCHOOLTRACE_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=os.environ.get("SCHOOLTRACE_ALLOWED_ORIGIN_REGEX") or None,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.middleware("http")
async def intake_write_guard(request: Request, call_next):
    # A CORS preflight carries no credentials, no reviewer header and no body — by design, the
    # browser sends it before it will send those. Guarding it means the preflight 403s and the
    # real request is never attempted, so a hosted web app sees only an opaque CORS failure.
    # The guard still runs on the request the preflight is asking about.
    if request.method == "OPTIONS":
        return await call_next(request)
    try:
        await security.guard(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
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
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


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
    """Human approval. Agents propose; nothing they can call reaches this endpoint."""
    approvals.decide(body.workspace, approval_id, body.decision)
    return projection.bundle(body.workspace)


@app.get("/api/workspaces")
def workspaces(request: Request):
    user = request.state.user
    return [ws for ws in ingestion.list_workspaces() if user["role"] == "admin" or ws["id"] in user["workspaces"]]


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


@app.post("/api/workspaces/{ws}/sources/detect")
def detect_saved_sources(ws: str):
    """Find committed documents that are really structured records, and stage them."""
    return ingestion.detect_saved_sources(ws)


@app.get("/api/roles")
def record_roles():
    """The record vocabulary, so the browser can detect a file's type before upload.

    Served rather than restated in TypeScript: the frontend detector used to carry its
    own copy of every role's columns, which meant adding a role silently stopped it
    being detected. One definition, `app/roles.py`, and both sides read it.
    """
    return {
        "roles": [{"id": role, "label": roles.LABELS[role], "required": fields,
                   "key": list(roles.KEY_FIELDS[role])}
                  for role, fields in roles.FIELDS.items()],
        "documents": [{"id": role, "label": roles.LABELS[role]}
                      for role in sorted(roles.DOCUMENT_ROLES)],
        "optional": roles.OPTIONAL_FIELDS,
    }


@app.get("/api/workspaces/{ws}/coverage")
def coverage(ws: str):
    return ingestion.coverage(ws)


@app.get("/api/workspaces/{ws}/requirements")
def workspace_requirements(ws: str):
    """What the agents need from this workspace, and what is still missing.

    Books renders this list directly, so an agent can never depend on data nobody
    was asked to supply.
    """
    return ingestion.coverage(ws)


@app.patch("/api/workspaces/{ws}/settings")
def settings(ws: str, body: ingestion.SettingsUpdate):
    """Answer the requirements that are a single value rather than a file."""
    return ingestion.update_settings(ws, body)


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
