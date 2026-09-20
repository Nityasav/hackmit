"""Read-only CFO DataSource over committed intake snapshots.

Bridges the intake layer (`app/ingestion.py`, owned by Functionality) to the CFO
ports so the coordinator investigates real uploaded records. This adapter only
reads: it never stages, commits, mutates records, publishes snapshots, or
reaches evaluator truth.

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

from ..accounting.ap import calculations as ap_calculations
from ..accounting.grants import calculations as grants_calculations
from ..accounting.payroll import PayrollCalculation, calculations as payroll_calculations
from ..accounting.review import checks
from ..cfo.schemas import Calculation, CalculationSpec, Scope, Source, SourceSpan
from ..ingestion import coverage, financial_records

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


async def _engine_calculations(workspace: str, available: set[str], config: dict) -> list[PayrollCalculation]:
    """Deterministic amounts for this snapshot, restricted to readable sources.

    A calculation derived from a superseded source could not be reperformed by
    the auditor through the same evidence, so it is withheld entirely rather
    than published with a partial basis.

    `config` is the workspace record intake already holds, passed through so
    date-bounded checks (pledge ageing reads its period end) run here exactly as
    they do on the review path. Without it they stand themselves down, and this
    caller consumes only amount-bearing AP and budget items, so the gap saying
    they did not run would be filtered away unseen.
    """
    try:
        inputs = await run_in_threadpool(financial_records, workspace)
    except HTTPException as exc:
        raise _unavailable(exc) from None
    service_present = "service" in inputs["roles"]
    records = inputs["records"]
    published = (payroll_calculations(records, service_present)
                 + ap_calculations(records)
                 + grants_calculations(records))
    known = {calculation.id for calculation in published}
    for item in checks(records, config):
        if (item["amount_cents"] is not None
                and item["id"].startswith(("ap-duplicate-", "budget-"))
                and item["id"] not in known):
            published.append(PayrollCalculation(
                id=item["id"], description=item["title"],
                source_ids=tuple(sorted({e["source_id"] for e in item["evidence"]})),
                amount_cents=item["amount_cents"], cash_delta_cents=0,
                category="exposure" if item["status"] == "attention" else "none",
                basis=item["explanation"],
            ))
    return [c for c in published if c.source_ids and set(c.source_ids).issubset(available)]


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
        engine = await _engine_calculations(workspace, {s.id for s in sources}, config)
        if engine:
            domains = sorted({c.id.split("-", 1)[0] for c in engine})
            missing = sorted({"payroll", "ap", "grants"} - set(domains))
            if missing:
                gaps.append("Deterministic amounts are published for " + ", ".join(domains)
                            + " only; " + ", ".join(missing) + " amounts cannot be confirmed in this run.")
            if any(c.id.startswith(("ap-duplicate-", "budget-")) for c in engine):
                gaps.append("Amount inventory includes exact-key invoice duplicate candidates and expense budget variance where supplied. No payment confirmation, full three-way matching, statutory accounts or full-population grant compliance is implied.")
        else:
            gaps.append("No deterministic calculation inventory is published for this workspace; "
                        "amounts cannot be confirmed in this run.")
        return Scope(
            workspace=workspace, snapshot_id=snapshot["id"], institution=config["name"],
            period=f"{config['start']} to {config['end']}", accounting_profile=config["profile"],
            sources=sources,
            calculations=[CalculationSpec(id=c.id, description=c.description, source_ids=list(c.source_ids))
                          for c in engine],
            gaps=gaps,
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
