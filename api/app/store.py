"""In-memory bundle store, seeded from contracts/fixtures.

This is the seam the four workstreams meet at. Replace the fixture seed with real
state as the pieces land:
  - Functionality: back it with SQLite (accounting engine + snapshots)
  - Agents: push task/step/decision updates as runs progress
  - Workflows: build workflow stages and scenario steps
The web app only ever sees Bundle, so each of those can land independently.
"""

from __future__ import annotations

import copy
import json
import threading
from pathlib import Path

from typing import Any

from .models import Approval, ApprovalStatus, Briefing, Bundle, Decision, Finding, Task, WorkspaceId

FIXTURES = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"

_bundles: dict[str, dict] = {}

# Specialists may investigate concurrently (spec.md §8), so anything that mutates
# a bundle takes this. Reads stay lock-free: they validate a snapshot of the dict.
_lock = threading.Lock()


def _load(ws: WorkspaceId) -> dict:
    return json.loads((FIXTURES / f"{ws}.json").read_text(encoding="utf-8"))


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
    """Human decision. Agents may never call this path (spec.md §8)."""
    with _lock:
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


def next_id(ws: WorkspaceId, collection: str, prefix: str, width: int = 2) -> str:
    """Next free `{prefix}{n}` ID in a bundle collection, e.g. F-07 -> F-11."""
    with _lock:
        bundle = _bundles.setdefault(ws, _load(ws))
        highest = 0
        for item in bundle.get(collection, []):
            item_id = str(item.get("id", ""))
            if item_id.startswith(prefix):
                suffix = item_id[len(prefix) :]
                if suffix.isdigit():
                    highest = max(highest, int(suffix))
        return f"{prefix}{highest + 1:0{width}d}"


def append_finding(ws: WorkspaceId, finding: dict) -> Finding:
    """Append an agent-proposed finding. Validated before it lands so one bad
    payload can't corrupt the bundle the whole dashboard reads."""
    record = Finding.model_validate(finding)
    with _lock:
        bundle = _bundles.setdefault(ws, _load(ws))
        bundle["findings"].append(record.model_dump())
    return record


def append_approval(ws: WorkspaceId, approval: dict) -> Approval:
    """Append an item to the human approval queue. Agents propose here; only
    decide_approval (the human path) may ever move it off `pending`."""
    record = Approval.model_validate(approval)
    if record.status != "pending":
        raise ValueError("an agent may only append a pending approval (spec.md §8)")
    with _lock:
        bundle = _bundles.setdefault(ws, _load(ws))
        bundle["approvals"].append(record.model_dump())
    return record


def apply_review(ws: WorkspaceId, finding_id: str, decision: str) -> Finding:
    """Internal Auditor review verdict on a finding. Still not human approval
    (spec.md §8) — only decide_approval, triggered by a human, moves an
    Approval off pending. `accept` sets verified_by; anything else clears it
    and sends the finding back to needs_evidence rather than repeating the
    preparer's assertion (spec.md: "A reviewer rejection should trigger a
    specific missing-evidence search... not a repeated assertion")."""
    with _lock:
        bundle = _bundles.setdefault(ws, _load(ws))
        for finding in bundle["findings"]:
            if finding["id"] != finding_id:
                continue
            if finding["agent"] == "au":
                raise ValueError("the auditor cannot review its own finding (spec.md §8)")
            if decision == "accept":
                finding["verified_by"] = "au"
            else:
                finding["verified_by"] = None
                finding["status"] = "needs_evidence"
            return Finding.model_validate(finding)
        raise KeyError(finding_id)


def append_decision(ws: WorkspaceId, decision: dict) -> Decision:
    """Append a structured decision record (spec.md §8) — this is what the
    Reasoning log reads. Concise rationale only; never raw chain-of-thought."""
    record = Decision.model_validate(decision)
    with _lock:
        bundle = _bundles.setdefault(ws, _load(ws))
        bundle["decisions"].append(record.model_dump())
    return record


def create_task(ws: WorkspaceId, task: dict) -> Task:
    """Create a task on the Agent board. The CFO Agent calls this when it
    hands a question to a specialist — this is what makes a run visible as a
    real board card instead of a detached function call."""
    record = Task.model_validate(task)
    with _lock:
        bundle = _bundles.setdefault(ws, _load(ws))
        bundle["tasks"].append(record.model_dump())
    return record


def update_task(ws: WorkspaceId, task_id: str, **fields: Any) -> Task:
    """Partial update of a task's fields (progress, column, steps, tool_calls,
    rationale, ...). A specialist's own run loop calls this as it works, so
    the board reflects what is actually happening (spec.md §8), not a guess."""
    with _lock:
        bundle = _bundles.setdefault(ws, _load(ws))
        for task in bundle["tasks"]:
            if task["id"] == task_id:
                task.update(fields)
                return Task.model_validate(task)
        raise KeyError(task_id)


def set_briefing(ws: WorkspaceId, briefing: dict) -> Briefing:
    """Replace the Command center briefing. Only the CFO Agent writes this,
    and only from accepted findings, open tasks, and pending approvals —
    never from an unreviewed specialist claim (AGENT_PROMPTS.md § CFO Agent)."""
    record = Briefing.model_validate(briefing)
    with _lock:
        bundle = _bundles.setdefault(ws, _load(ws))
        bundle["briefing"] = record.model_dump()
    return record


def snapshot(ws: WorkspaceId) -> dict:
    """Deep copy, for tests and for the replay recorder."""
    with _lock:
        return copy.deepcopy(_bundles.setdefault(ws, _load(ws)))
