"""Evaluation metrics for the extraction model (spec.md §7.5 step 4, brief §5).

Scores a set of predictions against human-verified labels. Deliberately pure
and model-free: it takes already-produced predictions, so it can be unit
tested and re-run offline against saved output without paying for inference
again.

The outcome taxonomy is the point. "Field accuracy" alone hides the two
failures that matter most in an audit context:

  * over-extraction (hallucination) — the label says the field is absent, the
    model produced a value anyway. In accounting, an invented PO reference or
    service date is worse than a blank one, because it looks like evidence.
  * wrong-value — the field exists and the model found it but got it wrong.
    Counted against BOTH precision and recall, never as a partial credit.

Correct abstention (label absent, prediction absent) is scored as its own
success, not silently dropped — a model that abstains correctly is doing the
job spec.md asks of it ("Never guess missing IDs, currencies, dates, or
amounts").

Citation accuracy is a real check, not a self-report: the quotation must
actually occur in the source page text. A model that produces the right value
with a fabricated quotation fails this, which is exactly the property that
makes an extraction reviewable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable

MONEY_FIELDS = {
    "subtotal", "tax", "total", "amount", "unit_price", "gross_pay", "net_pay",
    "total_deductions", "employer_costs", "ceiling_amount", "allocation_amount",
    "change_to_ceiling",
}
DATE_FIELDS = {
    "invoice_date", "service_date", "payment_due_date", "eligible_start_date",
    "eligible_end_date", "amendment_date", "pay_period_start", "pay_period_end",
    "service_period_start", "service_period_end",
}
ID_FIELDS = {
    "invoice_number", "purchase_order_reference", "receipt_reference", "award_id",
    "employee_identifier",
}


class Outcome(str, Enum):
    correct = "correct"                    # label present, prediction matches
    wrong_value = "wrong_value"            # label present, prediction present but different
    missed = "missed"                      # label present, prediction absent
    over_extracted = "over_extracted"      # label absent, prediction present (hallucination)
    correct_abstention = "correct_abstention"  # label absent, prediction absent


@dataclass
class FieldResult:
    field_name: str
    outcome: Outcome
    expected: str | None
    predicted: str | None
    citation_ok: bool | None = None   # None when there is nothing to cite
    supported: bool | None = None     # None when there is nothing to support


@dataclass
class ExampleResult:
    example_id: str
    split_key: str
    valid_json: bool
    fields: list[FieldResult] = field(default_factory=list)
    latency_s: float | None = None
    peak_memory_gb: float | None = None


def current_peak_memory_gb() -> float | None:
    """Peak memory on the device actually running the model. The brief asks
    for 'latency and memory use on the actual demo hardware', and memory is
    the constraint that bit hardest in practice: a leaked PyMuPDF handle plus
    an ungrown-back MPS cache pushed a 24GB machine into swap mid-run and took
    per-document time from 28s to 615s."""
    try:
        import torch
    except ImportError:
        return None

    if torch.backends.mps.is_available():
        return torch.mps.driver_allocated_memory() / 1e9
    if torch.cuda.is_available():
        return torch.cuda.max_memory_allocated() / 1e9
    return None


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def normalize_money(value: str) -> Decimal | None:
    cleaned = _nfkc(value).strip()
    # Accounting negatives: (1,234.56) means -1234.56
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    cleaned = re.sub(r"[^\d.\-]", "", cleaned)
    if not cleaned or cleaned in {"-", ".", "-."}:
        return None
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -amount if negative else amount


_DATE_PATTERNS = [
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"), (1, 2, 3)),
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$"), (3, 1, 2)),   # US m/d/Y
    (re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$"), (1, 2, 3)),
    (re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$"), (3, 1, 2)),
]

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# "March 20, 2024" / "20 March 2024" / "Mar 20 2024". Month names are
# unambiguous about day/month order, unlike pure-numeric formats, so these
# are safe to normalize.
_MONTH_FIRST = re.compile(r"^([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$", re.I)
_DAY_FIRST = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\.?,?\s+(\d{4})$", re.I)


def normalize_date(value: str) -> str | None:
    """Return ISO yyyy-mm-dd when the format is recognized, else None.

    A purely numeric format we don't recognize is NOT coerced — guessing
    day/month order would silently score a wrong date as correct. Month-name
    formats are safe because the name fixes the order, and they matter in
    practice: the APEX contract-attorney invoices print "March 20, 2024",
    so without this a model correctly answering "2024-03-20" would be
    marked wrong.
    """
    text = _nfkc(value).strip()
    for pattern, (y, m, d) in _DATE_PATTERNS:
        match = pattern.match(text)
        if match:
            return f"{int(match.group(y)):04d}-{int(match.group(m)):02d}-{int(match.group(d)):02d}"

    for pattern, (month_group, day_group, year_group) in ((_MONTH_FIRST, (1, 2, 3)), (_DAY_FIRST, (2, 1, 3))):
        match = pattern.match(text)
        if match:
            month = _MONTHS.get(match.group(month_group).lower())
            if month:
                return f"{int(match.group(year_group)):04d}-{month:02d}-{int(match.group(day_group)):02d}"
    return None


def normalize_id(value: str) -> str:
    return re.sub(r"[\s ]+", "", _nfkc(value)).upper()


_CURRENCY_ALIASES = {
    "$": "USD", "US$": "USD", "USD": "USD", "DOLLARS": "USD", "US DOLLARS": "USD",
    "€": "EUR", "EUR": "EUR", "EUROS": "EUR",
    "£": "GBP", "GBP": "GBP", "POUNDS": "GBP",
    "¥": "JPY", "JPY": "JPY",
}


def normalize_currency(value: str) -> str:
    """Map a currency symbol to its ISO code.

    Added after the APEX run: the model returned "$" (what the invoice prints,
    which is what a `verbatim-string` field asks for) against labels reading
    "USD", and that single convention mismatch produced 21 of 27 apparent
    failures. Both answers are right; the schema just never said which form it
    wanted. Normalizing here is the same move already made for money and
    dates, and it keeps the extraction faithful to the page while letting the
    label be canonical."""
    text = re.sub(r"[\s ]+", " ", _nfkc(value)).strip().upper()
    return _CURRENCY_ALIASES.get(text, text)


def values_match(field_name: str, expected: str, predicted: str) -> bool:
    if field_name in MONEY_FIELDS:
        exp, pred = normalize_money(expected), normalize_money(predicted)
        return exp is not None and pred is not None and exp == pred
    if field_name in DATE_FIELDS:
        exp_iso, pred_iso = normalize_date(expected), normalize_date(predicted)
        if exp_iso and pred_iso:
            return exp_iso == pred_iso
        return _nfkc(expected).strip() == _nfkc(predicted).strip()
    if field_name in ID_FIELDS:
        return normalize_id(expected) == normalize_id(predicted)
    if field_name == "currency":
        return normalize_currency(expected) == normalize_currency(predicted)
    return " ".join(_nfkc(expected).split()).casefold() == " ".join(_nfkc(predicted).split()).casefold()


def _is_blank(value: str | None) -> bool:
    return value is None or not str(value).strip()


def citation_resolves(quotation: str | None, page_text: str | None) -> bool | None:
    """True when the quotation actually occurs in the source text. None when
    there's nothing to check (no quotation and no claim)."""
    if quotation is None or not quotation.strip():
        return None
    if page_text is None:
        return None
    haystack = " ".join(_nfkc(page_text).split()).casefold()
    needle = " ".join(_nfkc(quotation).split()).casefold()
    return needle in haystack


