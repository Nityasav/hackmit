"""Deterministic restricted-award calculations across every charging source.

`payroll.py` already tests payroll charges against award terms, but a payroll-only
ceiling test understates an award that is also charged through invoices. This
module answers the award-level question — what has been charged to this award in
total, from everywhere — so the Grants agent can price a finding rather than only
describe it.

The payroll-only calculations stay where they are. These carry distinct IDs and
say plainly which sources they combine, so the two never double count: one is a
statement about payroll, the other a statement about the award.
"""

from __future__ import annotations

from .payroll import PayrollCalculation as Calculation

#: Roles that can carry a charge against a restricted award.
CHARGING_ROLES = ("payroll", "invoice")


def _grants(records: list[dict]) -> list[dict]:
    return [r for r in records if r["role"] == "grants"]


def _sources(rows: list[dict]) -> tuple[str, ...]:
    return tuple(sorted({r["source_id"] for r in rows}))


def _charges(records: list[dict]) -> list[dict]:
    """Every committed charge against a named award, with its amount and date.

    Payroll carries its restricted portion in `award_amount_cents`; an invoice
    charges its whole amount. Normalising here keeps the award tests from caring
    which subledger a charge came from.
    """
    charges = []
    for record in records:
        payload = record["payload"]
        award = payload.get("award_id")
        if not award:
            continue
        if record["role"] == "payroll":
            amount = payload.get("award_amount_cents", 0)
            date = payload.get("service_start")
            end = payload.get("service_end")
        elif record["role"] == "invoice":
            amount = payload.get("amount_cents", 0)
            date = end = payload.get("service_date")
        else:
            continue
        if amount:
            charges.append({"award_id": award, "amount_cents": amount, "start": date, "end": end,
                            "role": record["role"], "source_id": record["source_id"]})
    return charges


def _ceilings(grants: list[dict]) -> dict[str, int]:
    return {r["payload"]["award_id"]: r["payload"]["ceiling_cents"] for r in grants}


def _windows(grants: list[dict]) -> dict[str, tuple[str, str]]:
    return {r["payload"]["award_id"]: (r["payload"]["valid_from"], r["payload"]["valid_to"]) for r in grants}


def _basis_sources(charges: list[dict]) -> str:
    roles = sorted({c["role"] for c in charges})
    return " and ".join(roles) if roles else "no"


def award_charges(records: list[dict], charges: list[dict]) -> Calculation:
    """Total charged to restricted awards from every charging subledger."""
    return Calculation(
        id="grants-award-charges",
        description="Total charged to restricted awards across payroll and invoice records combined.",
        source_ids=_sources([r for r in records if r["role"] in CHARGING_ROLES]),
        amount_cents=sum(c["amount_cents"] for c in charges),
        cash_delta_cents=0,
        category="none",
        basis=f"{len(charges)} charge(s) from {_basis_sources(charges)} record(s).",
    )


def combined_ceiling_excess(records: list[dict], charges: list[dict], grants: list[dict]) -> Calculation:
    """Charges beyond an award's stated ceiling, counting every source together."""
    ceilings = _ceilings(grants)
    charged: dict[str, int] = {}
    for charge in charges:
        charged[charge["award_id"]] = charged.get(charge["award_id"], 0) + charge["amount_cents"]
    over = {award: total - ceilings[award] for award, total in charged.items()
            if award in ceilings and total > ceilings[award]}
    excess = sum(over.values())
    return Calculation(
        id="grants-combined-ceiling-excess",
        description="Charges to an award in excess of its stated ceiling, combining payroll and invoices.",
        source_ids=_sources([r for r in records if r["role"] in CHARGING_ROLES] + grants),
        amount_cents=excess,
        cash_delta_cents=0,
        category="exposure" if excess else "none",
        basis=(f"{len(over)} award(s) exceed their ceiling once every source is counted: "
               + ", ".join(sorted(over)) if over
               else f"No award exceeds its ceiling across {len(charged)} charged award(s)."),
    )


def combined_outside_window(records: list[dict], charges: list[dict], grants: list[dict]) -> Calculation:
    """Charges whose service period falls outside the award's validity window."""
    windows = _windows(grants)
    outside = [c for c in charges if c["award_id"] in windows
               and (c["start"] or "") and (
                   c["start"] < windows[c["award_id"]][0] or (c["end"] or c["start"]) > windows[c["award_id"]][1])]
    amount = sum(c["amount_cents"] for c in outside)
    return Calculation(
        id="grants-combined-outside-window",
        description="Charges whose service period falls outside the award's validity window, all sources.",
        source_ids=_sources([r for r in records if r["role"] in CHARGING_ROLES] + grants),
        amount_cents=amount,
        cash_delta_cents=0,
        category="exposure" if amount else "none",
        basis=(f"{len(outside)} charge(s) fall outside their award window."
               if outside else f"All {len(charges)} charge(s) fall within their award window."),
    )


def charges_to_unknown_award(records: list[dict], charges: list[dict], grants: list[dict]) -> Calculation:
    """Charges naming an award that the committed grant register does not contain."""
    known = set(_ceilings(grants))
    unknown = [c for c in charges if c["award_id"] not in known]
    amount = sum(c["amount_cents"] for c in unknown)
    return Calculation(
        id="grants-charges-to-unknown-award",
        description="Charges naming an award absent from the committed grant register, all sources.",
        source_ids=_sources([r for r in records if r["role"] in CHARGING_ROLES] + grants),
        amount_cents=amount,
        cash_delta_cents=0,
        category="exposure" if amount else "none",
        basis=(f"{len({c['award_id'] for c in unknown})} award identifier(s) are not in the register: "
               + ", ".join(sorted({c["award_id"] for c in unknown})) if unknown
               else f"Every charged award appears in the register of {len(known)} award(s)."),
    )


def calculations(records: list[dict]) -> list[Calculation]:
    """Every award-level calculation this snapshot supports, in a stable order.

    An empty list means nothing is charged to a named award, so no award amount
    may be asserted at all.
    """
    charges = _charges(records)
    if not charges:
        return []
    grants = _grants(records)
    results = [award_charges(records, charges), charges_to_unknown_award(records, charges, grants)]
    if grants:
        results += [combined_ceiling_excess(records, charges, grants),
                    combined_outside_window(records, charges, grants)]
    return sorted(results, key=lambda c: c.id)
