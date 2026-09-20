"""Read-only tools for the AR (accounts receivable) reconciliation benchmark
(https://github.com/ciru-ai/invoice-sandbox-benchmark).

These are NOT part of the AP & Payments agent's default toolkit. spec.md
scoped AP/AR aging as a deferred, cut feature, and grepping every agent
family in this repo turns up zero AR implementation — this module exists to
be passed as `extra_tools`/`extra_tool_specs` into `run_ap_agent` for this one
task (see ar_reconciliation.run_ar_reconciliation), not to permanently widen
what the AP agent does by default.

Every tool takes `workspace` as an absolute filesystem path to a benchmark
run's `workspace/` directory (e.g. `runs/test-001/workspace`) — real data the
benchmark's own reset_env.py copies from its gold_master, not a fixture label
like ap_tools.py's "sandbox"/"mit". Every read is path-checked to stay inside
that directory: the same "authorized source scope" principle this project
already applies to JSON fixtures, applied here to a real filesystem.

Invoices are multi-page "packets": page 1 states the actual invoice fields
(customer, line items, subtotal/discount/tax/total); later pages are
deliberately verbose distractor content (service logs, control sheets,
boilerplate terms), and the documents say so themselves ("Supporting pages
are intentionally verbose. The payable financial facts are ... shown on the
primary invoice page."). read_invoices returns page 1 text only, by design —
reading every page of 110+ invoices would spend tool-output tokens on noise
the source documents themselves flag as irrelevant.
"""

from __future__ import annotations

import csv
import mailbox
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

MAX_INVOICE_BATCH = 20  # keeps one tool_result readable; ~112 invoices -> ~6 calls


class WorkspacePathError(ValueError):
    """A requested file resolves outside the authorized workspace directory."""


def _resolve(workspace: str, relative_path: str) -> Path:
    root = Path(workspace).resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise WorkspacePathError(f"'{relative_path}' is outside the authorized workspace")
    return candidate


