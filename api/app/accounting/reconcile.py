"""Bank reconciliation and processor payout decomposition, in exact integer cents.

Agreeing the bank to the ledger is the most mechanical job in finance and the one where
a model is least welcome: it is set arithmetic over references, and every difference has
to be reported exactly rather than explained away. A3 reads what this produces and judges
only the residue — the cases references cannot settle.

Two things this deliberately will not do:

- **Guess a match from amount and date.** Two payments of the same amount in the same
  week are not evidence of anything. Matching is by recorded reference; what is left over
  is reported as unmatched, which is the honest answer and the one that sends a person to
  look.
- **Net anything.** An unmatched receipt and an unmatched payment of the same size do not
  cancel. They are two open items, and describing them as one closed one would hide both.

A difference here is *unreconciled*, never a loss, a saving or a recovery.
"""

from __future__ import annotations

from collections import defaultdict


def _by_role(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["role"]].append(record)
    return grouped


def _reference(payload: dict) -> str:
    """The reference a record was banked under, however the source spelled it."""
    for field in ("bank_reference", "reference", "payment_reference"):
        value = (payload.get(field) or "").strip()
        if value:
            return value
    return ""


def _cite(record: dict, note: str) -> dict:
    return {"role": record["role"], "record_key": record["record_key"],
            "source_id": record["source_id"], "line": record["locator"], "note": note}


def decompose_payout(records: list[dict], payout_key: str = "") -> list[dict]:
    """Check that each processor payout's parts add up to what arrived.

    A payout lands net of fees, refunds and chargebacks. Without that breakdown the cash
    that reaches the bank can never be agreed to gross sales, and the difference looks
    like missing revenue. Intake already refuses a payout whose parts do not sum, so this
    reports the decomposition rather than re-testing it — what it adds is the split a
    reconciliation needs, and the gross figure that revenue ties to.
    """
    out = []
    for record in _by_role(records)["processor_payouts"]:
        if payout_key and record["record_key"] != payout_key:
            continue
        payload = record["payload"]
        gross = payload.get("gross_cents", 0)
        deductions = {
            "fees": payload.get("fees_cents", 0),
            "refunds": payload.get("refunds_cents", 0),
            "chargebacks": payload.get("chargebacks_cents", 0),
        }
        out.append({
            "payout_key": record["record_key"],
            "processor": payload.get("processor", ""),
            "payout_date": payload.get("payout_date", ""),
            "reference": _reference(payload),
            "gross_cents": gross,
            "deductions": deductions,
            "net_cents": payload.get("net_cents", 0),
            "citations": [_cite(record, "the payout advice")],
            "note": "Gross is what customers were charged; net is what reached the bank. "
                    "Revenue ties to gross, and the difference is the processor's "
                    "deductions, not a shortfall.",
        })
    return out


def reconcile_bank(records: list[dict], config: dict | None = None) -> dict:
    """Agree bank activity to what the books say moved.

    Cash out is matched to payments, cash in to remittances and processor payouts, by
    reference. Everything unmatched on either side is reported, with its amount, because
    an unexplained bank line is the finding.
    """
    grouped = _by_role(records)
    bank = grouped["bank_transactions"]

    # Book side, indexed by the reference each record says it moved under.
    book: dict[str, list[dict]] = defaultdict(list)
    for role in ("payments", "remittances", "processor_payouts"):
        for record in grouped[role]:
            reference = _reference(record["payload"])
            if reference:
                book[reference].append(record)

    matched, unmatched_bank = [], []
    seen_references: set[str] = set()

    for line in bank:
        payload = line["payload"]
        reference = _reference(payload)
        amount = payload.get("amount_cents", 0)
        candidates = book.get(reference, []) if reference else []
        if not candidates:
            unmatched_bank.append({
                "bank_key": line["record_key"],
                "settlement_date": payload.get("settlement_date", ""),
                "direction": payload.get("direction", ""),
                "amount_cents": amount,
                "description": payload.get("description", ""),
                "reference": reference,
                "citations": [_cite(line, "bank line with nothing recorded against it")],
                "reason": "No payment, remittance or payout is recorded under this "
                          "reference." if reference else
                          "The bank line carries no reference, so it cannot be traced.",
            })
            continue

        seen_references.add(reference)
        # A payout is compared on its net figure: that is what actually arrives.
        expected = sum(
            candidate["payload"].get("net_cents" if candidate["role"] == "processor_payouts"
                                     else "amount_cents", 0)
            for candidate in candidates)
        matched.append({
            "bank_key": line["record_key"],
            "reference": reference,
            "direction": payload.get("direction", ""),
            "bank_amount_cents": amount,
            "book_amount_cents": expected,
            "difference_cents": amount - expected,
            "agrees": amount == expected,
            "book_records": [c["record_key"] for c in candidates],
            "roles": sorted({c["role"] for c in candidates}),
            # One bank line covering several book records is ordinary; a batch payment
            # is one debit against many invoices. It is reported as such, not split.
            "one_to_many": len(candidates) > 1,
            "citations": [_cite(line, "bank line")] + [_cite(c, "recorded movement") for c in candidates],
        })

    unmatched_book = []
    for reference, candidates in sorted(book.items()):
        if reference in seen_references:
            continue
        for candidate in candidates:
            payload = candidate["payload"]
            unmatched_book.append({
                "role": candidate["role"],
                "record_key": candidate["record_key"],
                "reference": reference,
                "amount_cents": payload.get(
                    "net_cents" if candidate["role"] == "processor_payouts" else "amount_cents", 0),
                "citations": [_cite(candidate, "recorded as moved, not seen at the bank")],
                "reason": "The books record this movement, but no supplied bank line "
                          "carries its reference.",
            })

    differences = [m for m in matched if not m["agrees"]]
    return {
        "matched": matched,
        "differences": differences,
        "unmatched_bank": unmatched_bank,
        "unmatched_book": unmatched_book,
        "totals": {
            "bank_lines": len(bank),
            "matched": len(matched),
            "differing": len(differences),
            "unmatched_bank": len(unmatched_bank),
            "unmatched_book": len(unmatched_book),
            # Reported separately and never netted: they are different open questions.
            "unmatched_bank_cents": sum(u["amount_cents"] for u in unmatched_bank),
            "unmatched_book_cents": sum(u["amount_cents"] for u in unmatched_book),
        },
        "payouts": decompose_payout(records),
        "note": "Matched by recorded reference only; nothing is inferred from amount and "
                "date. Unmatched items on the two sides are separate open questions and "
                "are never netted against each other. A difference is unreconciled, not "
                "a loss.",
    }
