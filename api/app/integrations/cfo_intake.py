"""Read-only CFO DataSource over committed intake snapshots.

Bridges the intake layer (`app/ingestion.py`, owned by Functionality) to the CFO
ports so the coordinator can investigate real uploaded records instead of the
scripted harness. This adapter only reads: it never stages, commits, mutates
records, publishes snapshots, or reaches evaluator truth.

Deterministic calculations are deliberately NOT implemented here. The accounting
engine is Functionality's (`app/accounting/`), and a calculation invented by this
bridge would defeat the provenance checks the CFO relies on, which require an
amount to come from the same engine the auditor reperforms. Until that inventory
is published the scope carries no calculations and `calculate` fails closed, so
specialists can still explain and cite evidence but cannot assert an amount.
"""

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from ..cfo.schemas import Calculation, Scope, Source, SourceSpan
from ..ingestion import coverage

# Intake roles map onto the three specialist domains; everything else is shared context.
DOMAINS = {"invoice": "ap", "payroll": "py", "grants": "gr"}
MAX_LINES = 400
MAX_CHARS = 20_000


def _unavailable(exc: HTTPException) -> ValueError:
    """Keep intake's HTTP error shape out of the CFO run loop."""
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return ValueError(detail.get("message") or "Intake workspace is unavailable.")


async def _snapshot_view(workspace: str) -> dict:
    try:
        return await run_in_threadpool(coverage, workspace)
    except HTTPException as exc:
        raise _unavailable(exc) from None


def _usable(source: dict) -> bool:
    """Committed sources still backing the snapshot.

    Every role, documents included, contributes a record, so intake clears the
    active flag exactly when a later version supersedes the source.
    """
    return bool(source["active"])


class IntakeDataSource:
    """DataSource over one institution's committed records."""

    async def snapshot(self, workspace: str) -> Scope:
        view = await _snapshot_view(workspace)
        config, snapshot = view["workspace"], view["snapshot"]
        if snapshot is None:
            raise ValueError("This workspace has no committed snapshot; commit an import before starting a CFO run.")
        sources = [
            Source(id=s["id"], title=s["name"], locator=f"{s['name']} (sha256 {s['sha256'][:12]})",
                   domain=DOMAINS.get(s["role"], "shared"))
            for s in view["sources"] if _usable(s)
        ]
        if not sources:
            raise ValueError("The committed snapshot exposes no readable sources.")
        gaps = [f"{c['label']}: missing {', '.join(c['missing'])}." for c in view["capabilities"] if c["missing"]]
        gaps += [f"Open evidence request ({r['role']}): {r['title']}."
                 for r in view["requests"] if r["status"] in {"open", "needs_review"}]
        gaps.append("No deterministic calculation inventory is published for this workspace; "
                    "amounts cannot be confirmed in this run.")
        return Scope(
            workspace=workspace, snapshot_id=snapshot["id"], institution=config["name"],
            period=f"{config['start']} to {config['end']}", accounting_profile=config["profile"],
            sources=sources, calculations=[], gaps=gaps,
        )

    async def read_source(self, scope: Scope, source_id: str) -> SourceSpan:
        view = await _snapshot_view(scope.workspace)
        # Serve evidence only from the snapshot the run was planned against.
        if view["snapshot"] is None or view["snapshot"]["id"] != scope.snapshot_id:
            raise ValueError("The snapshot changed since this run started; rerun against the current snapshot.")
        if not any(s["id"] == source_id and _usable(s) for s in view["sources"]):
            raise ValueError("Source is not part of the current committed snapshot.")
        from ..ingestion import source_view  # local import keeps the module surface small
        try:
            body = await run_in_threadpool(source_view, scope.workspace, source_id, 1, MAX_LINES)
        except HTTPException as exc:
            raise _unavailable(exc) from None
        text = "\n".join(line["text"] for line in body["lines"])[:MAX_CHARS]
        shown = min(body["line_count"], MAX_LINES)
        locator = f"{body['name']} lines 1-{shown} of {body['line_count']}"
        if body["line_count"] > shown or len(text) == MAX_CHARS:
            text += "\n[Truncated for review; request a narrower excerpt for the remainder.]"
        return SourceSpan(id=source_id, snapshot_id=scope.snapshot_id, text=text, locator=locator)

    async def calculate(self, scope: Scope, calculation_id: str) -> Calculation:
        raise ValueError(
            "No deterministic calculation is published for this workspace. Amounts must come from the "
            "accounting engine, not from an agent or this bridge."
        )
