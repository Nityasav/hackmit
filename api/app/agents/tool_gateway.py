"""OpenAI tool-calling gateway for the AP & Payments agent.

Two things live here that don't belong in the tool modules themselves:

1. TOOL_SPECS — the OpenAI function-calling tool schemas the model actually
   sees (Responses API shape: `{"type": "function", "name", "description",
   "parameters"}`). `workspace` is bound when a ToolGateway is constructed and
   never exposed as a parameter in the schema: which workspace to read is an
   orchestrator decision, not something the model should be free to pick.
2. Budget enforcement — spec.md §8's default of 12 tool calls per task. A
   ToolGateway belongs to exactly one task run. Each concurrent specialist (AP,
   Payroll, Grants) gets its own instance and its own counter, so one agent's
   run can never starve or corrupt another's.

The registry is split in two on purpose. READ_TOOLS (ap_tools) are pure
functions over a cached, immutable fixture — safe to call concurrently, no
locking needed (spec.md §8: specialists investigate against an immutable
snapshot). WRITE_TOOLS (ap_write_tools) append proposals to the shared Bundle;
they serialize through store's lock, and every one of them is append-only and
human-gated. Nothing here can approve, release, or activate anything.

A run loop (Phase 3) uses this as:

    gateway = ToolGateway(workspace="sandbox")
    ... pass gateway.remaining and TOOL_SPECS to the model ...
    result = gateway.call(tool_name, **tool_input)   # -> function_call_output
    ... on ToolBudgetExceeded, stop the run and show it as the stop reason ...
    decision.how = gateway.as_decision_log()          # -> Decision.how (app.models)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from . import ap_tools, ap_write_tools, au_write_tools

DEFAULT_BUDGET = 12  # spec.md §8: 12 tool calls per task


class ToolBudgetExceeded(RuntimeError):
    """A task tried to call a tool past its per-run budget.

    The run loop must catch this and stop with a visible reason (spec.md §8)
    rather than let the run continue on an uncounted call.
    """

    def __init__(self, tool_name: str, budget: int):
        super().__init__(f"tool budget exhausted ({budget}/{budget} used) — refused '{tool_name}'")
        self.tool_name = tool_name
        self.budget = budget


class UnknownTool(KeyError):
    """The model asked for a tool name that isn't registered.

    Deliberately does not consume budget — nothing ran. The run loop can feed
    this back to the model as a function_call_output error so it can self-correct.
    """


def _serialize(value: Any) -> Any:
    """Make a tool result JSON-safe for a function_call_output's `output` field."""
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


def _summarize(result: Any) -> str:
    """Short human-readable line for the decision log. Never the full payload —
    the Reasoning log shows concise records, not raw dumps (spec.md §8)."""
    if result is None:
        return "not found"
    if isinstance(result, list):
        return f"{len(result)} result{'' if len(result) == 1 else 's'}"
    if isinstance(result, dict):
        if "error" in result:
            return str(result["error"])
        # Write tools report what they filed; reads report which parts came back.
        for key in ("finding_id", "approval_id"):
            if key in result:
                return f"{result[key]} ({result.get('status', 'filed')})"
        present = [k for k, v in result.items() if v not in (None, [], {})]
        return f"packet: {', '.join(present)}" if present else "empty packet"
    if isinstance(result, BaseModel):
        ident = getattr(result, "id", None) or getattr(result, "name", "")
        return f"{type(result).__name__} {ident}".strip()
    return str(result)


@dataclass
class ToolCallRecord:
    tool: str
    input: dict[str, Any]
    output_summary: str
    output_json: Any


READ_TOOLS: dict[str, Callable[..., Any]] = {
    "get_vendor": ap_tools.get_vendor,
    "list_vendors": ap_tools.list_vendors,
    "get_purchase_order": ap_tools.get_purchase_order,
    "list_purchase_orders": ap_tools.list_purchase_orders,
    "get_goods_receipt": ap_tools.get_goods_receipt,
    "get_receipts_for_po": ap_tools.get_receipts_for_po,
    "get_invoice": ap_tools.get_invoice,
    "list_invoices": ap_tools.list_invoices,
    "find_duplicate_candidates": ap_tools.find_duplicate_candidates,
    "get_approvals_for_record": ap_tools.get_approvals_for_record,
    "get_payment_batch": ap_tools.get_payment_batch,
    "get_invoice_packet": ap_tools.get_invoice_packet,
}

