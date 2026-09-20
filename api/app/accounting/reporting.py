"""Management and board reporting, assembled from figures that already tie.

C5 writes prose and never numbers. This module is what makes that enforceable rather than
aspirational: it returns the report as sections, each with the figures already computed and
an `intent` saying what prose belongs there. The agent fills the prose slots. It is never
handed an opportunity to author a figure, because there is no slot for one.

## Every figure names where it came from

Each one carries `from`, the module that computed it. A board pack whose numbers cannot be
traced back to the statements is a board pack that will eventually disagree with them, and
by then nobody remembers which was right.

## A report over figures that do not tie

It is still assembled, and `presentable` is false with the reason attached. Refusing to
build it would leave the person with nothing to look at while the problem is diagnosed;
building it silently would put an unreconciled figure in front of a board. Saying so is
the only honest third option.
"""

from __future__ import annotations

from . import close, planning, statements, variance


def _figure(label: str, cents: int | None, source: str, note: str = "") -> dict:
    return {"label": label, "amount_cents": cents, "from": source, "note": note}


def management_report(records: list[dict], config: dict | None = None) -> dict:
    """The period's numbers, arranged for a reader, with prose left to be written.

    Nothing here is new arithmetic. Every figure is lifted from the module that already
    computed and checked it, which is why a board pack and the statements cannot drift
    apart into two different accounts of the same month.
    """
    config = config or {}
    figures = statements.statements(records, config)
    income = figures["income_statement"]
    sheet = figures["balance_sheet"]
    cash = figures["cash_flow"]
    checklist = close.checklist(records, config)
    against_budget = variance.explain(records, config, plan="budgets", limit=5)
    categories = planning.roll_up(records, config)

    problems = list(figures["problems"])
    if not checklist["ready"]:
        problems.append("The period is not closed: " + ", ".join(checklist["blocked_by"]) + ".")

    sections = [
        {
            "id": "result",
            "title": "The period's result",
            "figures": [
                _figure("Revenue", income["total_revenue_cents"], "statements.income_statement"),
                _figure("Expenses", income["total_expense_cents"], "statements.income_statement"),
                _figure("Result", income["net_income_cents"], "statements.income_statement",
                        "Movement for the period, not a year-to-date position."),
            ],
            "intent": "What the result was and what moved it. Name the drivers below "
                      "rather than restating the figures, which the reader can already see.",
        },
        {
            "id": "against-plan",
            "title": "Against the approved budget",
            "figures": [
                _figure("Expenses planned", against_budget["comparison"]["totals"]["expense"]["planned_cents"],
                        "variance.budget_vs_actual"),
                _figure("Expenses actual", against_budget["comparison"]["totals"]["expense"]["actual_cents"],
                        "variance.budget_vs_actual"),
                _figure("Variance", against_budget["comparison"]["totals"]["expense"]["variance_cents"],
                        "variance.budget_vs_actual",
                        "Positive is an overspend. Expense and revenue variances are not added together."),
            ],
            "drivers": against_budget["explained"],
            "unplanned": against_budget["comparison"]["unplanned"],
            "intent": "Explain the largest variances using the drivers supplied, each of "
                      "which names the transactions behind it. Do not introduce a driver "
                      "that is not in the list.",
        },
        {
            "id": "position",
            "title": "Position and cash",
            "figures": [
                _figure("Assets", sheet["total_assets_cents"], "statements.balance_sheet"),
                _figure("Liabilities", sheet["total_liabilities_cents"], "statements.balance_sheet"),
                _figure("Equity", sheet["total_equity_cents"], "statements.balance_sheet"),
                _figure("Opening cash", cash["opening_cash_cents"], "statements.cash_flow"),
                _figure("Closing cash", cash["closing_cash_cents"], "statements.cash_flow"),
            ],
            "intent": "What changed in the position and why cash moved as it did.",
        },
        {
            "id": "categories",
            "title": "Where the money went",
            "categories": categories["categories"],
            "headcount": categories["headcount"],
            "intent": "The shape of the cost base. Say which categories are unbudgeted "
                      "where the data marks them so.",
        },
        {
            "id": "close",
            "title": "Close status",
            "checklist": checklist["items"],
            "ready": checklist["ready"],
            "intent": "Whether the period is closed and what is outstanding. State what "
                      "the close does not establish.",
        },
    ]

    return {
        "period": checklist["period"],
        "sections": sections,
        "presentable": not problems,
        "problems": problems,
        "ties": {
            "trial_balance": figures["trial_balance"]["balances"],
            "balance_sheet": sheet["balances"],
            "cash_flow": cash["ties"],
        },
        "note": "Every figure here was computed by the module named beside it and is "
                "reproduced, not recalculated. Prose is written into the section intents; "
                "no figure in this report was authored by a model."
                if not problems else
                "This report was assembled over figures that do not tie or a period that "
                "is not closed. The reasons are listed under 'problems'. It is here to be "
                "worked from, not to be presented.",
    }
