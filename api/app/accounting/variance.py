"""Why actuals differ from plan, traced to the transactions that caused it.

The phase-6 gate is one sentence: **a variance decomposes to named transactions.** Not to
categories, not to a narrative, not to a percentage — to rows a person can open. An
explanation that stops at "cloud hosting was over budget" has restated the variance rather
than explained it.

## The arithmetic is the explanation

`decompose()` takes one account's activity and lists the economic events inside it, each
with the amount it contributed and the records behind it. Those contributions sum to the
actual exactly, and that identity is asserted before anything is returned. There is no
room for a model to add, drop or round a driver, because it never handles them.

## What "unexplained" means here, precisely

An entry that no economic event claims cannot be traced any further from the ledger alone.
Its amount is reported as `unexplained_cents` and it is still listed — never netted away,
never absorbed into a neighbouring driver. `attributed_pct` is the share of the actual that
*did* reach a named transaction, floored so it never rounds up into confidence it has not
earned, and that figure is what C3's escalation threshold reads. An agent cannot talk its
way past it.

## Signs

Variance is always `actual - plan`, in one direction for every account, so the number means
the same thing everywhere. Whether that is good news depends on the account type and is
reported separately as `favourable`. Totals are given per account type and never across
them: adding an expense overspend to a revenue shortfall produces a figure that describes
nothing.
"""

from __future__ import annotations

from collections import defaultdict

from . import statements

#: Plan roles this module can measure against, and what to call each on a screen.
PLANS = {"budgets": "the approved budget", "forecasts": "the forecast"}

#: Where a driver stops being worth naming individually. Everything below it is still
#: counted, and reported as a named group with its population size — never dropped.
DEFAULT_DRIVER_FLOOR_CENTS = 2_500


def _by_role(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["role"]].append(record)
    return grouped


def _actual(row: dict) -> int:
    """The period's activity on an account, in the direction the account is read.

    Movements are signed debit-minus-credit throughout the engine. Revenue carries a
    credit balance, so its movement is negative; presenting it that way against a positive
    budget would report every revenue line as an enormous shortfall.
    """
    return -row["movement_cents"] if row["type"] == "revenue" else row["movement_cents"]


def _plan_lines(grouped, plan: str, period: str) -> dict[str, dict]:
    out = {}
    for record in grouped[plan]:
        payload = record["payload"]
        if period and payload.get("period") != period:
            continue
        out[payload.get("account", "")] = {
            "amount_cents": payload.get("amount_cents", 0),
            "record_key": record["record_key"],
            "source_id": record["source_id"],
            "line": record["locator"],
            # A budget carries the approval that set it; a forecast carries its basis.
            # Both answer "who said this number", which is the first thing anyone asks
            # about a variance.
            "authority": payload.get("approval_reference") or payload.get("basis") or "",
        }
    return out


def budget_vs_actual(records: list[dict], config: dict | None = None,
                     *, plan: str = "budgets") -> dict:
    """Every account's actual against its plan, for the period.

    An account with activity and no plan line is *not* excluded, and a plan line for an
    account the chart does not carry is not either. Both are the interesting cases —
    quietly dropping either is how a variance report comes out clean while the thing it
    was meant to surface sits outside the join.
    """
    if plan not in PLANS:
        raise ValueError("No such plan: " + plan)
    config = config or {}
    grouped = _by_role(records)
    period = str(config.get("start", ""))[:7]
    rows = statements.balances(records)["accounts"]
    planned = _plan_lines(grouped, plan, period)

    lines, unplanned, outside_chart = [], [], []
    for account in sorted(set(rows) | set(planned)):
        row = rows.get(account)
        entry = planned.get(account)
        if row is None:
            outside_chart.append({
                "account": account, "planned_cents": entry["amount_cents"],
                "reason": "Planned against an account the chart does not carry, so there "
                          "is nothing to measure it against."})
            continue
        if row["type"] not in ("revenue", "expense"):
            continue
        actual = _actual(row)
        if entry is None:
            if actual:
                unplanned.append({
                    "account": account, "name": row["name"], "type": row["type"],
                    "actual_cents": actual,
                    "reason": "Activity with no line in " + PLANS[plan] + ". It is "
                              "measured against nothing, so it has no variance — which is "
                              "not the same as a variance of zero."})
            continue
        if not actual and not entry["amount_cents"]:
            continue
        variance = actual - entry["amount_cents"]
        lines.append({
            "account": account, "name": row["name"], "type": row["type"],
            "planned_cents": entry["amount_cents"], "actual_cents": actual,
            "variance_cents": variance,
            # Overspending is adverse; over-earning is not. The sign alone does not say.
            "favourable": variance <= 0 if row["type"] == "expense" else variance >= 0,
            "authority": entry["authority"],
            "evidence": [{"role": plan, "record_key": entry["record_key"],
                          "source_id": entry["source_id"], "line": entry["line"]}],
        })

    totals = {}
    for account_type in ("revenue", "expense"):
        selected = [line for line in lines if line["type"] == account_type]
        totals[account_type] = {
            "planned_cents": sum(line["planned_cents"] for line in selected),
            "actual_cents": sum(line["actual_cents"] for line in selected),
            "variance_cents": sum(line["variance_cents"] for line in selected),
            "lines": len(selected),
        }

    return {
        "plan": plan,
        "period": period,
        "lines": sorted(lines, key=lambda line: -abs(line["variance_cents"])),
        "unplanned": unplanned,
        "planned_outside_chart": outside_chart,
        "totals": totals,
        "note": "Actuals against " + PLANS[plan] + ", in exact cents. Totals are given per "
                "account type and never added across them: an expense overspend and a "
                "revenue shortfall are not the same quantity.",
    }