WRITE_TOOLS: dict[str, Callable[..., Any]] = {
    "submit_finding": ap_write_tools.submit_finding,
    "request_evidence": ap_write_tools.request_evidence,
    "prepare_payment_batch": ap_write_tools.prepare_payment_batch,
}

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {**READ_TOOLS, **WRITE_TOOLS}

READ_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_vendor",
        "description": "Look up one vendor by ID. Returns null if it doesn't exist.",
        "parameters": {
            "type": "object",
            "properties": {"vendor_id": {"type": "string", "description": "Vendor ID, e.g. 'V-08'."}},
            "required": ["vendor_id"],
        },
    },
    {
        "type": "function",
        "name": "list_vendors",
        "description": "List every known vendor.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "get_purchase_order",
        "description": "Get PO line(s) for a purchase order ID. A PO may span several lines; "
        "pass `line` to narrow to one.",
        "parameters": {
            "type": "object",
            "properties": {
                "po_id": {"type": "string", "description": "Purchase order ID, e.g. 'PO-901'."},
                "line": {"type": "integer", "description": "Optional line number to narrow to a single line."},
            },
            "required": ["po_id"],
        },
    },
    {
        "type": "function",
        "name": "list_purchase_orders",
        "description": "List PO lines, optionally filtered to one vendor.",
        "parameters": {
            "type": "object",
            "properties": {"vendor_id": {"type": "string", "description": "Optional vendor ID to filter by."}},
        },
    },
    {
        "type": "function",
        "name": "get_goods_receipt",
        "description": "Look up one goods receipt by ID.",
        "parameters": {
            "type": "object",
            "properties": {"receipt_id": {"type": "string", "description": "Goods receipt ID, e.g. 'RCPT-551'."}},
            "required": ["receipt_id"],
        },
    },
    {
        "type": "function",
        "name": "get_receipts_for_po",
        "description": "List goods receipts recorded against a PO, optionally narrowed to one line.",
        "parameters": {
            "type": "object",
            "properties": {
                "po_id": {"type": "string", "description": "Purchase order ID."},
                "line": {"type": "integer", "description": "Optional PO line number."},
            },
            "required": ["po_id"],
        },
    },
    {
        "type": "function",
        "name": "get_invoice",
        "description": "Look up one invoice by ID.",
        "parameters": {
            "type": "object",
            "properties": {"invoice_id": {"type": "string", "description": "Invoice ID, e.g. 'INV-2291'."}},
            "required": ["invoice_id"],
        },
    },
    {
        "type": "function",
        "name": "list_invoices",
        "description": "List invoices, optionally filtered by vendor and/or status.",
        "parameters": {
            "type": "object",
            "properties": {
                "vendor_id": {"type": "string", "description": "Optional vendor ID to filter by."},
                "status": {
                    "type": "string",
                    "enum": ["open", "matched", "exception", "held", "paid"],
                    "description": "Optional invoice status to filter by.",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "find_duplicate_candidates",
        "description": "Find other invoices from the same vendor with the same net amount as the given "
        "invoice. These are candidates to investigate, not confirmed duplicates — check "
        "get_receipts_for_po on each candidate for counterevidence (separate deliveries "
        "are common and clear the pair).",
        "parameters": {
            "type": "object",
            "properties": {"invoice_id": {"type": "string", "description": "Invoice ID to check."}},
            "required": ["invoice_id"],
        },
    },
    {
        "type": "function",
        "name": "get_approvals_for_record",
        "description": "List approval records referencing a given invoice or PO ID.",
        "parameters": {
            "type": "object",
            "properties": {"record_id": {"type": "string", "description": "Invoice or PO ID."}},
            "required": ["record_id"],
        },
    },
    {
        "type": "function",
        "name": "get_payment_batch",
        "description": "Look up one simulated payment batch by ID, including any held invoices and why.",
        "parameters": {
            "type": "object",
            "properties": {"batch_id": {"type": "string", "description": "Payment batch ID, e.g. 'PAY-B9'."}},
            "required": ["batch_id"],
        },
    },
    {
        "type": "function",
        "name": "get_invoice_packet",
        "description": "Everything needed to start judging one invoice, in a single call: the invoice, "
        "its vendor, matched PO line, goods receipts, approvals, and same-vendor/same-amount "
        "duplicate candidates. Prefer this over separate calls when starting work on an invoice.",
        "parameters": {
            "type": "object",
            "properties": {"invoice_id": {"type": "string", "description": "Invoice ID to investigate."}},
            "required": ["invoice_id"],
        },
    },
]

WRITE_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "submit_finding",
        "description": "File a finding for Internal Auditor review. Every finding must carry evidence; "
        "you cannot mark your own finding verified. An amount requires an amount_note "
        "stating its basis (e.g. 'reclassification - cash $0'). Filing a finding does not "
        "make it true to the human: it goes to the auditor first.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short headline, no accusation language."},
                "summary": {"type": "string", "description": "One or two sentences: condition and criterion."},
                "status": {
                    "type": "string",
                    "enum": ["substantiated", "cleared", "explained", "needs_evidence", "none_reported", "ties"],
                    "description": "Use needs_evidence when support is missing; cleared when counterevidence resolved it.",
                },
                "evidence": {
                    "type": "array",
                    "description": "The evidence path, source to conclusion. Required, non-empty.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "e.g. 'INV-2291 - $2,400.00'."},
                            "kind": {"type": "string", "enum": ["record", "award", "doc", "calc", "page"]},
                            "tone": {"type": "string", "enum": ["neutral", "bad", "good"]},
                            "edge": {
                                "type": "string",
                                "description": "Relationship to the next node, e.g. MATCHED_TO, CONTRADICTED_BY.",
                            },
                        },
                        "required": ["label", "kind", "tone"],
                    },
                },
                "amount_cents": {"type": "integer", "description": "Optional. Integer cents, never a float."},
                "amount_note": {"type": "string", "description": "Required if amount_cents is set: what the amount is."},
            },
            "required": ["title", "summary", "status", "evidence"],
        },
    },
    {
        "type": "function",
        "name": "request_evidence",
        "description": "Ask the human for a document you don't have. Adds an item to the in-app approval "
        "queue and sends nothing externally. Use this instead of guessing when a conclusion "
        "depends on a record you cannot retrieve.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "What document you need, e.g. 'Upload October service record'."},
                "summary": {"type": "string", "description": "Why it's needed and what it would resolve."},
            },
            "required": ["title", "summary"],
        },
    },
    {
        "type": "function",
        "name": "prepare_payment_batch",
        "description": "Assemble a simulated payment batch from invoice IDs and send it to the human queue. "
        "You cannot release funds. Hold rules are applied independently of your judgment: any "
        "invoice with changed vendor bank details, a missing invoice approval, a status other "
        "than matched, or an unresolved duplicate candidate is held out and reported back to "
        "you with the reason.",
        "parameters": {
            "type": "object",
            "properties": {
                "invoice_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Candidate invoice IDs for the batch.",
                },
            },
            "required": ["invoice_ids"],
        },
    },
]

