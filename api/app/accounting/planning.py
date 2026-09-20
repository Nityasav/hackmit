"""Budgets rolled up, forecasts scored, and scenarios projected.

Three things FP&A does that are not variance analysis, kept deterministic for the same
reason everything else here is: a figure a model wrote is a figure nobody can check.

## A scenario is not a result, and this module says so in its output

`scenario()` is the one place in the engine that produces numbers about a period that has
not happened. They are arithmetic on assumptions someone supplied, which makes them
reproducible but not measured, and every one of them is returned under `projection` with
the assumptions that produced it attached. C4 escalates unconditionally for the same
reason: there is nothing to score a projection against, so it always goes to a person.

## Per-head figures

`roll_up()` divides cost by headcount where headcount was supplied. That ratio is easy to
misread — it is cost per recorded head in one period, not a salary, not a fully loaded
cost, and not comparable across companies that count heads differently. It is returned
with that caveat rather than as a bare number.
"""

from __future__ import annotations

from collections import defaultdict

from . import statements, variance

#: How many future periods `scenario()` will project before refusing.
MAX_HORIZON = 24


def _by_role(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["role"]].append(record)
    return grouped


def roll_up(records: list[dict], config: dict | None = None) -> dict:
    """The budget and the actuals gathered into the categories the chart already names.

    Rolled up by `report_mapping` rather than by a grouping invented here, so the
    categories on a management report are the same ones the statements use. Inventing a
    second taxonomy is how two reports of the same period stop agreeing.
    """
    config = config or {}
    grouped = _by_role(records)
    period = str(config.get("start", ""))[:7]
    rows = statements.balances(records)["accounts"]
    comparison = variance.budget_vs_actual(records, config, plan="budgets")
    by_account = {line["account"]: line for line in comparison["lines"]}

    categories: dict[str, dict] = {}
    for account, row in rows.items():
        if row["type"] not in ("revenue", "expense"):
            continue
        actual = variance._actual(row)
        line = by_account.get(account)
        if not actual and not line:
            continue
        mapping = row["mapping"] or "uncategorized"
        bucket = categories.setdefault(mapping, {
            "category": mapping, "type": row["type"],
            "planned_cents": 0, "actual_cents": 0, "budgeted_actual_cents": 0,
            "unplanned_actual_cents": 0, "accounts": [], "unplanned_accounts": [],
        })
        bucket["actual_cents"] += actual
        bucket["accounts"].append(account)
        if line:
            bucket["planned_cents"] += line["planned_cents"]
            bucket["budgeted_actual_cents"] += actual
        elif actual:
            # Named at the category it lands in, so a roll-up cannot present a total as
            # fully budgeted when part of it was never in the budget at all.
            bucket["unplanned_accounts"].append(account)
            bucket["unplanned_actual_cents"] += actual

    heads = [r["payload"] for r in grouped["headcount"]
             if not period or r["payload"].get("period") == period]
    total_heads = sum(h.get("count", 0) for h in heads)

    for bucket in categories.values():
        # Against the budgeted part only. Measuring the whole category against a plan
        # that covers half of it reports the unbudgeted half as a variance, which reads
        # as an overspend against a budget nobody ever set — and a category with no
        # budget at all has no variance, rather than a variance equal to itself.
        bucket["variance_cents"] = (
            bucket["budgeted_actual_cents"] - bucket["planned_cents"]
            if bucket["accounts"] != bucket["unplanned_accounts"] else None)
        bucket["fully_budgeted"] = not bucket["unplanned_accounts"]
        bucket["cost_per_head_cents"] = (
            bucket["actual_cents"] // total_heads
            if total_heads and bucket["type"] == "expense" else None)

    return {
        "period": period,
        "categories": sorted(categories.values(), key=lambda c: -abs(c["actual_cents"])),
        "headcount": {
            "total": total_heads,
            "by_department": sorted(
                ({"department": h.get("department", ""), "count": h.get("count", 0)}
                 for h in heads), key=lambda h: -h["count"]),
        },
        "note": "Categories come from the chart's own report mapping, so a management "
                "view and the statements group the same accounts the same way. A "
                "variance is against the budgeted part of a category only; where nothing "
                "in it was budgeted there is no variance, which is not a variance of "
                "zero. Cost per head is this period's recorded cost over this period's "
                "recorded heads: not a salary, not a fully loaded cost, and not "
                "comparable across companies that count heads differently."
                if total_heads else
                "Categories come from the chart's own report mapping. A variance is "
                "against the budgeted part of a category only. No headcount was supplied "
                "for this period, so no per-head figure is given.",
    }


