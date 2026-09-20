"""Financial statements, computed from the ledger in exact integer cents.

**No model writes any of this.** B3 reads what this produces and flags what does not tie;
it never authors a figure. If anyone ever asks whether a language model wrote the balance
sheet, the answer has to be no, and that is why this file exists rather than a prompt.

## Everything comes from two places

Opening balances and posted journal lines. Nothing is estimated, allocated or carried
over from a previous run. An account's balance is its opening position plus its movement,
and a statement line is a sum of account balances — so every number can be traced back to
rows a person can open.

## Why the statements must tie, and what it means when they do not

Each journal balances, and the opening trial balance balances, so across every account
the debits equal the credits. That identity is what makes

    assets = liabilities + equity + net income

hold arithmetically rather than by construction. When it fails, something upstream is
wrong — an unbalanced entry, an account missing from the chart — and the honest response
is to report the difference exactly, not to insert a plug line that makes the statement
presentable. A balance sheet that balances because something was forced into it is worse
than one that visibly does not.

## What these are not

A management income statement, balance sheet and cash-flow summary over supplied records.
Not a statutory package: no consolidation, no deferred tax, no disclosure notes, no
comparatives beyond what was uploaded, and no assurance that the population is complete.
"""

from __future__ import annotations

from collections import defaultdict

#: Chart `report_mapping` values, grouped into the three cash-flow activities. Anything
#: unrecognized is treated as operating and named in `uncategorized`, because silently
#: dropping a cash movement would make the statement tie while hiding the movement.
INVESTING = frozenset({"fixed_assets"})
FINANCING = frozenset({"equity", "debt"})

#: Where an account belongs on the balance sheet, by its chart type.
BALANCE_SHEET_TYPES = ("asset", "liability", "equity")
INCOME_TYPES = ("revenue", "expense")


def _by_role(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["role"]].append(record)
    return grouped


def _chart(grouped) -> dict[str, dict]:
    return {r["payload"]["account"]: r["payload"] for r in grouped["chart"]}


def balances(records: list[dict]) -> dict:
    """Every account's opening position, movement and closing balance, in cents.

    Signed as debits-minus-credits throughout, which keeps the arithmetic in one
    direction; the presentation flips the sign for the accounts that normally carry a
    credit balance. Doing it the other way — flipping per account as you go — is how a
    sign error hides.
    """
    grouped = _by_role(records)
    chart = _chart(grouped)

    opening: dict[str, int] = defaultdict(int)
    movement: dict[str, int] = defaultdict(int)
    unknown: set[str] = set()

    for record in grouped["opening"]:
        payload = record["payload"]
        account = payload.get("account", "")
        (opening if account in chart else opening)[account] += (
            payload.get("debit_cents", 0) - payload.get("credit_cents", 0))
        if account not in chart:
            unknown.add(account)

    for record in grouped["ledger"]:
        payload = record["payload"]
        account = payload.get("account", "")
        movement[account] += payload.get("debit_cents", 0) - payload.get("credit_cents", 0)
        if account not in chart:
            unknown.add(account)

    rows = {}
    for account in sorted(set(opening) | set(movement) | set(chart)):
        detail = chart.get(account, {})
        rows[account] = {
            "account": account,
            "name": detail.get("name", account),
            "type": detail.get("type", "unknown"),
            "mapping": detail.get("report_mapping", ""),
            "opening_cents": opening.get(account, 0),
            "movement_cents": movement.get(account, 0),
            "closing_cents": opening.get(account, 0) + movement.get(account, 0),
        }
    return {"accounts": rows, "unknown_accounts": sorted(unknown)}


def trial_balance(records: list[dict]) -> dict:
    """Debits against credits across every account. The control everything else rests on."""
    rows = balances(records)["accounts"].values()
    debits = sum(r["closing_cents"] for r in rows if r["closing_cents"] > 0)
    credits = -sum(r["closing_cents"] for r in rows if r["closing_cents"] < 0)
    return {
        "debits_cents": debits, "credits_cents": credits,
        "difference_cents": debits - credits,
        "balances": debits == credits,
        "accounts": len(list(rows)),
    }


