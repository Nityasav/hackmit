"""Turns the AR agent's document classifications into a scored submission.

classify_documents is a run-scoped write tool, bound as a closure the same
way run_loop._bind_record_decision and cfo_tools.bind_assign_task are: it
needs a ledger that lives for exactly one run, which a plain module-level
function (like ap_tools.py's) can't hold. The model classifies what it
actually read; reduce_to_customer_totals below does the only arithmetic in
the whole pipeline. Never let the model state a net_spend_usd total itself —
this is the same principle the rest of this project already states ("never
calculate authoritative financial results mentally"), applied to a benchmark
task instead of a SchoolTrace finding.

Money here is USD with cents, matching the benchmark's own answer key
(customer_totals.csv's amounts, e.g. "13473.71") — not the integer-cents
convention the rest of this codebase uses for SchoolTrace's own records.
Amounts are always Decimal, parsed from the model's string argument, never a
JSON float: summing 100+ floating-point dollar amounts is exactly the kind of
silent precision bug this benchmark's $0.01 tolerance would catch.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Literal

from .ar_tools import AR_READ_TOOL_SPECS, AR_READ_TOOLS
from .run_loop import AgentRunResult, run_ap_agent

DocumentType = Literal[
    "valid_invoice", "credit_memo", "void", "superseded", "duplicate", "statement", "not_applicable"
]

_VALID_DOCUMENT_TYPES = {
    "valid_invoice", "credit_memo", "void", "superseded", "duplicate", "statement", "not_applicable",
}


@dataclass
class DocumentClassification:
    file_path: str
    document_type: DocumentType
    reason: str
    customer_id: str | None = None
    amount_usd: Decimal | None = None


CLASSIFY_DOCUMENTS_SPEC: dict[str, Any] = {
    "type": "function",
    "name": "classify_documents",
    "description": "Record your classification of one or more documents you have actually read. Call this "
    "in batches as you finish reading each set of invoices — do not wait until the very end, and "
    "do not classify a file you have not opened with read_invoices. amount_usd is the total "
    "stated ON the document (a string like '13473.71'), never a sum you computed yourself.",
    "parameters": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "e.g. 'invoices/INV-2025-1001_C011.pdf'."},
                        "document_type": {
                            "type": "string",
                            "enum": sorted(_VALID_DOCUMENT_TYPES),
                        },
                        "reason": {"type": "string", "description": "Why this classification, briefly."},
                        "customer_id": {
                            "type": "string",
                            "description": "Required for valid_invoice/credit_memo.",
                        },
                        "amount_usd": {
                            "type": "string",
                            "description": "The total's magnitude as a positive number, e.g. '13473.71' — even "
                            "for a credit memo whose total is printed as negative on the document. Required "
                            "for valid_invoice/credit_memo.",
                        },
                    },
                    "required": ["file_path", "document_type", "reason"],
                },
            }
        },
        "required": ["classifications"],
    },
}


def bind_classify_documents(ledger: list[DocumentClassification]) -> Callable[..., dict[str, Any]]:
    """Build the classify_documents closure for one reconciliation run. The
    ledger list is mutated in place so the caller can read it back after the
    agent run finishes, the same pattern _bind_record_decision uses for its
    per-run state."""

    def classify_documents(classifications: list[dict[str, Any]], **_ignored: Any) -> dict[str, Any]:
        recorded = 0
        errors: list[str] = []
        for entry in classifications:
            file_path = entry.get("file_path")
            document_type = entry.get("document_type")
            reason = entry.get("reason", "")
            if not file_path or document_type not in _VALID_DOCUMENT_TYPES:
                errors.append(f"skipped invalid entry: {entry!r}")
                continue

            amount_usd: Decimal | None = None
            if entry.get("amount_usd") is not None:
                try:
                    amount_usd = Decimal(str(entry["amount_usd"]))
                except InvalidOperation:
                    errors.append(f"{file_path}: invalid amount_usd {entry['amount_usd']!r}")
                    continue

            ledger.append(
                DocumentClassification(
                    file_path=file_path,
                    document_type=document_type,
                    reason=reason,
                    customer_id=entry.get("customer_id"),
                    amount_usd=amount_usd,
                )
            )
            recorded += 1

        return {"recorded": recorded, "total_classified": len(ledger), "errors": errors}

    return classify_documents


def reduce_to_customer_totals(ledger: list[DocumentClassification]) -> dict[str, Decimal]:
    """The only arithmetic in this pipeline. valid_invoice adds, credit_memo
    subtracts, everything else (void/superseded/duplicate/statement/
    not_applicable) contributes zero — exactly the answer key's own
    net_spend_effect_usd rule. A later classification of the same file_path
    replaces an earlier one instead of double-counting it, so a model that
    reclassifies a document after re-reading it doesn't get charged twice."""
    latest: dict[str, DocumentClassification] = {}
    for entry in ledger:
        latest[entry.file_path] = entry

    totals: dict[str, Decimal] = {}
    for entry in latest.values():
        if entry.document_type not in ("valid_invoice", "credit_memo"):
            continue
        if entry.customer_id is None or entry.amount_usd is None:
            continue
        # Normalize to a magnitude before signing: a credit memo's total is
        # often printed as a negative number on the document itself (this
        # benchmark's own answer key stores it that way), and a model asked
        # for "the amount stated on the document" will reasonably transcribe
        # that sign literally. Taking abs() first makes this correct
        # regardless of which convention the model used, instead of silently
        # double-negating an already-negative value.
        magnitude = abs(entry.amount_usd)
        signed = magnitude if entry.document_type == "valid_invoice" else -magnitude
        totals[entry.customer_id] = totals.get(entry.customer_id, Decimal("0")) + signed
    return totals