def _read_csv_folder(workspace: str, folder: str) -> dict[str, list[dict[str, str]]]:
    root = _resolve(workspace, folder)
    if not root.is_dir():
        return {}
    files: dict[str, list[dict[str, str]]] = {}
    for path in sorted(root.glob("*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as f:
            files[path.name] = list(csv.DictReader(f))
    return files


def list_invoice_files(workspace: str) -> dict[str, Any]:
    """List every filename under invoices/. Filenames often carry real signal
    (a scanned duplicate, a void marker, a statement) — that's the real
    filesystem, not a hint to trust without opening the file."""
    root = _resolve(workspace, "invoices")
    if not root.is_dir():
        return {"files": []}
    return {"files": sorted(p.name for p in root.iterdir() if p.is_file())}


def read_invoices(file_names: list[str], workspace: str) -> dict[str, Any]:
    """Read page 1 of each named invoice PDF under invoices/. Batch up to
    MAX_INVOICE_BATCH filenames per call — call this repeatedly to cover
    every file list_invoice_files returned."""
    from pypdf import PdfReader  # imported lazily: only this tool needs it

    if len(file_names) > MAX_INVOICE_BATCH:
        return {"error": f"too many files in one batch (max {MAX_INVOICE_BATCH}); split into smaller calls"}

    documents: dict[str, Any] = {}
    for name in file_names:
        try:
            path = _resolve(workspace, f"invoices/{name}")
        except WorkspacePathError as exc:
            documents[name] = {"error": str(exc)}
            continue
        if not path.is_file():
            documents[name] = {"error": "not found"}
            continue
        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        first_page_text = reader.pages[0].extract_text() if page_count else ""
        documents[name] = {"page_1_text": first_page_text or "", "page_count": page_count}
    return {"documents": documents}


def read_bank_exports(workspace: str) -> dict[str, Any]:
    """Read every CSV under bank_exports/ in full. These are payments and
    deposits received, not customer spend — a bank row is not an invoice."""
    return {"files": _read_csv_folder(workspace, "bank_exports")}


def read_crm_master(workspace: str) -> dict[str, Any]:
    """Read the customer master CSV(s): customer_id, canonical name, and any
    aliases on record."""
    return {"files": _read_csv_folder(workspace, "crm")}


def read_operations_files(workspace: str) -> dict[str, Any]:
    """Read every file under operations/ (AR aging, service catalog) and
    notes/ (controller close notes) in full — reference context, not
    source-of-truth invoice records."""
    result: dict[str, Any] = {}
    for folder in ("operations", "notes"):
        root = _resolve(workspace, folder)
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            if not path.is_file():
                continue
            if path.suffix == ".csv":
                with path.open(newline="", encoding="utf-8-sig") as f:
                    result[f"{folder}/{path.name}"] = list(csv.DictReader(f))
            else:
                result[f"{folder}/{path.name}"] = path.read_text(encoding="utf-8", errors="replace")
    return result


def read_email_archive(workspace: str) -> dict[str, Any]:
    """Read every email under email_archive/ (.eml files and any .mbox
    archive) as {subject, from, date, body}. Correspondence only — an email
    quoting an invoice total is not itself a billable record."""
    root = _resolve(workspace, "email_archive")
    messages: list[dict[str, str]] = []
    if not root.is_dir():
        return {"messages": messages}

    for path in sorted(root.glob("**/*.eml")):
        with path.open("rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)
        messages.append(_summarize_message(msg, source=path.name))

    for mbox_path in sorted(root.glob("*.mbox")):
        for msg in mailbox.mbox(str(mbox_path)):
            messages.append(_summarize_message(msg, source=mbox_path.name))

    return {"messages": messages}


def _summarize_message(msg: Any, *, source: str) -> dict[str, str]:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                body = payload.decode(errors="replace") if isinstance(payload, bytes) else str(payload or "")
                break
    else:
        payload = msg.get_payload(decode=True)
        body = payload.decode(errors="replace") if isinstance(payload, bytes) else str(msg.get_payload())
    return {
        "source": source,
        "subject": str(msg.get("Subject", "")),
        "from": str(msg.get("From", "")),
        "date": str(msg.get("Date", "")),
        "body": body[:2000],  # context, not a source to transcribe amounts from
    }


AR_READ_TOOLS = {
    "list_invoice_files": list_invoice_files,
    "read_invoices": read_invoices,
    "read_bank_exports": read_bank_exports,
    "read_crm_master": read_crm_master,
    "read_operations_files": read_operations_files,
    "read_email_archive": read_email_archive,
}

AR_READ_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "list_invoice_files",
        "description": "List every filename in the invoices/ folder.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "read_invoices",
        "description": f"Read page 1 (the actual invoice fields) of up to {MAX_INVOICE_BATCH} named invoice "
        "PDFs per call. Later pages are deliberately verbose distractor content, not additional "
        "invoice data — the documents themselves say so. Call repeatedly to cover every file "
        "returned by list_invoice_files.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"Up to {MAX_INVOICE_BATCH} filenames from invoices/.",
                }
            },
            "required": ["file_names"],
        },
    },
    {
        "type": "function",
        "name": "read_bank_exports",
        "description": "Read every bank export CSV in full. These are payments/deposits received, not "
        "customer invoice spend.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "read_crm_master",
        "description": "Read the customer master record(s): canonical customer_id, name, and known aliases.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "read_operations_files",
        "description": "Read AR aging, service catalog, and controller close notes in full.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "read_email_archive",
        "description": "Read every email (.eml and .mbox) as subject/from/date/body. Correspondence only — "
        "an email quoting an invoice total is not itself a billable record.",
        "parameters": {"type": "object", "properties": {}},
    },
]

assert {spec["name"] for spec in AR_READ_TOOL_SPECS} == set(AR_READ_TOOLS), (
    "AR_READ_TOOL_SPECS and AR_READ_TOOLS must match 1:1"
)
