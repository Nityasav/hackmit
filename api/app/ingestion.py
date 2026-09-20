"""Document intake, parsing and validation in one module.

The server owns amounts, identities, workspace scope and commit decisions.
Documents are evidence, never executable instructions or automatic postings.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
import hashlib
import io
import json
from pathlib import PurePath
import re
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

from . import db
from .accounting.money import parse_minor_units as money

MAX_FILE = 10 * 1024 * 1024
MAX_BATCH = 50 * 1024 * 1024
MAX_FILES = 20
MAX_ROWS = 50_000
PROFILE = "US_DISTRICT_MANAGEMENT_ACCRUAL_V1"
Role = Literal["chart", "opening", "ledger", "payroll", "grants", "budget", "invoice", "fees", "collections", "deposits", "sponsorships", "service", "policy", "document"]
DOCUMENT_ROLES = {"service", "policy", "document"}
# Money coming in: what a family or sponsor owes, what was received, and where it landed.
MONEY_IN_ROLES = {"fees", "collections", "deposits", "sponsorships"}
# Banking lags the till: cash taken on the last days of a period reaches the bank after it closes. A banking
# week is this intake's stated convention for how long that lag may run, not a rule of law or a policy finding.
DEPOSIT_GRACE_DAYS = 7
FIELDS = {
    "chart": ["account", "name", "type", "report_mapping", "effective_from"],
    "opening": ["record_id", "account", "balance_date", "debit", "credit"],
    "ledger": ["entry_id", "line_id", "date", "account", "debit", "credit"],
    "payroll": ["record_id", "employee_id", "service_start", "service_end", "pay_date", "gross", "deductions", "net", "employer_cost", "award_id", "award_amount"],
    "grants": ["award_id", "name", "ceiling", "valid_from", "valid_to"],
    "budget": ["record_id", "account", "amount", "approval_reference"],
    "invoice": ["record_id", "vendor_id", "invoice_number", "service_date", "amount"],
    "fees": ["record_id", "student_ref", "fee_type", "charge_date", "amount"],
    "collections": ["record_id", "collected_by", "collection_date", "method", "amount"],
    "deposits": ["record_id", "deposit_date", "bank_reference", "amount"],
    "sponsorships": ["record_id", "sponsor_id", "program", "pledge_date", "due_date", "amount"],
}
MONEY_FIELDS = {"debit", "credit", "gross", "deductions", "net", "employer_cost", "award_amount", "ceiling", "amount"}
DATE_FIELDS = {"date", "balance_date", "service_start", "service_end", "pay_date", "valid_from", "valid_to", "effective_from", "effective_to", "service_date",
               "charge_date", "collection_date", "deposit_date", "pledge_date", "due_date"}
OPTIONAL_FIELDS = ["currency", "school", "fund", "department", "award_id", "ledger_entry_id", "ledger_line_id", "effective_to", "po_id", "receipt_id",
                   "student_ref", "fee_record_id", "deposit_reference", "collection_reference", "program", "waiver_reference", "due_date"]


def fail(code: str, message: str, status: int = 422, **details):
    raise HTTPException(status, {"code": code, "message": message, "retryable": status == 409, **details})


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["synthetic", "public"] = "synthetic"
    entity_type: Literal["school", "district", "board", "university"] = "school"
    jurisdiction: str = Field(default="Unspecified", min_length=1, max_length=100)
    currency: Literal["USD", "CAD", "EUR", "GBP"] = "USD"
    start: date
    end: date
    scope: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def valid_scope(self):
        if not self.name.strip() or not self.scope.strip() or not self.jurisdiction.strip():
            raise ValueError("Name, scope and jurisdiction cannot be blank")
        if self.start > self.end:
            raise ValueError("Period start must not be after its end")
        if self.kind == "synthetic" and self.currency != "USD":
            raise ValueError("The current management accounting profile supports USD only; other currencies are public-document mode")
        return self


class FileOptions(BaseModel):
    role: Role = "document"
    source_system: str = Field(default="manual", min_length=1, max_length=100)
    source_version: int = Field(default=1, ge=1, le=1_000_000)
    external_id: str = Field(default="", max_length=200)
    applies_to: str = Field(default="", max_length=200)
    mapping: dict[str, str] = Field(default_factory=dict)
    amount_unit: Literal["major", "minor"] = "major"
    expected_rows: int | None = Field(default=None, ge=0, le=MAX_ROWS)
    expected_debit: str | None = Field(default=None, max_length=40)
    expected_credit: str | None = Field(default=None, max_length=40)
    excluded: bool = False
    exclusion_reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def valid_mapping(self):
        allowed = set(FIELDS.get(self.role, [])) | set(OPTIONAL_FIELDS)
        if any(k not in allowed or len(v) > 200 for k, v in self.mapping.items()):
            raise ValueError("Mapping contains an unsupported field")
        if self.excluded and not self.exclusion_reason.strip():
            raise ValueError("Excluded files require a reason")
        return self


class MappingUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    files: dict[str, FileOptions]


class CommitRequest(BaseModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class EvidenceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    role: Role = "service"
    task_id: str | None = Field(default=None, max_length=120)


class EvidenceResponse(BaseModel):
    source_id: str
    expected_version: int = Field(ge=1)


def workspace(connection, ws):
    row = connection.execute("SELECT * FROM workspaces WHERE id = ?", (ws,)).fetchone()
    if not row:
        fail("workspace_not_found", "Unknown intake workspace", 404)
    return {**json.loads(row["config"]), "id": ws, "revision": row["revision"]}


def create_workspace(body: WorkspaceCreate):
    config = body.model_dump(mode="json")
    config["name"] = config["name"].strip()
    config["profile"] = PROFILE if body.kind == "synthetic" else "PUBLIC_DOCUMENTS_ONLY"
    ws = db.uid("ws")
    with db.connect() as connection:
        connection.execute("INSERT INTO workspaces(id, config) VALUES (?, ?)", (ws, db.encode(config)))
        db.event(connection, ws, "workspace_created", config)
        return workspace(connection, ws)


def list_workspaces():
    with db.connect() as connection:
        return [workspace(connection, r["id"]) for r in connection.execute("SELECT id FROM workspaces ORDER BY rowid").fetchall()]


def load_batch(connection, ws, batch_id):
    workspace(connection, ws)
    row = connection.execute("SELECT * FROM batches WHERE ws = ? AND id = ?", (ws, batch_id)).fetchone()
    if not row:
        fail("batch_not_found", "Unknown import in this workspace", 404)
    return row


def iso_date(raw: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValueError("Dates must use YYYY-MM-DD")
    return date.fromisoformat(raw).isoformat()


def deposit_cutoff(period_end: str) -> str:
    return (date.fromisoformat(period_end) + timedelta(days=DEPOSIT_GRACE_DAYS)).isoformat()


def issue(code, message, source_id, locator=None, field=None):
    return {"code": code, "message": message, "source_id": source_id, "locator": locator, "field": field}


def parse_source(source, config):
    options = FileOptions.model_validate_json(source["options"])
    result = {"headers": [], "rows": [], "issues": [], "row_count": 0, "totals": {"debit_cents": 0, "credit_cents": 0}}
    if options.excluded:
        return result
    sid = source["id"]
    try:
        text = bytes(source["original"]).decode("utf-8-sig")
        if not text.strip() or any(ord(c) < 32 and c not in "\t\n\r" for c in text):
            raise ValueError("File must contain nonempty UTF-8 text without binary control characters")
        if source["name"].lower().endswith(".csv") and options.role not in DOCUMENT_ROLES:
            if config["kind"] == "public":
                raise ValueError("Public workspaces accept reference documents only, not ledger transactions")
            reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
            headers = reader.fieldnames or []
            if not headers or len(headers) > 100 or len(headers) != len(set(headers)):
                raise ValueError("CSV requires 1–100 unique column headers")
            result["headers"] = headers
            required = FIELDS[options.role]
            columns = {f: options.mapping.get(f, f) for f in required + OPTIONAL_FIELDS}
            missing = [f for f in required if columns[f] not in headers]
            if missing:
                result["issues"].append(issue("needs_mapping", "Map required columns: " + ", ".join(missing), sid))
                return result
            previous_line = reader.line_num
            for raw in reader:
                locator = previous_line + 1
                previous_line = reader.line_num
                result["row_count"] += 1
                if result["row_count"] > MAX_ROWS:
                    raise ValueError(f"CSV exceeds {MAX_ROWS:,} rows")
                if None in raw or any(v is None for v in raw.values()):
                    result["issues"].append(issue("row_shape", "Row has a different number of columns than its header", sid, locator))
                    continue
                values = {f: raw.get(c, "").strip() for f, c in columns.items() if c in raw}
                row_errors = []
                for f in required:
                    if not values.get(f):
                        row_errors.append(issue("required_field", "Required value is missing", sid, locator, f))
                payload = dict(values)
                for f, value in values.items():
                    try:
                        if f in MONEY_FIELDS:
                            payload.pop(f, None)
                            payload[f + "_cents"] = money(value, options.amount_unit)
                            if payload[f + "_cents"] < 0:
                                raise ValueError("Use nonnegative debit/credit sides and positive source amounts; reversals need explicit ledger lines")
                        elif f in DATE_FIELDS and value:
                            payload[f] = iso_date(value)
                    except ValueError as exc:
                        row_errors.append(issue("invalid_value", str(exc), sid, locator, f))
                currency = values.get("currency") or config["currency"]
                if currency != config["currency"]:
                    row_errors.append(issue("currency_mismatch", "Currency differs from this workspace", sid, locator, "currency"))
                payload["currency"] = currency
                if options.role in {"opening", "ledger"} and not row_errors:
                    d, c = payload["debit_cents"], payload["credit_cents"]
                    result["totals"]["debit_cents"] += d
                    result["totals"]["credit_cents"] += c
                    if (d == 0) == (c == 0):
                        row_errors.append(issue("journal_side", "Exactly one of debit or credit must be positive", sid, locator))
                if options.role == "ledger" and not row_errors:
                    if not config["start"] <= payload["date"] <= config["end"]:
                        row_errors.append(issue("period_mismatch", "Accounting date falls outside the selected period", sid, locator, "date"))
                if options.role == "opening" and not row_errors:
                    if payload["balance_date"] != config["start"]:
                        row_errors.append(issue("opening_date", "Opening balance date must equal the start of the period (before activity)", sid, locator))
                if options.role == "chart" and payload.get("type") not in {"asset", "liability", "equity", "revenue", "expense"}:
                    row_errors.append(issue("account_type", "Use asset, liability, equity, revenue or expense", sid, locator, "type"))
                for start, end in [("valid_from", "valid_to"), ("effective_from", "effective_to"), ("service_start", "service_end"), ("pledge_date", "due_date")]:
                    if payload.get(start) and payload.get(end) and payload[start] > payload[end]:
                        row_errors.append(issue("date_order", f"{start} must not be after {end}", sid, locator))
                if options.role == "payroll" and not row_errors:
                    if payload["gross_cents"] - payload["deductions_cents"] != payload["net_cents"]:
                        row_errors.append(issue("payroll_tie", "Gross minus deductions must equal net", sid, locator))
                    if payload["award_amount_cents"] > payload["gross_cents"] + payload["employer_cost_cents"]:
                        row_errors.append(issue("allocation_exceeds_cost", "Award allocation exceeds total payroll cost", sid, locator))
                    if payload["service_end"] < config["start"] or payload["service_start"] > config["end"]:
                        row_errors.append(issue("period_mismatch", "Payroll service period does not overlap workspace period", sid, locator))
                if options.role in MONEY_IN_ROLES and not row_errors:
                    if payload["amount_cents"] <= 0:
                        row_errors.append(issue("nonpositive_amount", "A charge, receipt, deposit or pledge of zero is a data error, not a record", sid, locator, "amount"))
                    # Cash movement is what the period bounds. A fee may be charged long before the review
                    # window opens and still be settled inside it, so charge_date stays unconstrained.
                    if payload.get("collection_date") and not config["start"] <= payload["collection_date"] <= config["end"]:
                        row_errors.append(issue("period_mismatch", "Cash movement date falls outside the selected period", sid, locator, "collection_date"))
                    # Refusing a deposit banked just after period end would withhold the record that answers an
                    # undeposited-cash difference, so the check reports a gap it created. Before the period opens
                    # is still an error: no deposit banks money that had not yet been received.
                    if payload.get("deposit_date") and not config["start"] <= payload["deposit_date"] <= deposit_cutoff(config["end"]):
                        row_errors.append(issue("period_mismatch", f"Deposit date falls outside the selected period and the {DEPOSIT_GRACE_DAYS}-day banking window supplied after it", sid, locator, "deposit_date"))
                result["issues"].extend(row_errors)
                if row_errors:
                    continue
                key = (payload["account"] if options.role == "chart" else payload["award_id"] if options.role == "grants"
                       else db.encode([payload["entry_id"], payload["line_id"]]) if options.role == "ledger"
                       else payload["record_id"])
                result["rows"].append({"key": key, "payload": payload, "locator": locator})
            if not result["row_count"]:
                raise ValueError("CSV has headers but no records")
            if options.expected_rows is not None and options.expected_rows != result["row_count"]:
                result["issues"].append(issue("control_count", "Source-stated row count does not match parsed rows", sid))
            for field in ("debit", "credit"):
                expected = getattr(options, "expected_" + field)
                if expected is not None and money(expected, options.amount_unit) != result["totals"][field + "_cents"]:
                    result["issues"].append(issue("control_total", f"Source-stated {field} total does not match parsed total", sid))
        elif options.role in DOCUMENT_ROLES:
            if len(text.splitlines()) > MAX_ROWS:
                raise ValueError(f"Document exceeds {MAX_ROWS:,} lines")
            result["row_count"] = len(text.splitlines())
            result["rows"] = [{"key": options.external_id or source["sha256"], "locator": 1,
                               "payload": {"sha256": source["sha256"], "applies_to": options.applies_to, "currency": config["currency"]}}]
        else:
            raise ValueError("Financial record roles require a CSV file")
    except (UnicodeDecodeError, ValueError, csv.Error) as exc:
        result["issues"].append(issue("parse_error", str(exc), sid))
        result["rows"] = []
    return result


def active_records(connection, ws):
    return [dict(r) | {"payload": json.loads(r["payload"])} for r in connection.execute(
        "SELECT * FROM records WHERE ws = ? AND active = 1", (ws,)
    ).fetchall()]


def candidate_records(connection, ws, files):
    current = {(r["role"], r["system"], r["record_key"]): r for r in active_records(connection, ws)}
    issues, additions = [], []
    seen = {}
    duplicates = 0
    for f in files:
        options = FileOptions.model_validate_json(f["options"])
        if options.excluded:
            continue
        parsed = json.loads(f["parsed"])
        issues.extend(parsed["issues"])
        for row in parsed["rows"]:
            key = (options.role, options.source_system, row["key"])
            full_key = key + (options.source_version,)
            candidate = {"id": db.uid("record"), "role": options.role, "system": options.source_system,
                         "record_key": row["key"], "version": options.source_version, "payload": row["payload"],
                         "source_id": f["id"], "locator": row["locator"], "previous": None}
            prior = connection.execute(
                "SELECT * FROM records WHERE ws=? AND role=? AND system=? AND record_key=? AND version=?",
                (ws, *full_key),
            ).fetchone()
            previous_payload = json.loads(prior["payload"]) if prior else seen.get(full_key)
            if previous_payload is not None:
                if previous_payload != row["payload"]:
                    issues.append(issue("record_conflict", "Same record ID/version has different values; provide a new version", f["id"], row["locator"]))
                else:
                    duplicates += 1
                continue
            if key in current:
                old = current[key]
                if options.source_version <= old["version"]:
                    issues.append(issue("stale_source_version", "Source version is older than the active record", f["id"], row["locator"]))
                    continue
                candidate["previous"] = {"version": old["version"], "payload": old["payload"], "source_id": old["source_id"]}
            seen[full_key] = row["payload"]
            current[key] = candidate
            additions.append(candidate)
    return list(current.values()), additions, issues, duplicates


def ledger_issues(records, config):
    issues = []
    accounts = {}
    for r in records:
        p = r["payload"]
        if r["role"] == "chart":
            if p["account"] in accounts:
                issues.append(issue("duplicate_account", "Account is defined by more than one source system", r["source_id"], r["locator"]))
            accounts[p["account"]] = p
    groups = {}
    ledger = [r for r in records if r["role"] == "ledger"]
    opening = [r for r in records if r["role"] == "opening"]
    for r in records:
        p = r["payload"]
        if r["role"] not in {"opening", "ledger", "budget"}:
            continue
        account = accounts.get(p["account"])
        effective = p.get("date") or p.get("balance_date") or config["start"]
        if not account:
            issues.append(issue("unknown_account", "Account is not in the accepted/staged chart", r["source_id"], r["locator"], "account"))
        elif effective < account["effective_from"] or (account.get("effective_to") and effective > account["effective_to"]):
            issues.append(issue("account_not_effective", "Account is not effective on this date", r["source_id"], r["locator"]))
        if r["role"] == "ledger":
            groups.setdefault((r["system"], p["entry_id"]), []).append(r)
    for rows in groups.values():
        if sum(r["payload"]["debit_cents"] - r["payload"]["credit_cents"] for r in rows):
            issues.append(issue("unbalanced_journal", "Journal is incomplete or unbalanced; no balancing entries will be invented", rows[0]["source_id"], rows[0]["locator"]))
        if len({r["payload"]["date"] for r in rows}) > 1:
            issues.append(issue("journal_dates", "All lines of a journal must share an accounting date", rows[0]["source_id"], rows[0]["locator"]))
    if opening and sum(r["payload"]["debit_cents"] - r["payload"]["credit_cents"] for r in opening):
        issues.append(issue("unbalanced_opening", "Opening trial balance does not balance", opening[0]["source_id"]))
    if ledger and not opening:
        issues.append(issue("missing_opening", "Upload a balanced opening trial balance before committing ledger activity", ledger[0]["source_id"]))
    return issues


def revalidate(connection, ws, batch_id):
    config = workspace(connection, ws)
    files = connection.execute("SELECT * FROM sources WHERE ws=? AND batch_id=? ORDER BY rowid", (ws, batch_id)).fetchall()
    for f in files:
        parsed = parse_source(f, config)
        connection.execute("UPDATE sources SET parsed=? WHERE id=?", (db.encode(parsed), f["id"]))
    files = connection.execute("SELECT * FROM sources WHERE ws=? AND batch_id=? ORDER BY rowid", (ws, batch_id)).fetchall()
    current, additions, issues, duplicates = candidate_records(connection, ws, files)
    issues += ledger_issues(current, config)
    included = [f for f in files if not json.loads(f["options"])["excluded"]]
    if not included:
        issues.append(issue("empty_batch", "Select at least one file to import", "batch"))
    counts = {"parsed": sum(json.loads(f["parsed"])["row_count"] for f in included),
              "valid_records": sum(len(json.loads(f["parsed"])["rows"]) for f in included),
              "new_records": len(additions), "duplicate_records": duplicates, "issues": len(issues)}
    totals = {k: sum(json.loads(f["parsed"])["totals"][k] for f in included) for k in ["debit_cents", "credit_cents"]}
    status = "needs_mapping" if any(i["code"] == "needs_mapping" for i in issues) else "needs_review" if issues else "ready_to_commit"
    result = {"counts": counts, "totals": totals, "issues": issues[:500], "issues_truncated": len(issues) > 500,
              "changes": [{"record_key": r["record_key"], "role": r["role"], "previous": r["previous"], "next": r["payload"]} for r in additions if r["previous"]][:100],
              "coverage_note": "Counts describe supplied records. Completeness of the institution's books is not independently verified."}
    connection.execute("UPDATE batches SET status=?, base_revision=?, result=? WHERE id=?",
                       (status, config["revision"], db.encode(result), batch_id))


def stage(ws, uploads: list[tuple[str, bytes, FileOptions]]):
    with db.connect() as connection:
        return stage_in_transaction(connection, ws, uploads)


def stage_in_transaction(connection, ws, uploads):
    if not 1 <= len(uploads) <= MAX_FILES or sum(len(b) for _, b, _ in uploads) > MAX_BATCH:
        fail("batch_limit", "Upload 1–20 files with a combined size of at most 50 MB", 413)
    config = workspace(connection, ws)
    bid = db.uid("import")
    connection.execute("INSERT INTO batches(id,ws,status,base_revision,created_at) VALUES(?,?,?,?,?)",
                       (bid, ws, "parsing", config["revision"], db.now()))
    for name, content, options in uploads:
        if not name or len(name) > 200 or "/" in name or "\\" in name or any(ord(c) < 32 for c in name):
            fail("invalid_filename", "Use a simple filename without directories or control characters")
        if PurePath(name).suffix.lower() not in {".csv", ".txt", ".md"}:
            fail("unsupported_format", "This intake accepts CSV/TXT/Markdown. Use the Document lab for PDF/image extraction.", 415)
        if not content or len(content) > MAX_FILE:
            fail("file_limit", "Each file must be nonempty and at most 10 MB", 413)
        connection.execute(
            "INSERT INTO sources(id,ws,batch_id,name,sha256,original,options) VALUES(?,?,?,?,?,?,?)",
            (db.uid("source"), ws, bid, name, hashlib.sha256(content).hexdigest(), content, options.model_dump_json()),
        )
    revalidate(connection, ws, bid)
    db.event(connection, ws, "import_staged", {"batch_id": bid})
    return batch_view(connection, ws, bid)


def batch_view(connection, ws, bid):
    row = load_batch(connection, ws, bid)
    files = []
    for f in connection.execute("SELECT * FROM sources WHERE ws=? AND batch_id=? ORDER BY rowid", (ws, bid)):
        parsed = json.loads(f["parsed"])
        duplicate = connection.execute("SELECT id FROM sources WHERE ws=? AND sha256=? AND committed=1 AND id!=? LIMIT 1",
                                       (ws, f["sha256"], f["id"])).fetchone()
        files.append({"id": f["id"], "name": f["name"], "sha256": f["sha256"], "options": json.loads(f["options"]),
                      "headers": parsed.get("headers", []), "required_fields": FIELDS.get(json.loads(f["options"])["role"], []),
                      "row_count": parsed.get("row_count", 0), "preview": parsed.get("rows", [])[:8],
                      "totals": parsed.get("totals", {}), "duplicate_of": duplicate["id"] if duplicate else None})
    return {"id": bid, "workspace_id": ws, "status": row["status"], "version": row["version"],
            "base_revision": row["base_revision"], "created_at": row["created_at"], "snapshot_id": row["snapshot_id"],
            "files": files, **json.loads(row["result"])}


def get_batch(ws, bid):
    with db.connect() as connection:
        return batch_view(connection, ws, bid)


def list_batches(ws):
    with db.connect() as connection:
        workspace(connection, ws)
        return [dict(r) for r in connection.execute(
            "SELECT id,status,version,created_at,snapshot_id FROM batches WHERE ws=? ORDER BY rowid DESC LIMIT 100", (ws,)
        )]


def update_mapping(ws, bid, body: MappingUpdate):
    with db.connect() as connection:
        batch = load_batch(connection, ws, bid)
        if batch["status"] == "committed" or batch["version"] != body.expected_version:
            fail("stale_preview", "This preview changed or was already committed; refresh it", 409)
        for sid, options in body.files.items():
            changed = connection.execute("UPDATE sources SET options=? WHERE id=? AND ws=? AND batch_id=?",
                                         (options.model_dump_json(), sid, ws, bid))
            if not changed.rowcount:
                fail("source_not_found", "Source does not belong to this import", 404)
        connection.execute("UPDATE batches SET version=version+1 WHERE id=?", (bid,))
        revalidate(connection, ws, bid)
        db.event(connection, ws, "mapping_reviewed", {"batch_id": bid, "previous_version": body.expected_version})
    return get_batch(ws, bid)


def commit(ws, bid, body: CommitRequest):
    with db.connect() as connection:
        batch = load_batch(connection, ws, bid)
        saved = json.loads(batch["result"])
        if batch["status"] == "committed":
            if saved.get("idempotency_key") != body.idempotency_key:
                fail("already_committed", "Import already committed; retrieve the saved result", 409)
            return batch_view(connection, ws, bid)
        config = workspace(connection, ws)
        if body.expected_version != batch["version"] or config["revision"] != batch["base_revision"]:
            fail("stale_preview", "Workspace or mappings changed. Revalidate the preview before committing.", 409)
        if batch["status"] != "ready_to_commit":
            fail("validation_blocked", "Resolve or explicitly exclude invalid files before committing", 409)
        # Corrections can change after a document-derived preview was staged.
        # Never commit a stale transcription or superseded review as current facts.
        from . import extraction
        for staged in extraction.items(connection, ws, "staging"):
            if staged["batch_id"] == bid:
                correction = extraction.get(connection, ws, staged["correction_id"], "correction")
                document = extraction.document(connection, ws, correction["document_id"])
                latest = [x for x in extraction.items(connection, ws, "correction") if x["document_id"] == document["id"]][-1]
                if latest["id"] != correction["id"] or correction["text_sha256"] != document["text_sha256"]:
                    fail("stale_extraction", "Extraction correction changed; stage the latest reviewed version", 409)
        files = connection.execute("SELECT * FROM sources WHERE ws=? AND batch_id=?", (ws, bid)).fetchall()
        current, additions, issues, _ = candidate_records(connection, ws, files)
        issues += ledger_issues(current, config)
        if issues:
            fail("validation_blocked", "Current records no longer pass validation", 409, issues=issues[:20])
        for r in additions:
            connection.execute("UPDATE records SET active=0 WHERE ws=? AND role=? AND system=? AND record_key=?",
                               (ws, r["role"], r["system"], r["record_key"]))
            connection.execute("INSERT INTO records(id,ws,role,system,record_key,version,payload,source_id,locator) VALUES(?,?,?,?,?,?,?,?,?)",
                               (r["id"], ws, r["role"], r["system"], r["record_key"], r["version"], db.encode(r["payload"]), r["source_id"], r["locator"]))
        for f in files:
            if not json.loads(f["options"])["excluded"]:
                connection.execute("UPDATE sources SET committed=1 WHERE id=?", (f["id"],))
        # Duplicate-only imports preserve financial revision and snapshot.
        latest = connection.execute("SELECT id FROM snapshots WHERE ws=? ORDER BY revision DESC LIMIT 1", (ws,)).fetchone()
        snapshot_id = latest["id"] if latest else None
        if additions:
            revision = config["revision"] + 1
            snapshot_id = db.uid("snapshot")
            manifest = {"record_ids": [r["id"] for r in active_records(connection, ws)],
                        "source_ids": sorted({r["source_id"] for r in active_records(connection, ws)}),
                        "profile": config["profile"], "scope": config["scope"], "period": [config["start"], config["end"]]}
            connection.execute("UPDATE snapshots SET stale=1 WHERE ws=?", (ws,))
            connection.execute("INSERT INTO snapshots(id,ws,revision,created_at,manifest) VALUES(?,?,?,?,?)",
                               (snapshot_id, ws, revision, db.now(), db.encode(manifest)))
            connection.execute("UPDATE workspaces SET revision=? WHERE id=?", (revision, ws))
            # Supplied evidence requires re-review when its active source is superseded.
            active_sources = set(manifest["source_ids"])
            for request in connection.execute("SELECT * FROM evidence_requests WHERE ws=? AND status='supplied'", (ws,)).fetchall():
                if request["source_id"] not in active_sources:
                    connection.execute("UPDATE evidence_requests SET status='needs_review',version=version+1 WHERE id=?", (request["id"],))
            db.event(connection, ws, "snapshot_published", {"snapshot_id": snapshot_id, "revision": revision,
                                                        "invalidates_previous": bool(latest), "new_records": len(additions)})
        saved["idempotency_key"] = body.idempotency_key
        connection.execute("UPDATE batches SET status='committed',snapshot_id=?,result=? WHERE id=?",
                           (snapshot_id, db.encode(saved), bid))
        db.event(connection, ws, "import_committed", {"batch_id": bid, "snapshot_id": snapshot_id, "version": batch["version"]})
        return batch_view(connection, ws, bid)


def source_view(ws, sid, start=1, limit=100):
    with db.connect() as connection:
        workspace(connection, ws)
        source = connection.execute("SELECT * FROM sources WHERE ws=? AND id=?", (ws, sid)).fetchone()
        if not source:
            fail("source_not_found", "Source not found in this workspace", 404)
        try:
            lines = bytes(source["original"]).decode("utf-8-sig").splitlines()
        except UnicodeDecodeError:
            lines = ["[Not readable UTF-8; original preserved for download]"]
        origin = None
        from . import extraction
        for staged in extraction.items(connection, ws, "staging"):
            if staged["batch_id"] == source["batch_id"]:
                corrected = extraction.get(connection, ws, staged["correction_id"], "correction")
                doc = extraction.document(connection, ws, staged["document_id"])
                origin = {"document_id": doc["id"], "name": doc["name"], "sha256": doc["sha256"],
                          "correction_id": corrected["id"], "has_images": doc["suffix"] not in {".txt", ".md"},
                          "pages": sorted({v["page"] for r in corrected["output"]["records"] for v in r.values() if v["status"] == "present"})}
        return {"id": sid, "name": source["name"], "sha256": source["sha256"],
                "extraction_origin": origin,
                "committed": bool(source["committed"]), "options": json.loads(source["options"]),
                "line_count": len(lines), "lines": [{"number": i + 1, "text": line} for i, line in enumerate(lines) if start <= i + 1 < start + limit]}


def source_bytes(ws, sid):
    with db.connect() as connection:
        workspace(connection, ws)
        source = connection.execute("SELECT name,original FROM sources WHERE ws=? AND id=?", (ws, sid)).fetchone()
        if not source:
            fail("source_not_found", "Source not found in this workspace", 404)
        return source["name"], bytes(source["original"])


def coverage(ws):
    with db.connect() as connection:
        config = workspace(connection, ws)
        records = active_records(connection, ws)
        roles = {r["role"] for r in records}
        counts = {role: sum(r["role"] == role for r in records) for role in FIELDS | dict.fromkeys(DOCUMENT_ROLES)}
        docs = roles & DOCUMENT_ROLES
        capabilities = []
        for key, label, required in [
            ("document_explanation", "Document evidence available", set()),
            ("transaction_investigation", "Ledger available for investigation", {"chart", "opening", "ledger"}),
            ("payroll_allocation_confirmation", "Payroll / grant evidence", {"payroll", "grants", "policy", "service"}),
            ("management_statements", "Management statements", {"chart", "opening", "ledger"}),
            ("budget_variance", "Budget versus actual", {"chart", "opening", "ledger", "budget"}),
            ("collections_reconciliation", "Collections reconciled to deposits", {"collections", "deposits"}),
        ]:
            missing = sorted(required - roles)
            if key == "document_explanation":
                missing = [] if docs else ["document"]
            status = "missing" if missing else "ready_for_scope"
            note = "Available for a bounded investigation; completeness of the full institution is unverified."
            if key in {"management_statements", "budget_variance"}:
                status = "missing" if missing else "needs_review"
                note = "Input presence is not statement readiness. Full coverage review and report calculation are not implemented."
            if key == "payroll_allocation_confirmation" and not missing:
                status = "needs_review"
                note = "Documents are supplied, not independently verified. Auditor review and allocation calculation are still required."
            if key == "collections_reconciliation" and not missing:
                status = "needs_review"
                note = "Receipts and deposits are supplied records, not a verified complete set. A difference between them is unreconciled, not evidence of loss."
            if config["kind"] == "public" and key != "document_explanation":
                status, note = "unsupported", "Public-document workspace; no transaction accounting."
            # `requires` is the same set the status is computed from. It is published
            # so a client can draw what a check depends on without re-declaring the
            # requirements and drifting from them.
            capabilities.append({"id": key, "label": label, "status": status, "missing": missing,
                                 "note": note, "requires": sorted(required)})
        sources = []
        active_ids = {r["source_id"] for r in records}
        for f in connection.execute("SELECT id,name,sha256,options,committed FROM sources WHERE ws=? AND committed=1 ORDER BY rowid DESC", (ws,)):
            sources.append({"id": f["id"], "name": f["name"], "sha256": f["sha256"],
                            "role": json.loads(f["options"])["role"], "active": f["id"] in active_ids})
        requests = [dict(r) for r in connection.execute("SELECT * FROM evidence_requests WHERE ws=? ORDER BY rowid DESC", (ws,))]
        latest = connection.execute("SELECT id,revision,created_at FROM snapshots WHERE ws=? ORDER BY revision DESC LIMIT 1", (ws,)).fetchone()
        return {"workspace": config, "snapshot": dict(latest) if latest else None, "counts": counts,
                "capabilities": capabilities, "sources": sources, "requests": requests,
                "coverage_verified": False, "note": "Coverage is limited to supplied records; no audit opinion or full-population completeness is implied."}


def financial_records(ws):
    """Active committed records, for the deterministic accounting engine only.

    Read-only projection: role, business key, parsed payload and the source the
    record came from. Callers get the records, never the connection, so SQL and
    original bytes stay inside this module.
    """
    with db.connect() as connection:
        workspace(connection, ws)
        records = active_records(connection, ws)
        return {
            "records": [{"role": r["role"], "record_key": r["record_key"], "payload": r["payload"],
                         "source_id": r["source_id"], "locator": r["locator"]} for r in records],
            "roles": sorted({r["role"] for r in records}),
        }


def create_evidence_request(ws, body: EvidenceCreate):
    with db.connect() as connection:
        workspace(connection, ws)
        rid = db.uid("request")
        connection.execute("INSERT INTO evidence_requests(id,ws,title,role,task_id) VALUES(?,?,?,?,?)",
                           (rid, ws, body.title, body.role, body.task_id))
        db.event(connection, ws, "evidence_requested", {"request_id": rid, **body.model_dump()})
    return coverage(ws)


def respond(ws, rid, body: EvidenceResponse):
    with db.connect() as connection:
        workspace(connection, ws)
        request = connection.execute("SELECT * FROM evidence_requests WHERE ws=? AND id=?", (ws, rid)).fetchone()
        if not request:
            fail("request_not_found", "Unknown evidence request", 404)
        if request["version"] != body.expected_version:
            fail("stale_request", "This evidence request has changed; refresh it", 409)
        source = connection.execute("SELECT * FROM sources WHERE ws=? AND id=? AND committed=1", (ws, body.source_id)).fetchone()
        active = connection.execute("SELECT 1 FROM records WHERE ws=? AND source_id=? AND active=1", (ws, body.source_id)).fetchone()
        if not source or not active or json.loads(source["options"])["role"] != request["role"]:
            fail("evidence_not_ready", "Attach an active, committed source with the requested role")
        snapshot = connection.execute("SELECT id FROM snapshots WHERE ws=? ORDER BY revision DESC LIMIT 1", (ws,)).fetchone()
        connection.execute("UPDATE evidence_requests SET status='supplied',source_id=?,snapshot_id=?,version=version+1 WHERE id=?",
                           (body.source_id, snapshot["id"], rid))
        db.event(connection, ws, "evidence_supplied", {"request_id": rid, "task_id": request["task_id"],
                                                    "source_id": body.source_id, "snapshot_id": snapshot["id"],
                                                    "next_action": "review_evidence_then_resume", "agent_runtime_available": False})
    return coverage(ws)