def score_fields(
    expected_fields: dict[str, str | None],
    predicted: dict[str, Any],
    page_text: str | None = None,
) -> list[FieldResult]:
    """`predicted` maps field_name -> RawExtraction-like object or dict with
    .value/.quotation. Only fields present in expected_fields are scored:
    the label set defines the task, so a model emitting extra keys is not
    penalized here (that's schema validity, measured separately)."""
    results: list[FieldResult] = []
    for name, expected in expected_fields.items():
        entry = predicted.get(name)
        if entry is None:
            pred_value, quotation = None, None
        elif isinstance(entry, dict):
            pred_value, quotation = entry.get("value"), entry.get("quotation")
        else:  # RawExtraction
            pred_value, quotation = entry.value, entry.quotation

        expected_blank, predicted_blank = _is_blank(expected), _is_blank(pred_value)

        if expected_blank and predicted_blank:
            outcome = Outcome.correct_abstention
        elif expected_blank:
            outcome = Outcome.over_extracted
        elif predicted_blank:
            outcome = Outcome.missed
        elif values_match(name, str(expected), str(pred_value)):
            outcome = Outcome.correct
        else:
            outcome = Outcome.wrong_value

        cited = citation_resolves(quotation, page_text) if not predicted_blank else None
        results.append(
            FieldResult(
                field_name=name,
                outcome=outcome,
                expected=expected,
                predicted=pred_value,
                citation_ok=cited,
                supported=(not _is_blank(quotation)) if not predicted_blank else None,
            )
        )
    return results