def income_statement(records: list[dict]) -> dict:
    """Revenue less expenses for the period.

    Movement only, never closing balances: revenue and expense accounts accumulate from
    the start of the year, and a period result that included their opening positions
    would be a year-to-date figure wearing a month's label.
    """
    rows = balances(records)["accounts"]
    revenue, expense = [], []
    for row in rows.values():
        if row["type"] == "revenue" and row["movement_cents"]:
            # Revenue carries a credit balance; present it positive.
            revenue.append({**row, "amount_cents": -row["movement_cents"]})
        elif row["type"] == "expense" and row["movement_cents"]:
            expense.append({**row, "amount_cents": row["movement_cents"]})

    total_revenue = sum(line["amount_cents"] for line in revenue)
    total_expense = sum(line["amount_cents"] for line in expense)
    by_mapping: dict[str, int] = defaultdict(int)
    for line in expense:
        by_mapping[line["mapping"] or "unmapped"] += line["amount_cents"]

    return {
        "revenue": sorted(revenue, key=lambda r: -r["amount_cents"]),
        "expenses": sorted(expense, key=lambda r: -r["amount_cents"]),
        "total_revenue_cents": total_revenue,
        "total_expense_cents": total_expense,
        "net_income_cents": total_revenue - total_expense,
        "expense_by_category_cents": dict(sorted(by_mapping.items())),
        "note": "Movement in the period only. Supplied records; no assurance that the "
                "population is complete and no statutory presentation is implied.",
    }


def balance_sheet(records: list[dict]) -> dict:
    """Position at the end of the period, and whether it balances.

    The period's result is shown as its own equity line rather than folded into retained
    earnings. Folding it in would make the statement balance whatever the ledger said,
    which is exactly the check worth keeping.
    """
    rows = balances(records)["accounts"]
    assets, liabilities, equity = [], [], []
    for row in rows.values():
        if not row["closing_cents"] and row["type"] not in BALANCE_SHEET_TYPES:
            continue
        if row["type"] == "asset":
            assets.append({**row, "amount_cents": row["closing_cents"]})
        elif row["type"] == "liability":
            liabilities.append({**row, "amount_cents": -row["closing_cents"]})
        elif row["type"] == "equity":
            equity.append({**row, "amount_cents": -row["closing_cents"]})

    total_assets = sum(line["amount_cents"] for line in assets)
    total_liabilities = sum(line["amount_cents"] for line in liabilities)
    opening_equity = sum(line["amount_cents"] for line in equity)
    net_income = income_statement(records)["net_income_cents"]
    total_equity = opening_equity + net_income

    difference = total_assets - (total_liabilities + total_equity)
    return {
        "assets": sorted(assets, key=lambda r: -r["amount_cents"]),
        "liabilities": sorted(liabilities, key=lambda r: -r["amount_cents"]),
        "equity": sorted(equity, key=lambda r: -r["amount_cents"]),
        "total_assets_cents": total_assets,
        "total_liabilities_cents": total_liabilities,
        "opening_equity_cents": opening_equity,
        "net_income_cents": net_income,
        "total_equity_cents": total_equity,
        "difference_cents": difference,
        "balances": difference == 0,
        "note": "The period result is shown separately from retained earnings, so the "
                "balance is a check rather than an assumption.",
    }


def _activity(mapping: str) -> str:
    if mapping in INVESTING:
        return "investing"
    if mapping in FINANCING:
        return "financing"
    return "operating"