TOOL_SPECS: list[dict[str, Any]] = [*READ_TOOL_SPECS, *WRITE_TOOL_SPECS]

assert {spec["name"] for spec in TOOL_SPECS} == set(TOOL_REGISTRY), "TOOL_SPECS and TOOL_REGISTRY must match 1:1"
assert {spec["name"] for spec in WRITE_TOOL_SPECS} == set(WRITE_TOOLS), "write specs and WRITE_TOOLS must match 1:1"

# The Internal Auditor gets the same reads as AP (it re-performs the same AP
# investigation from originals) but a different, narrower write side: it can
# only submit_review, never submit_finding/prepare_payment_batch — spec.md §8:
# "You cannot review your own preparation as an independent check."
AUDITOR_WRITE_TOOLS: dict[str, Callable[..., Any]] = {
    "submit_review": au_write_tools.submit_review,
}
AUDITOR_REGISTRY: dict[str, Callable[..., Any]] = {
    **READ_TOOLS, **AUDITOR_WRITE_TOOLS, "get_finding": au_write_tools.get_finding,
}

AUDITOR_WRITE_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "submit_review",
        "description": "Independently accept, reject, or request more evidence on a finding you did not "
        "write. You must re-perform the check yourself with your own tool calls first — agreeing "
        "with the preparer's summary is not a review. `accept` verifies the finding; `reject` or "
        "`needs_evidence` clears verification and sends it back for a specific missing-evidence "
        "search or recalculation, not a repeated assertion.",
        "parameters": {
            "type": "object",
            "properties": {
                "finding_id": {"type": "string", "description": "The finding you independently re-checked."},
                "decision": {"type": "string", "enum": ["accept", "reject", "needs_evidence"]},
                "evidence_note": {
                    "type": "string",
                    "description": "What you personally re-checked and found, citing the original sources "
                    "you re-read — not the preparer's claim.",
                },
            },
            "required": ["finding_id", "decision", "evidence_note"],
        },
    },
]

