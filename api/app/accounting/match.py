"""Three-way matching, duplicate detection and policy tests, in exact integer cents.

This is the deterministic half of Accounts Payable. It decides everything that can be
decided by arithmetic and set logic: whether an invoice has an order and a receipt
behind it, whether the three amounts agree, whether the same obligation appears twice,
and whether the approval on it satisfies the policy. An agent reads the result and
judges what is left — it never recomputes any of this, and it never produces a number.

## Confidence is a rubric, not an opinion

`confidence` is a weighted score over named features, with the weights written below and
every feature recorded on the result. A person can re-derive the score by hand, and a
reviewer can disagree with a *weight* rather than with a model's mood. This is the whole
reason the number is defensible: "99.3%" from a language model is not a measurement, and
a score nobody can reconstruct is worse than no score at all.

The weights are a starting position, not a calibrated instrument. They have not been
fitted against outcomes, and the docstring says so because the screen will not.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from hashlib import sha256

#: Feature weights, summing to 100. Each is a thing a person would actually check.
WEIGHTS: dict[str, int] = {
    "purchase_order_found": 25,
    "goods_receipt_found": 20,
    "amount_agrees": 30,
    "vendor_agrees": 10,
    "dates_consistent": 5,
    "approval_present": 10,
}
assert sum(WEIGHTS.values()) == 100, "confidence weights must sum to 100"


@dataclass
class MatchResult:
    """What matching established about one invoice, and how certain that is."""

    invoice_key: str
    invoice_number: str
    vendor_id: str
    amount_cents: int
    po_id: str = ""
    receipt_id: str = ""
    #: feature name -> whether it held. The inputs to `confidence`, kept so the score
    #: can be reconstructed rather than trusted.
    features: dict[str, bool] = field(default_factory=dict)
    exceptions: list[tuple[str, str]] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)

    @property
    def confidence(self) -> int:
        """0-100, computed from `features` alone."""
        return sum(weight for name, weight in WEIGHTS.items() if self.features.get(name))

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(code for code, _ in self.exceptions)

    def as_dict(self) -> dict:
        return {
            "invoice_key": self.invoice_key, "invoice_number": self.invoice_number,
            "vendor_id": self.vendor_id, "amount_cents": self.amount_cents,
            "po_id": self.po_id, "receipt_id": self.receipt_id,
            "confidence": self.confidence, "features": dict(self.features),
            "weights": dict(WEIGHTS),
            "exceptions": [{"code": c, "detail": d} for c, d in self.exceptions],
            "citations": list(self.citations),
        }


def _by_role(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["role"]].append(record)
    return grouped


def _cite(record: dict, note: str) -> dict:
    return {"role": record["role"], "record_key": record["record_key"],
            "source_id": record["source_id"], "line": record["locator"], "note": note}


def three_way(records: list[dict], invoice_key: str, config: dict | None = None) -> MatchResult:
    """Match one vendor invoice to its purchase order and goods receipt.

    Matching is by *recorded reference* only. An invoice that names no purchase order is
    unmatched, and this will not go looking for a plausible one on amount and date:
    guessing which order a bill belongs to is exactly the judgment a person is being
    asked to make, and inventing it here would hide the question.
    """
    grouped = _by_role(records)
    invoice = next((r for r in grouped["vendor_invoices"] if r["record_key"] == invoice_key), None)
    if invoice is None:
        raise KeyError(f"No committed vendor invoice with key {invoice_key!r}")

    payload = invoice["payload"]
    result = MatchResult(
        invoice_key=invoice_key,
        invoice_number=payload.get("invoice_number", ""),
        vendor_id=payload.get("vendor_id", ""),
        amount_cents=payload.get("amount_cents", 0),
        po_id=payload.get("po_id", "") or "",
        receipt_id=payload.get("receipt_id", "") or "",
        citations=[_cite(invoice, "the invoice under review")],
    )

    orders = [r for r in grouped["purchase_orders"]
              if result.po_id and r["payload"].get("po_id") == result.po_id]
    receipts = [r for r in grouped["goods_receipts"]
                if result.receipt_id and r["payload"].get("receipt_id") == result.receipt_id]

    result.features["purchase_order_found"] = bool(orders)
    result.features["goods_receipt_found"] = bool(receipts)
    if not orders:
        result.exceptions.append((
            "no_purchase_order",
            "The invoice names no purchase order, or names one that is not in the "
            "committed population. It cannot be three-way matched."))
    if not receipts:
        result.exceptions.append((
            "no_goods_receipt",
            "No goods receipt is recorded against this invoice, so there is no evidence "
            "that what was billed was actually delivered."))

    # Amounts. A multi-line order is summed; the comparison is exact, in cents.
    order_total = sum(r["payload"].get("amount_cents", 0) for r in orders)
    receipt_total = sum(r["payload"].get("amount_cents", 0) for r in receipts)
    result.citations += [_cite(r, "purchase order line") for r in orders]
    result.citations += [_cite(r, "goods receipt line") for r in receipts]

    if orders and receipts:
        agrees = result.amount_cents == order_total == receipt_total
        result.features["amount_agrees"] = agrees
        if not agrees:
            result.exceptions.append((
                "amount_mismatch",
                "The billed amount, the ordered amount and the received amount are not "
                "all equal. The difference is reported exactly and is not apportioned."))
    else:
        result.features["amount_agrees"] = False

    # Vendor identity has to agree between the bill and the order.
    if orders:
        order_vendors = {r["payload"].get("vendor_id") for r in orders}
        agrees = order_vendors == {result.vendor_id}
        result.features["vendor_agrees"] = agrees
        if not agrees:
            result.exceptions.append((
                "vendor_mismatch",
                "The invoice and its purchase order name different vendors."))
    else:
        result.features["vendor_agrees"] = False

    # Order, then delivery, then bill. Out of sequence is a question, not a verdict.
    ordered = min((r["payload"].get("order_date", "") for r in orders), default="")
    received = min((r["payload"].get("received_date", "") for r in receipts), default="")
    billed = payload.get("invoice_date", "")
    sequence = [d for d in (ordered, received, billed) if d]
    result.features["dates_consistent"] = sequence == sorted(sequence)
    if not result.features["dates_consistent"]:
        result.exceptions.append((
            "date_disorder",
            "The order, delivery and invoice dates are not in sequence. This can be a "
            "back-dated order or a data error; it is not by itself a finding."))

    approvals = [r for r in grouped["approvals"]
                 if r["payload"].get("target_id") == invoice_key
                 or r["payload"].get("target_id") == payload.get("record_id")]
    result.features["approval_present"] = bool(approvals)
    result.citations += [_cite(r, "approval") for r in approvals]
    if not approvals:
        result.exceptions.append((
            "missing_approval", "No approval is recorded against this invoice."))

    result.exceptions += _policy_exceptions(result, orders, approvals, config or {})
    return result


def _policy_exceptions(result: MatchResult, orders, approvals, config: dict) -> list[tuple[str, str]]:
    """Policy tests that need the workspace's own thresholds.

    The approval limit is a setting a person answered in Books, not a constant. Where it
    has not been answered the test stands itself down and says so, rather than assuming
    a number and reporting breaches of it.
    """
    found: list[tuple[str, str]] = []
    settings = config.get("settings") or {}
    limit = settings.get("approval_limit_cents")

    if limit is None:
        found.append((
            "approval_limit_unknown",
            "No payment approval limit has been set for this workspace, so whether this "
            "invoice needed a second approver could not be tested."))
    elif result.amount_cents >= int(limit):
        # Not a failure on its own: it is a statement that a person must decide, which
        # is why the spec also lists this amount in `amount_above_cents`.
        found.append((
            "over_approval_limit",
            "The invoice is at or above the approval limit set for this workspace, so a "
            "person decides it regardless of how well it matched."))

    # Whoever raised the order must not be the person who approved paying it.
    requesters = {r["payload"].get("approver", "").strip().casefold() for r in orders}
    requesters.discard("")
    approvers = {r["payload"].get("actor", "").strip().casefold() for r in approvals}
    approvers.discard("")
    if requesters & approvers:
        found.append((
            "self_approved",
            "The same person raised the purchase order and approved the invoice, which "
            "the segregation-of-duties control does not permit."))
    return found


def duplicate_key(vendor_id: str, invoice_number: str, amount_cents: int, currency: str) -> str:
    """The identity of a *duplicate*, not of the rows currently in one.

    Hashing the group's members meant a third matching invoice retired one finding id
    and minted another, orphaning any note a reviewer had attached to it. The key is the
    thing being claimed, so it is stable however many rows share it.
    """
    basis = f"{vendor_id.strip().casefold()}|{invoice_number.strip().casefold()}|{amount_cents}|{currency}"
    return sha256(basis.encode()).hexdigest()[:12]


def find_duplicates(records: list[dict], invoice_key: str = "") -> list[dict]:
    """Invoices sharing vendor, number, amount and currency exactly.

    An exact-key repeat is a *candidate*, never a confirmed duplicate payment: the same
    obligation can legitimately appear twice across two source systems, and two separate
    deliveries can carry one number. Nothing here tests whether either was paid.

    Punctuation is preserved and only case and surrounding space are normalized, because
    aggressive normalization conflates invoices that are genuinely distinct.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for record in records:
        if record["role"] != "vendor_invoices":
            continue
        payload = record["payload"]
        groups[(
            payload.get("vendor_id", "").strip().casefold(),
            payload.get("invoice_number", "").strip().casefold(),
            payload.get("amount_cents", 0),
            payload.get("currency", ""),
        )].append(record)

    found = []
    for (vendor, number, amount, currency), rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        if invoice_key and not any(r["record_key"] == invoice_key for r in rows):
            continue
        found.append({
            "id": "ap-duplicate-" + duplicate_key(vendor, number, amount, currency),
            "vendor_id": rows[0]["payload"].get("vendor_id", ""),
            "invoice_number": rows[0]["payload"].get("invoice_number", ""),
            "amount_cents": amount,
            "count": len(rows),
            # What is at stake if they are duplicates: the repeats, not the whole group.
            "exposure_cents": (len(rows) - 1) * amount,
            "record_keys": [r["record_key"] for r in rows],
            "citations": [_cite(r, "matching invoice") for r in rows],
            "note": "Same vendor, invoice number, amount and currency on more than one "
                    "record. This does not establish that anything was paid twice.",
        })
    return found
