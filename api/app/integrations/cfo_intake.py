"""CFO DataSource over committed intake snapshots.

Bridges the intake layer (`app/ingestion.py`, owned by Functionality) to the CFO
ports so the coordinator investigates real uploaded records. It never stages,
commits, mutates records, publishes snapshots, or reaches evaluator truth. Its
single write is `note_precedent_uses`, which increments a counter recording
that a run weighed a human decision; it cannot create precedent or alter
anything an agent reads as evidence.

Amounts are never computed here. The accounting engine is Functionality's
(`app/accounting/`); this module only forwards its results, because the CFO's
provenance checks require an amount to come from the same engine the auditor
reperforms. Calculations are published from `accounting/payroll.py`,
`accounting/ap.py` and `accounting/grants.py`. A domain with no committed
records still carries no calculations, and `calculate` fails closed for it, so
that specialist can cite evidence and explain a finding but cannot assert an
amount.
"""

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from ..cfo.schemas import Calculation, CalculationSpec, Precedent, Scope, Source, SourceSpan
from ..ingestion import coverage, financial_records

# Intake roles map onto the three specialist domains; everything else is shared context.
# This vocabulary is the old five-agent one and is replaced in phase 3, when workers
# become A/B/C/D and the domain literal widens with them.
DOMAINS = {
    "vendors": "ap", "vendor_invoices": "ap", "purchase_orders": "ap",
    "goods_receipts": "ap", "payments": "ap",
    "payroll": "py", "expenses": "py", "budgets": "py", "forecasts": "py", "headcount": "py",
    "customers": "gr", "customer_invoices": "gr", "remittances": "gr",
}
MAX_LINES = 400
MAX_CHARS = 20_000


def _precedents(workspace: str) -> list[Precedent]:
    """Reviewed human decisions for this workspace, newest-relevant first.

    Read through the same accessor the triage agent uses, so the two run paths
    are offered the same memory rather than two drifting copies of it.
    """
    from .. import approvals, db  # local import keeps the module surface small

    with db.connect() as connection:
        rows = approvals.active_precedents(connection, workspace)
    return [
        Precedent(id=row["id"], pattern=row["pattern"],
                  verdict=row["verdict"], guidance=row["guidance"])
        for row in rows
    ]


def _note_precedent_uses(workspace: str, precedent_ids: list[str]) -> None:
    from .. import approvals, db

    with db.connect() as connection:
        approvals.note_precedent_uses(connection, workspace, precedent_ids)


def _unavailable(exc: HTTPException) -> ValueError:
    """Keep intake's HTTP error shape out of the CFO run loop."""
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return ValueError(detail.get("message") or "Intake workspace is unavailable.")


async def _snapshot_view(workspace: str) -> dict:
    try:
        return await run_in_threadpool(coverage, workspace)
    except HTTPException as exc:
        raise _unavailable(exc) from None


async def _engine_calculations(workspace: str, available: set[str], config: dict) -> list:
    """Deterministic amounts for this snapshot, restricted to readable sources.

    Empty until the phase-4 engine lands in `accounting/`. The coordinator treats an
    empty inventory correctly on its own: `calculate` fails closed, so a specialist can
    cite evidence and describe a finding but cannot assert an amount. That is the right
    behaviour while the calculations are being rebuilt — better a stated gap than a
    number with nothing behind it.
    """
    # Touched so the signature stays honest about what it will read.
    await run_in_threadpool(financial_records, workspace)
    return []


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
        # Missing inputs come from the one registry Books also renders, so the run is
        # told about a gap in the same words the person was asked to fill it.
        gaps = [f"{r['label']} has not been supplied: {r['unlocks']}"
                for r in view["requirements"] if not r["satisfied"] and not r["optional"]]
        gaps += [f"Open evidence request ({r['role']}): {r['title']}."
                 for r in view["requests"] if r["status"] in {"open", "needs_review"}]
        engine = await _engine_calculations(workspace, {s.id for s in sources}, config)
        if not engine:
            gaps.append("No deterministic calculation inventory is published for this workspace; "
                        "amounts cannot be confirmed in this run.")
        return Scope(
            workspace=workspace, snapshot_id=snapshot["id"], institution=config["name"],
            period=f"{config['start']} to {config['end']}", accounting_profile=config["profile"],
            sources=sources,
            calculations=[CalculationSpec(id=c.id, description=c.description, source_ids=list(c.source_ids))
                          for c in engine],
            gaps=gaps,
            precedents=await run_in_threadpool(_precedents, workspace),
        )

    async def note_precedent_uses(self, workspace: str, precedent_ids: list[str]) -> None:
        if not precedent_ids:
            return
        await run_in_threadpool(_note_precedent_uses, workspace, precedent_ids)

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
        view = await _snapshot_view(scope.workspace)
        # An amount is only reperformable against the snapshot it was planned on.
        if view["snapshot"] is None or view["snapshot"]["id"] != scope.snapshot_id:
            raise ValueError("The snapshot changed since this run started; rerun against the current snapshot.")
        available = {s["id"] for s in view["sources"] if _usable(s)}
        engine = await _engine_calculations(scope.workspace, available, view["workspace"])
        result = next((c for c in engine if c.id == calculation_id), None)
        if result is None:
            raise ValueError(
                "No deterministic calculation is published for this identifier. Amounts must come from the "
                "accounting engine, not from an agent or this bridge."
            )
        return Calculation(
            id=result.id, snapshot_id=scope.snapshot_id, source_ids=list(result.source_ids),
            amount_cents=result.amount_cents, cash_delta_cents=result.cash_delta_cents,
            category=result.category, description=f"{result.description} Basis: {result.basis}",
        )
