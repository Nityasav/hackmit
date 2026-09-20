"""In-memory bundle store, seeded from the same fixtures the web app renders.

Swap the fixture seed for SQLite-backed state once the accounting engine lands.
The web app only ever sees Bundle, so that can happen behind this module.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import ApprovalStatus, Bundle, WorkspaceId

FIXTURES = Path(__file__).resolve().parents[2] / "web" / "src" / "fixtures"

_bundles: dict[str, dict] = {}


def _load(ws: WorkspaceId) -> dict:
    return json.loads((FIXTURES / f"{ws}.json").read_text())


def get_bundle(ws: WorkspaceId) -> Bundle:
    if ws not in _bundles:
        _bundles[ws] = _load(ws)
    return Bundle.model_validate(_bundles[ws])


def reset(ws: WorkspaceId | None = None) -> None:
    if ws is None:
        _bundles.clear()
    else:
        _bundles.pop(ws, None)


def decide_approval(ws: WorkspaceId, approval_id: str, decision: ApprovalStatus) -> Bundle:
    """Human decision. Agents may never call this path."""
    bundle = _bundles.setdefault(ws, _load(ws))
    found = False
    for approval in bundle["approvals"]:
        if approval["id"] == approval_id:
            approval["status"] = decision
            found = True
    if not found:
        raise KeyError(approval_id)
    if decision == "approved":
        for task in bundle["tasks"]:
            if task.get("approval_id") == approval_id:
                task["column"] = "done"
                task["progress"] = 100
    return Bundle.model_validate(bundle)