def decompose(records: list[dict], account: str, config: dict | None = None,
              *, plan: str = "budgets",
              floor_cents: int = DEFAULT_DRIVER_FLOOR_CENTS) -> dict:
    """One account's actual, broken into the transactions that make it up.

    This is the gate. Every driver names an economic event and the ledger lines behind it,
    the contributions sum to the actual exactly, and anything no event claims is reported
    as unexplained rather than folded into its neighbours.
    """
    config = config or {}
    grouped = _by_role(records)
    rows = statements.balances(records)["accounts"]
    if account not in rows:
        return {"account": account, "found": False, "drivers": [], "actual_cents": 0,
                "unexplained_cents": 0, "attributed_pct": 100,
                "note": "No such account in the chart or in the ledger."}

    row = rows[account]
    sign = -1 if row["type"] == "revenue" else 1
    comparison = budget_vs_actual(records, config, plan=plan)
    line = next((item for item in comparison["lines"] if item["account"] == account), None)

    by_event: dict[str, dict] = {}
    unexplained_cents = 0
    for record in grouped["ledger"]:
        payload = record["payload"]
        if payload.get("account") != account:
            continue
        amount = sign * (payload.get("debit_cents", 0) - payload.get("credit_cents", 0))
        reference = payload.get("event_ref") or ""
        if not reference:
            # No event claims it, so the ledger alone cannot say what it was for.
            unexplained_cents += amount
        bucket = by_event.setdefault(reference, {
            "event_ref": reference or None,
            "amount_cents": 0,
            "entries": 0,
            "entry_ids": [],
            "evidence": [],
            "traceable": bool(reference),
        })
        bucket["amount_cents"] += amount
        bucket["entries"] += 1
        if payload.get("entry_id") and payload["entry_id"] not in bucket["entry_ids"]:
            bucket["entry_ids"].append(payload["entry_id"])
        bucket["evidence"].append({
            "role": "ledger", "record_key": record["record_key"],
            "source_id": record["source_id"], "line": record["locator"]})

    ranked = sorted(by_event.values(), key=lambda bucket: -abs(bucket["amount_cents"]))
    named = [b for b in ranked if abs(b["amount_cents"]) >= floor_cents]
    smaller = [b for b in ranked if abs(b["amount_cents"]) < floor_cents]
    drivers = list(named)
    if smaller:
        # Counted, named and sized. A tail that is dropped instead is how a
        # decomposition comes out tidy and wrong.
        drivers.append({
            "event_ref": None,
            "amount_cents": sum(b["amount_cents"] for b in smaller),
            "entries": sum(b["entries"] for b in smaller),
            "entry_ids": [],
            "evidence": [],
            "traceable": all(b["traceable"] for b in smaller),
            "grouped": len(smaller),
            "label": str(len(smaller)) + " item(s) below " + str(floor_cents)
                     + " cent(s), counted together rather than listed",
        })

    actual = _actual(row)
    lost = actual - sum(driver["amount_cents"] for driver in drivers)
    # The identity the whole module rests on. A decomposition that does not add up is not
    # a smaller error than a wrong one; it is the same error, harder to see.
    assert lost == 0, "decomposition of " + account + " lost " + str(lost) + " cent(s)"

    attributed = actual - unexplained_cents
    return {
        "account": account, "name": row["name"], "type": row["type"], "found": True,
        "actual_cents": actual,
        "planned_cents": line["planned_cents"] if line else None,
        "variance_cents": line["variance_cents"] if line else None,
        "favourable": line["favourable"] if line else None,
        "drivers": drivers,
        "named_drivers": len(named),
        "unexplained_cents": unexplained_cents,
        # Floored: a decomposition that reached 99.6% reports 99, because rounding up is
        # how a gap comes to be described as complete.
        "attributed_pct": 100 if not actual else max(
            0, min(100, abs(attributed) * 100 // abs(actual))),
        "note": "Each driver is one economic event, with the ledger lines behind it. "
                "Contributions sum to the actual exactly. An entry no event claims is "
                "reported as unexplained, never absorbed into another driver.",
    }


def explain(records: list[dict], config: dict | None = None, *, plan: str = "budgets",
            limit: int = 5) -> dict:
    """The largest variances, each already decomposed to its transactions.

    What C3 reads. The model's job downstream of this is to say what the drivers mean, and
    it is given no opportunity to compute one.
    """
    comparison = budget_vs_actual(records, config, plan=plan)
    worst = [line for line in comparison["lines"] if line["variance_cents"]][:limit]
    explained = [decompose(records, line["account"], config, plan=plan) for line in worst]
    return {
        "plan": plan,
        "comparison": comparison,
        "explained": explained,
        # One figure for the whole task, so an escalation threshold has something to read.
        # The weakest decomposition sets it: an agent is only as traceable as its worst line.
        "attributed_pct": min((item["attributed_pct"] for item in explained), default=100),
        "unexplained_cents": sum(item["unexplained_cents"] for item in explained),
        "amount_cents": sum(abs(line["variance_cents"]) for line in worst),
        "note": "The largest variances by absolute size, which is not the same as by "
                "importance. A small variance on a sensitive account may matter more.",
    }