def aggregate(results: Iterable[ExampleResult]) -> dict[str, Any]:
    results = list(results)
    counts = {outcome: 0 for outcome in Outcome}
    by_category: dict[str, dict[str, int]] = {
        "money": {"correct": 0, "total": 0},
        "date": {"correct": 0, "total": 0},
        "id": {"correct": 0, "total": 0},
    }
    citation_checked = citation_ok = 0
    claims = unsupported = 0
    latencies: list[float] = []
    memories: list[float] = []

    for example in results:
        if example.latency_s is not None:
            latencies.append(example.latency_s)
        if example.peak_memory_gb is not None:
            memories.append(example.peak_memory_gb)
        for item in example.fields:
            counts[item.outcome] += 1

            category = (
                "money" if item.field_name in MONEY_FIELDS
                else "date" if item.field_name in DATE_FIELDS
                else "id" if item.field_name in ID_FIELDS
                else None
            )
            if category and item.outcome in (Outcome.correct, Outcome.wrong_value, Outcome.missed):
                by_category[category]["total"] += 1
                if item.outcome is Outcome.correct:
                    by_category[category]["correct"] += 1

            if item.citation_ok is not None:
                citation_checked += 1
                citation_ok += int(item.citation_ok)
            if item.supported is not None:
                claims += 1
                unsupported += int(not item.supported)

    correct = counts[Outcome.correct]
    wrong = counts[Outcome.wrong_value]
    missed = counts[Outcome.missed]
    over = counts[Outcome.over_extracted]
    abstained = counts[Outcome.correct_abstention]

    predicted_positives = correct + wrong + over
    actual_positives = correct + wrong + missed
    precision = correct / predicted_positives if predicted_positives else 0.0
    recall = correct / actual_positives if actual_positives else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    abstention_opportunities = abstained + over
    return {
        "examples": len(results),
        "valid_json_rate": (sum(r.valid_json for r in results) / len(results)) if results else 0.0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "outcomes": {outcome.value: counts[outcome] for outcome in Outcome},
        "exact_accuracy": {
            category: round(vals["correct"] / vals["total"], 4) if vals["total"] else None
            for category, vals in by_category.items()
        },
        "citation_accuracy": round(citation_ok / citation_checked, 4) if citation_checked else None,
        "unsupported_extraction_rate": round(unsupported / claims, 4) if claims else None,
        "abstention_quality": (
            round(abstained / abstention_opportunities, 4) if abstention_opportunities else None
        ),
        "latency_s": {
            "mean": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "max": round(max(latencies), 2) if latencies else None,
        },
        "peak_memory_gb": round(max(memories), 2) if memories else None,
    }


def format_report(summary: dict[str, Any], title: str = "extraction evaluation") -> str:
    lines = [f"=== {title} ===", f"examples: {summary['examples']}"]
    lines.append(f"valid_json_rate: {summary['valid_json_rate']:.4f}")
    lines.append(f"precision/recall/f1: {summary['precision']} / {summary['recall']} / {summary['f1']}")
    lines.append("outcomes:")
    for name, count in summary["outcomes"].items():
        lines.append(f"  {name}: {count}")
    lines.append("exact accuracy:")
    for category, value in summary["exact_accuracy"].items():
        lines.append(f"  {category}: {value}")
    lines.append(f"citation_accuracy: {summary['citation_accuracy']}")
    lines.append(f"unsupported_extraction_rate: {summary['unsupported_extraction_rate']}")
    lines.append(f"abstention_quality: {summary['abstention_quality']}")
    lines.append(f"latency_s mean/max: {summary['latency_s']['mean']} / {summary['latency_s']['max']}")
    lines.append(f"peak_memory_gb: {summary['peak_memory_gb']}")
    return "\n".join(lines)
