"""Sampling and tracing: the work of checking whether the records say what they claim.

D1 does not re-run the other agents' logic and agree with it. It picks transactions and
follows each one from the document that started it to the ledger entry that ended it, and
reports where the chain stops.

## A sample is reported with its method, always

`select()` returns what it chose *and* how, because a sample without its method is an
anecdote. Everything at or above materiality is taken in full — those are not sampled at
all — and the rest is drawn with a seeded generator so the same population and the same
seed give the same sample. A reader who wants to check the selection can reproduce it.

## What a trace establishes, and what it does not

A complete trace says every step the records should contain is present and refers to the
step before it. It does not say the transaction was genuine, that the goods arrived, or
that the price was right. `trace()` returns `establishes` and `does_not_establish` side by
side so that distinction survives into whatever reads it.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

#: The chain a purchase is supposed to leave behind, in the order it happens.
PURCHASE_TRAIL = (
    ("purchase_orders", "The order that committed the company to the spend"),
    ("goods_receipts", "The record that what was ordered arrived"),
    ("vendor_invoices", "The vendor's request to be paid"),
    ("approvals", "A person with authority allowing the payment"),
    ("payments", "The payment the company made"),
    ("bank_transactions", "The bank's own record that the money left"),
    ("ledger", "The journal entries that put it in the books"),
)


def _by_role(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["role"]].append(record)
    return grouped


def _draw(key: str, seed: str) -> int:
    """A stable pseudo-random ordinal for one record.

    Hashing the key rather than shuffling a list means the selection does not depend on
    the order records happen to arrive in, so re-uploading the same period in a different
    order selects the same sample.
    """
    digest = hashlib.sha256((seed + "\x1f" + key).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def select(records: list[dict], config: dict | None = None, *, role: str = "vendor_invoices",
           size: int = 10, seed: str = "") -> dict:
    """A reproducible sample of one role, with everything material taken in full.

    Amounts at or above the workspace's materiality are not sampled: a test that might
    miss the largest item in the population is not a test of the largest item. They are
    reported as their own stratum so nobody reads the sample as uniform.
    """
    config = config or {}
    grouped = _by_role(records)
    population = grouped.get(role, [])
    materiality = int((config.get("settings") or {}).get("materiality_cents") or 0)
    seed = seed or str(config.get("id") or config.get("start") or "sherlock")

    def amount(record: dict) -> int:
        payload = record["payload"]
        for field in ("amount_cents", "net_cents", "gross_cents", "debit_cents"):
            if payload.get(field):
                return abs(payload[field])
        return 0

    material = [r for r in population if materiality and amount(r) >= materiality]
    remainder = [r for r in population if r not in material]
    drawn = sorted(remainder, key=lambda r: _draw(r["record_key"], seed))[:max(0, size)]

    def describe(record: dict, stratum: str) -> dict:
        return {"record_key": record["record_key"], "role": role, "stratum": stratum,
                "amount_cents": amount(record),
                "evidence": [{"role": role, "record_key": record["record_key"],
                              "source_id": record["source_id"], "line": record["locator"]}]}

    selected = ([describe(r, "material") for r in material]
                + [describe(r, "sampled") for r in drawn])
    covered = sum(item["amount_cents"] for item in selected)
    total = sum(amount(r) for r in population)

    return {
        "role": role,
        "population": len(population),
        "population_cents": total,
        "selected": selected,
        "selected_cents": covered,
        # An integer percentage, floored. Coverage rounded up reads as more assurance
        # than the sample supports.
        "coverage_pct": 0 if not total else covered * 100 // total,
        "method": {
            "material_threshold_cents": materiality,
            "material_taken_in_full": len(material),
            "sampled": len(drawn),
            "seed": seed,
            "how": "Everything at or above materiality is taken in full. The remainder is "
                   "ordered by a hash of its record key and the seed, so the same "
                   "population and seed give the same sample however the records were "
                   "uploaded.",
        },
        "note": "A sample. Findings apply to the items selected and say nothing about the "
                "items that were not."
                if materiality else
                "No materiality was supplied, so nothing was taken in full and the whole "
                "population was sampled uniformly. The largest item may not be in it.",
    }


def trace(records: list[dict], invoice_key: str) -> dict:
    """Follow one purchase from the order that started it to the entries that recorded it.

    Each step says whether it is present and what connects it to the step before. A step
    that is missing is named as missing rather than skipped, because a trail with a hole
    in it and a trail with one fewer step look identical once the hole is omitted.
    """
    grouped = _by_role(records)
    invoice = next((r for r in grouped["vendor_invoices"]
                    if r["record_key"] == invoice_key), None)
    if invoice is None:
        return {"invoice_key": invoice_key, "found": False, "steps": [], "complete": False,
                "note": "No such vendor invoice in the committed population."}

    payload = invoice["payload"]
    po_id = payload.get("po_id", "")
    number = payload.get("invoice_number") or ""
    names = {n for n in (number, payload.get("record_id"), invoice_key) if n}
    event_ref = payload.get("event_ref") or ""

    # Resolved first, because the bank line does not name the invoice. It quotes the
    # payment's own reference, so the honest link is invoice → payment → bank rather than
    # a search for the invoice number in a field that never holds it.
    payments = [r for r in grouped.get("payments", [])
                if number and r["payload"].get("invoice_number") == number]
    payment_references = {str(r["payload"].get("reference", "")) for r in payments
                          if r["payload"].get("reference")}

    def hits(role: str) -> list[dict]:
        found = []
        for record in grouped.get(role, []):
            body = record["payload"]
            if role == "vendor_invoices":
                if record["record_key"] == invoice_key:
                    found.append(record)
            elif role in ("purchase_orders", "goods_receipts"):
                if po_id and body.get("po_id") == po_id:
                    found.append(record)
            elif role == "approvals":
                if body.get("target_id") in names:
                    found.append(record)
            elif role == "payments":
                found = list(payments)
                break
            elif role == "bank_transactions":
                reference = str(body.get("bank_reference") or body.get("reference") or "")
                if reference and reference in payment_references:
                    found.append(record)
            elif role == "ledger":
                if event_ref and body.get("event_ref") == event_ref:
                    found.append(record)
        return found

    steps, missing = [], []
    for role, description in PURCHASE_TRAIL:
        found = hits(role)
        steps.append({
            "role": role, "description": description, "present": bool(found),
            "records": [r["record_key"] for r in found],
            "evidence": [{"role": role, "record_key": r["record_key"],
                          "source_id": r["source_id"], "line": r["locator"]} for r in found],
            "linked_by": {"purchase_orders": "the order reference on the invoice",
                          "goods_receipts": "the order reference on the invoice",
                          "vendor_invoices": "the invoice itself",
                          "approvals": "the invoice number the approval names",
                          "payments": "the invoice number the payment names",
                          "bank_transactions": "the payment's own reference, which the "
                                               "bank line quotes back",
                          "ledger": "the economic event the invoice carries"}[role],
        })
        if not found:
            missing.append(role)

    return {
        "invoice_key": invoice_key, "found": True, "steps": steps,
        "complete": not missing, "missing": missing,
        "establishes": "Every step named above exists in the committed records and refers "
                       "to the step before it by a recorded reference.",
        "does_not_establish": "That the transaction was genuine, that what was ordered "
                              "arrived, that the price was right, or that the population "
                              "these records came from is complete.",
        "note": "A complete trail is evidence that the records are internally consistent. "
                "It is not evidence that they are true."
                if not missing else
                "The trail stops. A missing step is not the same as a step that does not "
                "apply, and neither is established by the records alone.",
    }
