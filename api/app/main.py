"""SchoolTrace API.

Run: uv run uvicorn app.main:app --reload --port 8000
Point the web app at it with NEXT_PUBLIC_API_URL=http://localhost:8000
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import store
from .models import ApprovalDecision, Bundle, WorkspaceId

app = FastAPI(title="SchoolTrace API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/workspaces/{ws}/bundle", response_model=Bundle)
def get_bundle(ws: WorkspaceId) -> Bundle:
    """Everything the dashboard renders, in one payload. The web app polls this."""
    try:
        return store.get_bundle(ws)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"unknown workspace {ws}")


@app.post("/api/approvals/{approval_id}/decision", response_model=Bundle)
def decide(approval_id: str, body: ApprovalDecision) -> Bundle:
    """Human approval. The only path that may apply a change to a scenario."""
    try:
        return store.decide_approval(body.workspace, approval_id, body.decision)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown approval {approval_id}")