def forecast_accuracy(records: list[dict], config: dict | None = None) -> dict:
    """How the forecast did, account by account, and what each forecast claimed as its basis.

    A miss is reported with the basis the forecast recorded for itself. "Prior period run
    rate" missing by a third is a different fact from a bottom-up build missing by a third,
    and a report that gives only the miss throws away the half that says what to fix.
    """
    comparison = variance.budget_vs_actual(records, config, plan="forecasts")
    misses = []
    for line in comparison["lines"]:
        planned = line["planned_cents"]
        misses.append({
            "account": line["account"], "name": line["name"], "type": line["type"],
            "forecast_cents": planned, "actual_cents": line["actual_cents"],
            "miss_cents": line["variance_cents"],
            # Against the forecast, not against the actual: the question is how wrong the
            # forecast was, and dividing by the outcome answers a different one.
            "miss_pct": None if not planned else abs(line["variance_cents"]) * 100 // abs(planned),
            "basis": line["authority"] or "No basis was recorded with this forecast.",
            "evidence": line["evidence"],
        })
    ranked = sorted(misses, key=lambda m: -(m["miss_pct"] or 0))
    return {
        "period": comparison["period"],
        "accounts": ranked,
        "unforecast": comparison["unplanned"],
        "totals": comparison["totals"],
        "worst": ranked[0] if ranked else None,
        "note": "A miss is measured against what was forecast, not against what happened. "
                "Accounts with no forecast line are listed separately rather than scored "
                "as perfect.",
    }


def scenario(records: list[dict], config: dict | None = None, *,
             revenue_growth_pct: int = 0, expense_growth_pct: int = 0,
             headcount_change: int = 0, periods: int = 3) -> dict:
    """Project the period forward under assumptions someone supplied.

    Every figure returned describes a period that has not happened. They are labelled as a
    projection throughout and carry the assumptions that produced them, because a
    projection separated from its assumptions is indistinguishable from a measurement.
    """
    if not 1 <= periods <= MAX_HORIZON:
        raise ValueError("Projections run from 1 to " + str(MAX_HORIZON) + " periods.")
    income = statements.income_statement(records)
    base_revenue = income["total_revenue_cents"]
    base_expense = income["total_expense_cents"]
    grouped = _by_role(records)
    period = str((config or {}).get("start", ""))[:7]
    heads = sum(r["payload"].get("count", 0) for r in grouped["headcount"]
                if not period or r["payload"].get("period") == period)

    projection, revenue, expense = [], base_revenue, base_expense
    for step in range(1, periods + 1):
        # Integer arithmetic throughout, so a projection repeated is a projection
        # reproduced. Floor division is applied to the growth, not to the base.
        revenue += revenue * revenue_growth_pct // 100
        expense += expense * expense_growth_pct // 100
        projection.append({
            "period_offset": step,
            "revenue_cents": revenue,
            "expense_cents": expense,
            "result_cents": revenue - expense,
            "headcount": heads + headcount_change * step,
        })

    return {
        "basis": {
            "period": period,
            "revenue_cents": base_revenue,
            "expense_cents": base_expense,
            "result_cents": income["net_income_cents"],
            "headcount": heads,
            "source": "This period's income statement, computed from the ledger.",
        },
        "assumptions": {
            "revenue_growth_pct": revenue_growth_pct,
            "expense_growth_pct": expense_growth_pct,
            "headcount_change_per_period": headcount_change,
            "periods": periods,
            "supplied_by": "the person who asked for the scenario",
        },
        "projection": projection,
        "measured": False,
        "note": "A projection, not a result. Every figure under 'projection' describes a "
                "period that has not happened and follows arithmetically from the "
                "assumptions above. Changing an assumption changes all of them, and "
                "nothing here has been compared with an outcome.",
    }
