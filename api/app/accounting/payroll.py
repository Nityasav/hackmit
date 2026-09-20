"""Deterministic payroll and budget calculations. Integer cents, no model involvement.

Owner: Functionality (`app/accounting/`). The CFO architecture requires every
confirmed amount to come from this engine so the Internal Auditor can reperform
it through the same code path and reach an identical result. Nothing here reads
a model, a document body, or evaluator truth: each calculation is a pure
function of the committed structured records in one snapshot.

Scope boundary worth stating plainly: percentages written in prose evidence
(a service memo saying "60% student support") are NOT parsed here. Extracting an
allocation rate from free text is document interpretation, not accounting, and a
number obtained that way would defeat the provenance guarantee. Where an
allocation depends on such evidence this module reports the exposure it can
establish from structured records and leaves the split to a later structured
allocation record. Invariant IDs refer to ACCOUNTING_CONTROLS.md sections 2 and 6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Category = Literal["reclassification", "exposure", "potential_recovery", "none"]

# Chart accounts whose report_mapping marks them as payroll for the tie-out.
PAYROLL_MAPPING = "payroll"


@dataclass(frozen=True)
class PayrollCalculation:
    """One reperformable amount, bound to the sources it was derived from."""

    id: str
    description: str
    source_ids: tuple[str, ...]
    amount_cents: int
    cash_delta_cents: int
    category: Category
    basis: str


def _records(records: list[dict], role: str) -> list[dict]:
    return [r for r in records if r["role"] == role]


def _sources(rows: list[dict]) -> tuple[str, ...]:
    """Deterministic, de-duplicated source IDs backing a set of records."""
    return tuple(sorted({r["source_id"] for r in rows}))


def _total(rows: list[dict], field: str) -> int:
    return sum(r["payload"][field] for r in rows)


def _award_ceilings(grants: list[dict]) -> dict[str, int]:
    return {r["payload"]["award_id"]: r["payload"]["ceiling_cents"] for r in grants}


def _award_windows(grants: list[dict]) -> dict[str, tuple[str, str]]:
    return {r["payload"]["award_id"]: (r["payload"]["valid_from"], r["payload"]["valid_to"]) for r in grants}


def _allocated(payroll: list[dict]) -> list[dict]:
    """Payroll records carrying a nonzero restricted-award allocation."""
    return [r for r in payroll if r["payload"].get("award_amount_cents", 0) > 0]


def gross_to_net(payroll: list[dict]) -> PayrollCalculation:
    """AC-06/§6: gross less employee deductions must reconcile to recorded net pay."""
    residual = _total(payroll, "gross_cents") - _total(payroll, "deductions_cents") - _total(payroll, "net_cents")
    return PayrollCalculation(
        id="payroll-gross-to-net",
        description="Aggregate payroll gross pay less employee deductions, compared with recorded net pay.",
        source_ids=_sources(payroll),
        amount_cents=residual,
        cash_delta_cents=0,
        category="none" if residual == 0 else "exposure",
        basis=(f"{len(payroll)} payroll records reconcile gross less deductions to net."
               if residual == 0 else
               f"{len(payroll)} payroll records leave an unreconciled gross-to-net difference."),
    )


def total_expense(payroll: list[dict]) -> PayrollCalculation:
    """§6: payroll expense is gross compensation plus employer costs, not net pay."""
    amount = _total(payroll, "gross_cents") + _total(payroll, "employer_cost_cents")
    return PayrollCalculation(
        id="payroll-total-expense",
        description="Total payroll expense: gross compensation plus employer costs. Net salary payments are not the expense.",
        source_ids=_sources(payroll),
        amount_cents=amount,
        cash_delta_cents=0,
        category="none",
        basis=f"Gross plus employer cost across {len(payroll)} payroll records.",
    )


def award_allocation(payroll: list[dict]) -> PayrollCalculation:
    """Total payroll cost charged to restricted awards."""
    allocated = _allocated(payroll)
    return PayrollCalculation(
        id="payroll-award-allocation",
        description="Total payroll cost allocated to restricted awards across the committed payroll records.",
        source_ids=_sources(payroll),
        amount_cents=_total(allocated, "award_amount_cents"),
        cash_delta_cents=0,
        category="none",
        basis=f"{len(allocated)} of {len(payroll)} payroll records carry an award allocation.",
    )


def ceiling_excess(payroll: list[dict], grants: list[dict]) -> PayrollCalculation:
    """Allocation charged beyond a stated award ceiling, per award then summed."""
    ceilings = _award_ceilings(grants)
    charged: dict[str, int] = {}
    for record in _allocated(payroll):
        award = record["payload"].get("award_id", "")
        charged[award] = charged.get(award, 0) + record["payload"]["award_amount_cents"]
    over = {award: total - ceilings[award] for award, total in charged.items()
            if award in ceilings and total > ceilings[award]}
    excess = sum(over.values())
    return PayrollCalculation(
        id="payroll-award-ceiling-excess",
        description="Payroll allocation charged to an award in excess of that award's stated ceiling.",
        source_ids=_sources(payroll + grants),
        amount_cents=excess,
        cash_delta_cents=0,
        category="exposure" if excess else "none",
        basis=(f"{len(over)} award(s) exceed their ceiling: " + ", ".join(sorted(over)) if over
               else f"No award exceeds its ceiling across {len(charged)} charged award(s)."),
    )


def outside_award_window(payroll: list[dict], grants: list[dict]) -> PayrollCalculation:
    """Allocation whose service period falls outside the award's validity window.

    Allocability under §6: a cost is charged to the period of actual service. A
    service period that starts before or ends after the award window is reported
    in full, because the structured records do not say which days fall inside.
    """
    windows = _award_windows(grants)
    outside = []
    for record in _allocated(payroll):
        payload = record["payload"]
        window = windows.get(payload.get("award_id", ""))
        if window and not (window[0] <= payload["service_start"] and payload["service_end"] <= window[1]):
            outside.append(record)
    amount = _total(outside, "award_amount_cents")
    return PayrollCalculation(
        id="payroll-outside-award-window",
        description="Payroll allocated to an award whose service period is not fully inside that award's validity window.",
        source_ids=_sources(payroll + grants),
        amount_cents=amount,
        cash_delta_cents=0,
        category="reclassification" if amount else "none",
        basis=(", ".join(sorted(r["record_key"] for r in outside)) if outside
               else "Every allocated service period falls inside its award window."),
    )


def unknown_award(payroll: list[dict], grants: list[dict]) -> PayrollCalculation:
    """Allocation referencing an award with no supplied award record."""
    known = set(_award_ceilings(grants))
    unmatched = [r for r in _allocated(payroll) if r["payload"].get("award_id", "") not in known]
    amount = _total(unmatched, "award_amount_cents")
    return PayrollCalculation(
        id="payroll-unknown-award",
        description="Payroll allocated to an award identifier that has no corresponding award record in this snapshot.",
        source_ids=_sources(payroll + grants) or _sources(payroll),
        amount_cents=amount,
        cash_delta_cents=0,
        category="exposure" if amount else "none",
        basis=(", ".join(sorted({r["payload"].get("award_id", "") for r in unmatched})) if unmatched
               else "Every allocation references a supplied award record."),
    )


def unsupported_by_service_evidence(payroll: list[dict], service_present: bool) -> PayrollCalculation:
    """§6: a budgeted percentage is not evidence of actual service.

    With no service record in the snapshot at all, the entire restricted
    allocation is unsupported and is a reclassification candidate. Once service
    evidence exists this reports zero: whether that evidence actually supports
    the recorded split is a matter for the specialist and the auditor to read,
    and any resulting split needs a structured allocation record, not prose.
    """
    allocated = _allocated(payroll)
    amount = 0 if service_present else _total(allocated, "award_amount_cents")
    return PayrollCalculation(
        id="payroll-unsupported-by-service-evidence",
        description="Restricted payroll allocation with no service record of any kind in the snapshot to support it.",
        source_ids=_sources(payroll),
        amount_cents=amount,
        cash_delta_cents=0,
        category="reclassification" if amount else "none",
        basis=("A service record is present; this calculation does not judge whether it supports the recorded split."
               if service_present else
               f"No service record is committed, leaving {len(allocated)} allocated payroll record(s) unsupported."),
    )


def ledger_tie(payroll: list[dict], ledger: list[dict], chart: list[dict]) -> PayrollCalculation:
    """Payroll expense per the subledger against payroll-mapped ledger activity (L07)."""
    accounts = {r["payload"]["account"] for r in chart if r["payload"].get("report_mapping") == PAYROLL_MAPPING}
    lines = [r for r in ledger if r["payload"]["account"] in accounts]
    posted = sum(r["payload"]["debit_cents"] - r["payload"]["credit_cents"] for r in lines)
    subledger = _total(payroll, "gross_cents") + _total(payroll, "employer_cost_cents")
    residual = subledger - posted
    return PayrollCalculation(
        id="payroll-ledger-tie",
        description="Payroll subledger expense compared with net activity posted to payroll-mapped ledger accounts.",
        source_ids=_sources(payroll + ledger + chart),
        amount_cents=residual,
        cash_delta_cents=0,
        category="none" if residual == 0 else "exposure",
        basis=(f"Subledger ties to {len(lines)} ledger line(s) on account(s) " + ", ".join(sorted(accounts))
               if residual == 0 else
               f"Subledger and {len(lines)} payroll ledger line(s) differ; this is a reconciling item, not a proven error."),
    )


def calculations(records: list[dict], service_present: bool) -> list[PayrollCalculation]:
    """Every payroll calculation this snapshot supports, in a stable order.

    An empty list means the snapshot carries no payroll records, so no payroll
    amount may be asserted at all.
    """
    payroll = _records(records, "payroll")
    if not payroll:
        return []
    grants = _records(records, "grants")
    ledger = _records(records, "ledger")
    chart = _records(records, "chart")

    results = [gross_to_net(payroll), total_expense(payroll), award_allocation(payroll),
               unsupported_by_service_evidence(payroll, service_present), unknown_award(payroll, grants)]
    if grants:
        results += [ceiling_excess(payroll, grants), outside_award_window(payroll, grants)]
    if ledger and chart:
        results.append(ledger_tie(payroll, ledger, chart))
    return sorted(results, key=lambda c: c.id)