AUDITOR_TOOL_SPECS: list[dict[str, Any]] = [*READ_TOOL_SPECS, *AUDITOR_WRITE_TOOL_SPECS, {
    "type": "function", "name": "get_finding",
    "description": "Read the exact untrusted preparer finding by F-* ID before independently checking original records.",
    "strict": True,
    "parameters": {"type": "object", "properties": {"finding_id": {"type": "string"}},
                   "required": ["finding_id"], "additionalProperties": False},
}]

assert {spec["name"] for spec in AUDITOR_TOOL_SPECS} == set(AUDITOR_REGISTRY), (
    "AUDITOR_TOOL_SPECS and AUDITOR_REGISTRY must match 1:1"
)


class ToolGateway:
    """Owns the tool-call budget and call log for exactly one task run.

    Never share an instance across tasks or across concurrent specialists —
    that would let one agent's investigation exhaust another's budget.
    `registry` defaults to the AP registry; pass AUDITOR_REGISTRY (or any other
    role's) to run a gateway scoped to a different tool set.
    """

    def __init__(
        self,
        workspace: str = "sandbox",
        budget: int = DEFAULT_BUDGET,
        registry: dict[str, Callable[..., Any]] | None = None,
    ):
        self.workspace = workspace
        self.budget = budget
        self.used = 0
        self.calls: list[ToolCallRecord] = []
        self.registry: dict[str, Callable[..., Any]] = dict(TOOL_REGISTRY if registry is None else registry)

    @property
    def remaining(self) -> int:
        return self.budget - self.used

    def call(self, tool_name: str, **tool_input: Any) -> Any:
        """Dispatch one tool call and return a JSON-serializable result — feed
        this straight back to the model as a function_call_output's `output`.

        Raises UnknownTool for a name that isn't registered (no budget spent)
        and ToolBudgetExceeded once the run's budget is gone (run must stop).
        A call with bad arguments, a reference to a record that doesn't exist
        (a finding/task/approval ID the model made up or mistyped), or one
        that breaks a write-tool rule (a finding with no evidence, an amount
        with no basis), still consumes budget — it was a real attempt — but
        returns an {"error": ...} payload instead of raising, so the model can
        see the mistake and correct it within its remaining budget rather than
        killing the run (a real failure mode: a nested specialist run started
        via assign_task has no other way to surface this than crashing its
        caller, all the way up through the CFO's own run, unless it's caught
        here).
        """
        if tool_name not in self.registry:
            raise UnknownTool(tool_name)
        if self.used >= self.budget:
            raise ToolBudgetExceeded(tool_name, self.budget)

        fn = self.registry[tool_name]
        try:
            result: Any = fn(**tool_input, workspace=self.workspace)
        except TypeError as exc:
            result = {"error": f"invalid arguments for {tool_name}: {exc}"}
        except ValueError as exc:
            # Includes pydantic ValidationError: a rejected proposal, not a bug.
            result = {"error": f"{tool_name} rejected: {exc}"}
        except KeyError as exc:
            # store.apply_review/decide_approval raise this for an unknown ID.
            # UnknownTool is also a KeyError but is raised above, outside this
            # try block, so it never reaches here.
            result = {"error": f"{tool_name}: no such record {exc}"}

        self.used += 1
        serialized = _serialize(result)
        self.calls.append(
            ToolCallRecord(
                tool=tool_name,
                input=tool_input,
                output_summary=_summarize(result),
                output_json=serialized,
            )
        )
        return serialized

    def as_decision_log(self) -> list[dict[str, str]]:
        """Render the call log in app.models.ToolCall's (tool, input, output)
        shape, for a Decision record's `how` field (spec.md §8)."""
        return [
            {
                "tool": rec.tool,
                "input": ", ".join(f"{k}={v!r}" for k, v in rec.input.items()) or "(no args)",
                "output": rec.output_summary,
            }
            for rec in self.calls
        ]