def cash_flow(records: list[dict]) -> dict:
    """Cash movement by activity, derived from what each cash entry was posted against.

    Direct, not indirect: for every journal touching a cash account, the *other* lines
    say what the movement was for. That keeps each figure traceable to entries a person
    can open, where an indirect reconciliation would derive cash from working-capital
    deltas and lose the link.

    A journal whose non-cash side is missing or unmapped is counted as operating and
    named in `uncategorized`. Dropping it would let the statement tie while hiding a
    real movement, which is the failure this is written to avoid.
    """
    grouped = _by_role(records)
    chart = _chart(grouped)
    cash_accounts = {a for a, d in chart.items() if d.get("report_mapping") == "cash"}

    entries: dict[tuple, list[dict]] = defaultdict(list)
    for record in grouped["ledger"]:
        payload = record["payload"]
        entries[(record["record_key"].split("\x1f")[0], payload.get("date", ""))].append(payload)

    activities: dict[str, int] = defaultdict(int)
    uncategorized: list[str] = []
    for (entry_id, _), lines in sorted(entries.items()):
        cash_lines = [x for x in lines if x.get("account") in cash_accounts]
        if not cash_lines:
            continue
        delta = sum(x.get("debit_cents", 0) - x.get("credit_cents", 0) for x in cash_lines)
        if not delta:
            continue
        others = [x for x in lines if x.get("account") not in cash_accounts]
        mappings = {chart.get(x.get("account", ""), {}).get("report_mapping", "")
                    for x in others}
        mappings.discard("")
        if not mappings:
            uncategorized.append(entry_id)
            activities["operating"] += delta
            continue
        # One entry, one activity: split by mapping would apportion a single movement
        # across categories on a rule nobody supplied.
        activities[_activity(sorted(mappings)[0])] += delta

    opening = sum(r["payload"].get("debit_cents", 0) - r["payload"].get("credit_cents", 0)
                  for r in grouped["opening"] if r["payload"].get("account") in cash_accounts)
    net = sum(activities.values())
    closing_per_accounts = sum(
        row["closing_cents"] for account, row in balances(records)["accounts"].items()
        if account in cash_accounts)

    return {
        "opening_cash_cents": opening,
        "operating_cents": activities.get("operating", 0),
        "investing_cents": activities.get("investing", 0),
        "financing_cents": activities.get("financing", 0),
        "net_movement_cents": net,
        "closing_cash_cents": opening + net,
        # The tie that matters: walking the entries must land on the same figure the
        # balance sheet carries. A difference means an entry was missed.
        "closing_per_balance_sheet_cents": closing_per_accounts,
        "difference_cents": (opening + net) - closing_per_accounts,
        "ties": (opening + net) == closing_per_accounts,
        "uncategorized_entries": uncategorized,
        "cash_accounts": sorted(cash_accounts),
        "note": "Each entry is assigned to one activity from what its non-cash side was "
                "posted against. Entries whose counterpart is unmapped are counted as "
                "operating and named, never dropped.",
    }


def statements(records: list[dict], config: dict | None = None) -> dict:
    """All three, plus the checks that say whether they can be relied on.

    The checks travel with the statements rather than beside them: a balance sheet whose
    tie failed is not a balance sheet, and separating the figure from its verdict is how
    one gets quoted without the other.
    """
    trial = trial_balance(records)
    income = income_statement(records)
    position = balance_sheet(records)
    cash = cash_flow(records)
    unknown = balances(records)["unknown_accounts"]

    problems = []
    if not trial["balances"]:
        problems.append("The trial balance does not balance; every figure below inherits "
                        "that difference.")
    if not position["balances"]:
        problems.append("Assets do not equal liabilities plus equity and the period result.")
    if not cash["ties"]:
        problems.append("Cash derived from the entries does not agree with the balance "
                        "sheet cash line.")
    if unknown:
        problems.append("Entries reference accounts that are not in the chart: "
                        + ", ".join(unknown[:5]))
    if cash["uncategorized_entries"]:
        problems.append(f"{len(cash['uncategorized_entries'])} cash entry/entries could "
                        "not be categorized and are counted as operating.")

    return {
        "trial_balance": trial,
        "income_statement": income,
        "balance_sheet": position,
        "cash_flow": cash,
        "reliable": not problems,
        "problems": problems,
        "note": "Management statements over supplied records. Not a statutory package: "
                "no consolidation, deferred tax, disclosure notes or assurance that the "
                "population is complete.",
    }
