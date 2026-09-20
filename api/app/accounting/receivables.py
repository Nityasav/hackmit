"""Receivables aging and conservative cash application, in integer cents.

Only a unique customer/currency/invoice reference permits allocation. Multi-invoice
receipts remain unapplied: this schema has no per-invoice allocation amounts. Neither
matching amounts nor FIFO establishes which obligation a customer paid.
"""
from collections import defaultdict
from datetime import date
import re


def _cite(row):
    return {"role": row["role"], "record_key": row["record_key"],
            "source_id": row["source_id"], "line": row["locator"]}


def match_remittances(records, config, as_of=None):
    cutoff = date.fromisoformat(as_of or config["end"])
    if cutoff > date.fromisoformat(config["end"]):
        raise ValueError("As-of date cannot exceed the workspace period")
    currency = config["currency"]
    invoices = [r for r in records if r["role"] == "customer_invoices"
                and date.fromisoformat(r["payload"]["invoice_date"]) <= cutoff]
    receipts = sorted((r for r in records if r["role"] == "remittances"
                       and date.fromisoformat(r["payload"]["received_date"]) <= cutoff),
                      key=lambda r: (r["payload"]["received_date"], r["record_key"], r["source_id"]))
    by_reference = defaultdict(list)
    for index, row in enumerate(invoices):
        p = row["payload"]
        by_reference[(p["customer_id"], p.get("currency", currency), p["invoice_number"])].append(index)
    # A repeated receipt reference is not safe to apply twice, even with distinct IDs.
    receipt_refs = defaultdict(list)
    for row in receipts:
        p = row["payload"]
        receipt_refs[(p["customer_id"], p.get("currency", currency), p["reference"])].append(row)
    balances = [r["payload"]["amount_cents"] for r in invoices]
    applications, unapplied, exceptions = [], [], []
    for row in receipts:
        p = row["payload"]
        refs = [s.strip() for s in re.split(r"[,;|]", p.get("invoice_refs", "")) if s.strip()]
        key = (p["customer_id"], p.get("currency", currency), p["reference"])
        candidates = by_reference.get((key[0], key[1], refs[0]), []) if len(refs) == 1 else []
        evidence = [_cite(row)] + [_cite(invoices[i]) for i in candidates]
        if len(receipt_refs[key]) != 1 or len(refs) != 1 or len(candidates) != 1:
            code = "ambiguous_remittance" if refs or len(receipt_refs[key]) != 1 else "unreferenced_remittance"
            unapplied.append({"record_key": row["record_key"], "amount_cents": p["amount_cents"],
                              "reason": code, "citations": evidence})
            exceptions.append({"code": code, "detail": "Receipt cannot be uniquely allocated from its recorded references."})
            continue
        i = candidates[0]
        invoice = invoices[i]
        if p["received_date"] < invoice["payload"]["invoice_date"]:
            unapplied.append({"record_key": row["record_key"], "amount_cents": p["amount_cents"],
                              "reason": "receipt_before_invoice", "citations": evidence})
            exceptions.append({"code": "ambiguous_remittance", "detail": "Receipt predates the referenced invoice; review as a possible advance."})
            continue
        applied = min(balances[i], p["amount_cents"])
        balances[i] -= applied
        applications.append({"remittance_key": row["record_key"], "invoice_key": invoice["record_key"],
                             "applied_cents": applied, "citations": evidence})
        excess = p["amount_cents"] - applied
        if excess:
            unapplied.append({"record_key": row["record_key"], "amount_cents": excess,
                              "reason": "overpayment", "citations": evidence})
            exceptions.append({"code": "overpayment", "detail": "Receipt exceeds the remaining balance; excess remains unapplied."})
    invoice_rows = []
    for row, outstanding in zip(invoices, balances):
        original = row["payload"]["amount_cents"]
        if 0 < outstanding < original:
            exceptions.append({"code": "partial_payment", "detail": "A referenced invoice remains partially unpaid."})
        invoice_rows.append({"invoice_key": row["record_key"], "customer_id": row["payload"]["customer_id"],
                             "due_date": row["payload"]["due_date"], "amount_cents": original,
                             "outstanding_cents": outstanding, "citations": [_cite(row)]})
    return {"as_of": cutoff.isoformat(), "currency": currency, "applications": applications,
            "unapplied": unapplied, "invoices": invoice_rows, "exceptions": exceptions,
            "received_cents": sum(r["payload"]["amount_cents"] for r in receipts),
            "applied_cents": sum(a["applied_cents"] for a in applications),
            "unapplied_cents": sum(a["amount_cents"] for a in unapplied),
            "note": "Supplied invoices and receipts only. Proposed allocation, not a posting. Ambiguous receipts remain unapplied."}


def age_receivables(records, config, as_of=None):
    result = match_remittances(records, config, as_of)
    cutoff = date.fromisoformat(result["as_of"])
    buckets = dict.fromkeys(("current", "1-30", "31-60", "61-90", "over-90"), 0)
    for invoice in result["invoices"]:
        days = (cutoff - date.fromisoformat(invoice["due_date"])).days
        bucket = "current" if days <= 0 else "1-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "over-90"
        invoice.update(days_overdue=max(0, days), bucket=bucket)
        buckets[bucket] += invoice["outstanding_cents"]
    return {**result, "buckets_cents": buckets, "outstanding_cents": sum(buckets.values())}
