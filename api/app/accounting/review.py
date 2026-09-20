"""Bounded management checks, not statutory accounting or fraud determinations."""
from collections import defaultdict
from hashlib import sha256

from .collections import collection_checks
from .payroll import calculations as payroll_calculations


def checks(records, config):
    by_role = defaultdict(list)
    for row in records:
        by_role[row["role"]].append(row)
    result = []

    def add(key, title, role, status, explanation, rows=(), amount=None, action="Review the original support with the finance team."):
        """Record one finding.

        `key` becomes the finding id, and a reviewer attaches follow-up to it by
        (finding_id, snapshot_id). So an id must name WHAT the finding is, never
        which rows are currently in it: derive it from the grouping key, or use a
        fixed id and let evidence carry membership. An id that moves when a group
        gains a row orphans the reviewer's note, re-presents the finding as new,
        and is invisible to the changes diff, which keys on id alone.

        If one ever has to move anyway, do it while no workspace exists — the
        migration is free at zero rows and costs reviewer history at any other
        time.
        """
        evidence = sorted({(r["source_id"], r["locator"]) for r in rows})
        result.append(dict(id=key, title=title, role=role, status=status, explanation=explanation,
                           amount_cents=amount, action=action, origin="deterministic", review="Rules-based check; not an Auditor verdict",
                           evidence=[dict(source_id=s, line=n) for s, n in evidence]))

    invoices = by_role["invoice"]
    if not invoices:
        add("ap-inventory", "Invoice records missing", "ap", "gap", "No invoice population supplied. AP has not been cleared.", action="Upload an invoice register and supporting purchase/receipt records.")
    else:
        groups = defaultdict(list)
        for row in invoices:
            p = row["payload"]
            # Preserve punctuation: aggressive normalization can conflate distinct invoices.
            groups[(p["vendor_id"].strip().casefold(), p["invoice_number"].strip().casefold(), p["amount_cents"], p["currency"])].append(row)
        duplicates = [(gkey, rows) for gkey, rows in groups.items() if len(rows) > 1]
        for gkey, rows in duplicates:
            # Hash the duplicate's identity, not its current members. This
            # previously hashed the group's record_keys, so a third matching
            # invoice retired one id and minted another. See add() above.
            vendor, invoice_number, amount_cents, currency = gkey
            key = sha256(f"{vendor}|{invoice_number}|{amount_cents}|{currency}".encode()).hexdigest()[:12]
            add("ap-duplicate-" + key, "Possible duplicate invoice", "ap", "attention",
                "Same vendor, invoice number, currency and amount appear on multiple source records. This does not establish duplicate payment.",
                rows, (len(rows) - 1) * rows[0]["payload"]["amount_cents"], "Compare originals, payment status and legitimate split/reversal explanations before proposing a correction.")
        if not duplicates:
            add("ap-duplicates", "Exact-key duplicate check", "ap", "pass", "No repeated vendor/invoice/amount/currency key in the supplied register. Fuzzy duplicates and payment execution were not tested.", invoices)
        missing = [r for r in invoices if not r["payload"].get("po_id") or not r["payload"].get("receipt_id")]
        add("ap-matching", "Purchase and receipt support", "ap", "gap",
            f"{len(missing)} invoice records lack a purchase-order or receipt reference. References alone cannot establish a three-way match; underlying PO/receipt quantities and amounts are not structured inputs yet.",
            missing or invoices, action="Supply purchase orders and receiving records; have a reviewer match quantities, rates and totals.")

    chart = {r["payload"]["account"]: r for r in by_role["chart"]}
    if not chart or not by_role["opening"] or not by_role["ledger"]:
        add("management-inputs", "Management balances need records", "py", "gap",
            "Supply a chart of accounts, opening trial balance and ledger.")
    else:
        balances = defaultdict(int)
        for row in by_role["opening"] + by_role["ledger"]:
            p = row["payload"]
            balances[p["account"]] += p["debit_cents"] - p["credit_cents"]
        for account, definition in sorted(chart.items()):
            rows = [r for r in by_role["opening"] + by_role["ledger"] if r["payload"]["account"] == account]
            add("management-account-" + account, f"Closing balance · {account} · {definition['payload']['name']}",
                "py", "pass", "Opening balance plus supplied period activity. Positive is debit; negative is credit. Not a completeness or audit conclusion.",
                [definition] + rows, balances[account], "Review the supplied account balance against your books.")
        difference = sum(balances.values())
        add("management-trial-balance", "Closing trial balance", "py", "attention" if difference else "pass",
            "Sum of opening balances and period debits less credits. Zero means supplied balances tie; omitted balanced transactions cannot be detected.",
            by_role["opening"] + by_role["ledger"], difference)
        activity = [r for r in by_role["ledger"] if chart.get(r["payload"]["account"], {}).get("payload", {}).get("type") in {"revenue", "expense"}]
        surplus = sum(r["payload"]["credit_cents"] - r["payload"]["debit_cents"] for r in activity)
        add("management-period-result", "Period revenue less expenses", "py", "pass",
            "Net supplied revenue and expense activity; positive is surplus, negative is deficit. Excludes opening balances. This is a management summary, not statutory financial statements.",
            activity + by_role["chart"], surplus, "Confirm period coverage and account classifications before reporting.")
    budgets = defaultdict(list)
    for row in by_role["budget"]:
        p = row["payload"]
        budgets[(p["account"], p.get("fund", ""), p.get("department", ""), p.get("school", ""))].append(row)
    if not budgets or not by_role["ledger"] or not chart:
        add("budget-inputs", "Budget comparison needs records", "py", "gap", "Supply the chart, approved period budget and general ledger. No variance is inferred from missing inputs.")
    for dims, rows in budgets.items():
        account = dims[0]
        key = "budget-" + sha256(str(dims).encode()).hexdigest()[:12]
        if account not in chart or chart[account]["payload"]["type"] != "expense":
            add(key, "Budget basis requires review", "py", "gap", "This check only compares expense accounts on the configured accrual profile.", rows)
            continue
        if not by_role["ledger"]:
            continue
        if len(rows) != 1:
            add(key, "Ambiguous budget versions", "py", "gap", "Multiple budget lines share the same account and dimensions. Select a single approved period budget; versions are not summed.", rows)
            continue
        lines = [r for r in by_role["ledger"] if tuple(r["payload"].get(k, "") for k in ("account", "fund", "department", "school")) == dims]
        actual = sum(r["payload"]["debit_cents"] - r["payload"]["credit_cents"] for r in lines)
        approved = rows[0]["payload"]["amount_cents"]
        variance = actual - approved
        add(key, f"Expense budget variance · {account}", "py", "attention" if variance > 0 else "pass",
            "Net expense activity less the supplied approved period budget, matched on account/fund/department/school. Assumes this budget covers the workspace period; encumbrances and forecast are excluded.",
            rows + lines + [chart[account]], variance, "Confirm budget period and approval, then explain the variance; overspend alone is not wrongdoing.")

    if not by_role["payroll"]:
        add("payroll-inputs", "Payroll records missing", "py", "gap", "No payroll tie-out or grant allocation checks could be performed.")
    for calc in payroll_calculations(records, bool(by_role["service"])):
        if calc.id in {"payroll-total-expense", "payroll-award-allocation"}:
            continue
        role = "gr" if "award" in calc.id or "service" in calc.id else "py"
        status = "attention" if calc.category != "none" else "pass"
        amount = calc.amount_cents
        evidence_rows = [r for r in records if r["source_id"] in calc.source_ids]
        if calc.id == "payroll-unsupported-by-service-evidence":
            status = "gap"  # Presence of a memo is never evidence of a supported allocation.
            evidence_rows += by_role["service"] + by_role["policy"]
            if by_role["service"]:
                amount = None  # A zero presence-check is not a zero-exposure conclusion.
        title = {"payroll-award-ceiling-excess": "Award ceiling check · payroll charges",
                 "payroll-outside-award-window": "Award service-period check",
                 "payroll-unknown-award": "Award reference check",
                 "payroll-unsupported-by-service-evidence": "Service support for payroll allocation",
                 "payroll-gross-to-net": "Payroll gross-to-net reconciliation",
                 "payroll-ledger-tie": "Payroll-to-ledger reconciliation"}.get(calc.id, calc.description)
        add(calc.id, title, role, status, calc.basis, evidence_rows, amount,
            "Obtain and independently assess service evidence; do not infer an approved reclassification or cash recovery.")
    if not by_role["grants"]:
        add("grant-inputs", "Grant register missing", "gr", "gap", "Award eligibility and ceilings cannot be confirmed without award definitions.")
    add("grant-eligibility", "Purpose and service eligibility", "gr", "gap",
        "Period and ceiling checks cover supplied payroll allocations only. Award purpose, invoice-funded charges, service allocation, amendments and full-population completeness require independent review.", by_role["policy"])
    collection_checks(by_role, config, add)
    return result