def write_submission_csv(totals: dict[str, Decimal], output_path: str) -> Path:
    """Write exactly the two columns scripts/score_submission.py reads —
    it ignores everything else, so there's no reason to guess at richer output."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        f.write("customer_id,net_spend_usd\n")
        for customer_id in sorted(totals):
            f.write(f"{customer_id},{totals[customer_id].quantize(Decimal('0.01'))}\n")
    return path


# Task brief handed to run_ap_agent as `question` for this benchmark. The AP
# agent's own system prompt stays untouched (spec.md AGENT_PROMPTS.md AP
# role) — this is the per-run task, not a permanent identity change.
RECONCILIATION_BRIEF = """\
Reconcile customer accounts receivable from the documents in this workspace.

Goal: for every customer, compute gross valid invoice spend, credit memo
total, and net spend (gross minus credit memos). Also count valid invoices
per customer.

Process:
1. Call list_invoice_files to see every file under invoices/.
2. Call read_invoices in batches (up to 20 filenames per call) to read page 1
   of each. Later pages are documented distractor noise — do not transcribe
   amounts from them.
3. Call read_bank_exports, read_crm_master, and read_operations_files once
   each for context. Call read_email_archive once for context.
4. For every invoice file, call classify_documents with its document_type,
   customer_id, and the amount_usd exactly as stated on the document (never a
   number you computed).

Exclusion rules — do not count these as valid invoice spend:
- Voided invoices (document_type "void").
- The original of a superseded pair when a revision exists — classify the
  original as "superseded" and only the revision as "valid_invoice".
- Duplicate scans of an invoice already read elsewhere (document_type
  "duplicate") — do not double-count a repeated invoice number.
- Statement summaries (document_type "statement") — reference only.
- An email that quotes an invoice total with no backing invoice record is not
  itself billable spend; do not classify emails as invoices at all.
- Bank deposits are payments received, not new spend; do not classify bank
  rows as invoices.

Credit memos (document_type "credit_memo") subtract from net spend but do not
count toward the valid invoice count.

Classify every invoice file you find — do not skip any. Then call
record_decision summarizing what you did, citing the exact counts and any
documents you were unsure about.
"""


def run_ar_reconciliation(
    workspace_dir: str,
    *,
    budget: int = 80,
    max_turns: int = 60,
    client: Any = None,
) -> tuple[AgentRunResult, list[DocumentClassification]]:
    """Run the AP & Payments agent against one AR benchmark workspace
    directory (e.g. `runs/test-001/workspace` from
    https://github.com/ciru-ai/invoice-sandbox-benchmark). Returns the run
    result and the ledger of everything it classified — call
    reduce_to_customer_totals(ledger) and write_submission_csv(...) on the
    result to produce a scoreable submission.

    budget/max_turns default much higher than run_ap_agent's normal 12/25:
    ~112 invoices at up to 20 per read_invoices call plus a matching batch of
    classify_documents calls is roughly 15-20 tool calls at minimum, before
    any re-reads or corrections.
    """
    ledger: list[DocumentClassification] = []
    extra_tools = {**AR_READ_TOOLS, "classify_documents": bind_classify_documents(ledger)}
    extra_tool_specs = [*AR_READ_TOOL_SPECS, CLASSIFY_DOCUMENTS_SPEC]

    result = run_ap_agent(
        RECONCILIATION_BRIEF,
        workspace=workspace_dir,
        budget=budget,
        max_turns=max_turns,
        client=client,
        extra_tools=extra_tools,
        extra_tool_specs=extra_tool_specs,
    )
    return result, ledger
