"""Everything a finished document needs, gathered once, computed in one place.

A deliverable is not a new analysis. It is the period's existing figures arranged for
someone who was not in the room, so this endpoint recomputes nothing that the accounting
modules already own — it calls them and returns what they say.

## Why this is a single endpoint

A one-page snapshot that fetched statements from one route, the close from another and
controls from a third would be assembling a document out of four reads taken at four
moments. Between the first and the last, a commit can land. The figures would each be
true and the page as a whole would be of no particular period.

So: one read, one snapshot id, one `prepared_at`. If the books move, the next fetch says
so, and the document a person is looking at is still internally consistent.

## No model touches any of this

Every number here comes from `accounting/`, in integer cents. The renderer formats them
and writes nothing. That is what makes a PDF from this safe to hand to a board: the
figures on it were derived, and the same inputs give the same page.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import db, ingestion, roles as role_registry
from .accounting import accruals, close, controls, reconcile, statements, variance

router = APIRouter(prefix="/api/workspaces/{ws}", tags=["Deliverables"])

#: How many exceptions and variance lines a one-page document can carry before it stops
#: being one page. The rest are counted, never silently dropped.
PAGE_LIMIT = 6


@router.get("/deliverables/snapshot")
def snapshot(ws: str):
    """The period on one page: result, position, close, exceptions, drivers.

    Deterministic and free. Nothing here calls a model, so a person can regenerate this
    as often as they like and get the same document from the same books.
    """
    config = ingestion.workspace_config(ws)
    records = ingestion.financial_records(ws)["records"]
    coverage = ingestion.coverage(ws)

    figures = statements.statements(records, config)
    checklist = close.checklist(records, config)
    found = controls.checks(records, config)
    exceptions = [c for c in found if c["status"] == "attention"]
    passes = [c for c in found if c["status"] == "pass"]
    gaps = [c for c in found if c["status"] == "gap"]
    against_plan = variance.budget_vs_actual(records, config)
    accrual = accruals.unbilled_receipts(records, config)
    bank = (reconcile.reconcile_bank(records, config)["totals"]
            if any(r["role"] == "bank_transactions" for r in records) else None)

    drivers = [line for line in against_plan["lines"] if line["variance_cents"]]

    return {
        "workspace": {
            "name": config.get("name", ""),
            "start": config.get("start", ""),
            "end": config.get("end", ""),
            "period": str(config.get("start", ""))[:7],
            "jurisdiction": config.get("jurisdiction", ""),
            "currency": config.get("currency", "USD"),
        },
        # One read, one moment. A document assembled from four fetches is a document of
        # no particular period.
        "snapshot_id": coverage.get("snapshot", {}).get("id") if coverage.get("snapshot") else None,
        "prepared_at": db.now(),
        "records": len(records),
        "result": {
            "revenue_cents": figures["income_statement"]["total_revenue_cents"],
            "expense_cents": figures["income_statement"]["total_expense_cents"],
            "net_cents": figures["income_statement"]["net_income_cents"],
            "expense_by_category_cents": figures["income_statement"]["expense_by_category_cents"],
        },
        "position": {
            "assets_cents": figures["balance_sheet"]["total_assets_cents"],
            "liabilities_cents": figures["balance_sheet"]["total_liabilities_cents"],
            "equity_cents": figures["balance_sheet"]["total_equity_cents"],
            "opening_cash_cents": figures["cash_flow"]["opening_cash_cents"],
            "closing_cash_cents": figures["cash_flow"]["closing_cash_cents"],
        },
        # The three identities that decide whether any of the above may be shown at all.
        "checks": {
            "trial_balance_balances": figures["trial_balance"]["balances"],
            "balance_sheet_balances": figures["balance_sheet"]["balances"],
            "balance_sheet_difference_cents": figures["balance_sheet"]["difference_cents"],
            "cash_flow_ties": figures["cash_flow"]["ties"],
            "reliable": figures["reliable"],
            "problems": figures["problems"],
        },
        "close": {
            "ready": checklist["ready"],
            "blocked_by": checklist["blocked_by"],
            "counts": checklist.get("counts", {}),
            "items": checklist["items"],
        },
        "controls": {
            "exceptions": [
                {"id": c["id"], "title": c["title"], "amount_cents": c["amount_cents"],
                 # Readable, because a composite key printed raw reads as `PO-70081` —
                 # a document number that does not exist. On a page someone hands to a
                 # board, that is worse than showing nothing.
                 "records": [role_registry.readable_key(c["role"], k)
                             for k in c["record_keys"]],
                 "action": c["action"]}
                for c in exceptions[:PAGE_LIMIT]],
            "exception_count": len(exceptions),
            # Named, not just counted. "Six tests passed" is a finding; silence is not.
            "passed": [c["title"] for c in passes],
            "pass_count": len(passes),
            "gap_count": len(gaps),
            "omitted": max(0, len(exceptions) - PAGE_LIMIT),
        },
        "variance": {
            "lines": drivers[:PAGE_LIMIT],
            "line_count": len(drivers),
            "omitted": max(0, len(drivers) - PAGE_LIMIT),
            "expense_planned_cents": against_plan["totals"]["expense"]["planned_cents"],
            "expense_actual_cents": against_plan["totals"]["expense"]["actual_cents"],
            "unplanned": against_plan["unplanned"],
        },
        "accruals": {
            "count": len(accrual["proposals"]),
            "total_cents": accrual["total_cents"],
        },
        "bank": bank,
        "limitations": [
            "Prepared from the records supplied for this period. Not an audit opinion, "
            "and not a statement that the population is complete.",
            "Exceptions are questions raised by rules-based tests. A duplicate candidate "
            "is not a duplicate payment, and amounts from different tests may overlap.",
            "Every figure was computed from the ledger in exact cents. No figure on this "
            "page was written by a language model.",
        ],
    }
