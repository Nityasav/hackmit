"""Everything a finished document needs, gathered once, computed in one place.

A deliverable is not a new analysis. It is the period's existing figures arranged for
someone who was not in the room, so this endpoint recomputes nothing that the accounting
modules already own — it calls them and returns what they say.

## Why this is a single endpoint

A one-page snapshot that fetched statements from one route, the close from another and
controls from a third would be assembling a document out of four reads taken at four
moments. Between the first and the last, a commit can land. The figures would each be
true and the page as a whole would be of no particular period.

So: one read, one snapshot id, one `prepared_at`. If the books move, the next fetch says
so, and the document a person is looking at is still internally consistent.

## No model touches any of this

Every number here comes from `accounting/`, in integer cents. The renderer formats them
and writes nothing. That is what makes a PDF from this safe to hand to a board: the
figures on it were derived, and the same inputs give the same page.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import db, ingestion, roles as role_registry
from .accounting import accruals, close, controls, reconcile, statements, variance

router = APIRouter(prefix="/api/workspaces/{ws}", tags=["Deliverables"])

#: How many exceptions and variance lines a one-page document can carry before it stops
#: being one page. The rest are counted, never silently dropped.
PAGE_LIMIT = 6

#: What can be asked for, and what each is called once it exists.
KINDS = {
    "one_pager": "One-page snapshot",
    "deck": "Board deck",
}

#: Phrases that name a kind. Matched rather than inferred by a model, for the same
#: reason the orchestrator routes on keywords: this is a choice between two known
#: options, and a model call buys nothing here but latency and a way to be wrong.
#: Longest phrases first, so "one page summary" is not caught by "summary".
_ASKS: tuple[tuple[str, str], ...] = (
    # Anything that names slides is a deck, however it is counted or spelled. "Make a
    # 2 slide report" asked for slides and got nothing, because the list held "slides"
    # and not "slide" — a vocabulary that narrow is a vocabulary that mostly says no.
    ("slide deck", "deck"), ("slideshow", "deck"), ("slide show", "deck"),
    ("slides", "deck"), ("slide", "deck"), ("deck", "deck"),
    ("presentation", "deck"), ("board pack", "deck"), ("powerpoint", "deck"),

    ("one-pager", "one_pager"), ("one pager", "one_pager"),
    ("one-page", "one_pager"), ("one page", "one_pager"),
    ("1-pager", "one_pager"), ("1 pager", "one_pager"),
    ("snapshot", "one_pager"), ("summary sheet", "one_pager"),
    ("write up", "one_pager"), ("briefing", "one_pager"),
    ("report", "one_pager"), ("summary", "one_pager"), ("pdf", "one_pager"),
    ("page", "one_pager"), ("pager", "one_pager"),
    # A kind nobody named. Asking for "a deliverable" is asking for the default one
    # rather than for nothing, and refusing on a technicality helps no one.
    ("deliverable", "one_pager"), ("document", "one_pager"), ("handout", "one_pager"),
)

#: A kind named without any of these is a mention, not a request. "The one-pager was
#: wrong" should not silently produce a second one-pager, and this is what carries most
#: of the weight now that the vocabulary above is broad: "report on the payables" names
#: a kind and asks for nothing.
_VERBS = ("make", "create", "build", "generate", "produce", "prepare", "draft",
          "give me", "i want", "i need", "can you do", "put together", "assemble",
          "export", "write me", "send me", "turn this into", "turn that into",
          "let me have", "i'd like", "id like", "could you do", "hand me", "save as")


#: Counts people put in front of a kind. "A 2 slide report" and "a two slide report"
#: are the same request, and a vocabulary that reads one and not the other is a
#: vocabulary that mostly says no. The number itself is not honoured — a deck has the
#: slides its content needs — so it is removed rather than parsed.
_COUNTS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
           "a couple of", "a few", "several", "single", "short", "brief", "quick")


def _normalised(message: str) -> str:
    """The sentence with counts and punctuation flattened, for matching only.

    Digits become spaces and written counts are dropped, so "1 page", "2-slide" and "a
    few slides" all reduce to the kind being asked for. Nothing here changes what is
    produced; it only decides what the person meant.
    """
    text = (message or "").lower()
    text = "".join(" " if character.isdigit() else character for character in text)
    for separator in ("-", "/", ",", ".", "!", "?", ";", ":"):
        text = text.replace(separator, " ")
    for count in _COUNTS:
        text = text.replace(f" {count} ", " ")
    return " " + " ".join(text.split()) + " "


def requested(message: str) -> str | None:
    """Which deliverable this sentence asks for, or None.

    None is the common case and the important one. A person asking a question about
    their books has not asked for a document, and producing one anyway fills a screen
    with artifacts nobody wanted and makes the ones they did want harder to find.
    """
    text = _normalised(message)
    kind = next((k for phrase, k in _ASKS if f" {phrase} " in text
                 or phrase in text.replace(" ", "")), None)
    if kind is None:
        return None
    return kind if any(verb in text for verb in _VERBS) else None


def figures_for(ws: str) -> dict:
    """Everything any deliverable draws on: result, position, close, exceptions, drivers.

    Deterministic and free. Nothing here calls a model, so the same books give the same
    document every time — which is what makes freezing one at a moment meaningful rather
    than arbitrary.
    """
    config = ingestion.workspace_config(ws)
    records = ingestion.financial_records(ws)["records"]
    coverage = ingestion.coverage(ws)

    figures = statements.statements(records, config)
    checklist = close.checklist(records, config)
    found = controls.checks(records, config)
    exceptions = [c for c in found if c["status"] == "attention"]
    passes = [c for c in found if c["status"] == "pass"]
    gaps = [c for c in found if c["status"] == "gap"]
    against_plan = variance.budget_vs_actual(records, config)
    accrual = accruals.unbilled_receipts(records, config)
    bank = (reconcile.reconcile_bank(records, config)["totals"]
            if any(r["role"] == "bank_transactions" for r in records) else None)

    drivers = [line for line in against_plan["lines"] if line["variance_cents"]]

    return {
        "workspace": {
            "name": config.get("name", ""),
            "start": config.get("start", ""),
            "end": config.get("end", ""),
            "period": str(config.get("start", ""))[:7],
            "jurisdiction": config.get("jurisdiction", ""),
            "currency": config.get("currency", "USD"),
        },
        # One read, one moment. A document assembled from four fetches is a document of
        # no particular period.
        "snapshot_id": coverage.get("snapshot", {}).get("id") if coverage.get("snapshot") else None,
        "prepared_at": db.now(),
        "records": len(records),
        "result": {
            "revenue_cents": figures["income_statement"]["total_revenue_cents"],
            "expense_cents": figures["income_statement"]["total_expense_cents"],
            "net_cents": figures["income_statement"]["net_income_cents"],
            "expense_by_category_cents": figures["income_statement"]["expense_by_category_cents"],
        },
        "position": {
            "assets_cents": figures["balance_sheet"]["total_assets_cents"],
            "liabilities_cents": figures["balance_sheet"]["total_liabilities_cents"],
            "equity_cents": figures["balance_sheet"]["total_equity_cents"],
            "opening_cash_cents": figures["cash_flow"]["opening_cash_cents"],
            "closing_cash_cents": figures["cash_flow"]["closing_cash_cents"],
        },
        # The three identities that decide whether any of the above may be shown at all.
        "checks": {
            "trial_balance_balances": figures["trial_balance"]["balances"],
            "balance_sheet_balances": figures["balance_sheet"]["balances"],
            "balance_sheet_difference_cents": figures["balance_sheet"]["difference_cents"],
            "cash_flow_ties": figures["cash_flow"]["ties"],
            "reliable": figures["reliable"],
            "problems": figures["problems"],
        },
        "close": {
            "ready": checklist["ready"],
            "blocked_by": checklist["blocked_by"],
            "counts": checklist.get("counts", {}),
            "items": checklist["items"],
        },
        "controls": {
            "exceptions": [
                {"id": c["id"], "title": c["title"], "amount_cents": c["amount_cents"],
                 # Readable, because a composite key printed raw reads as `PO-70081` —
                 # a document number that does not exist. On a page someone hands to a
                 # board, that is worse than showing nothing.
                 "records": [role_registry.readable_key(c["role"], k)
                             for k in c["record_keys"]],
                 "action": c["action"]}
                for c in exceptions[:PAGE_LIMIT]],
            "exception_count": len(exceptions),
            # Named, not just counted. "Six tests passed" is a finding; silence is not.
            "passed": [c["title"] for c in passes],
            "pass_count": len(passes),
            "gap_count": len(gaps),
            "omitted": max(0, len(exceptions) - PAGE_LIMIT),
        },
        "variance": {
            "lines": drivers[:PAGE_LIMIT],
            "line_count": len(drivers),
            "omitted": max(0, len(drivers) - PAGE_LIMIT),
            "expense_planned_cents": against_plan["totals"]["expense"]["planned_cents"],
            "expense_actual_cents": against_plan["totals"]["expense"]["actual_cents"],
            "unplanned": against_plan["unplanned"],
        },
        "accruals": {
            "count": len(accrual["proposals"]),
            "total_cents": accrual["total_cents"],
        },
        "bank": bank,
        "limitations": [
            "Prepared from the records supplied for this period. Not an audit opinion, "
            "and not a statement that the population is complete.",
            "Exceptions are questions raised by rules-based tests. A duplicate candidate "
            "is not a duplicate payment, and amounts from different tests may overlap.",
            "Every figure was computed from the ledger in exact cents. No figure on this "
            "page was written by a language model.",
        ],
    }


class Request(BaseModel):
    kind: str = Field(min_length=1, max_length=40)
    #: The sentence that asked for it, kept so a document can say why it exists.
    requested_by: str = Field(default="", max_length=2000)
    thread_id: str = Field(default="", max_length=100)


def create(ws: str, kind: str, *, requested_by: str = "", thread_id: str = "") -> dict:
    """Build one deliverable and freeze it.

    The figures are stored, not a pointer to recompute them. A document is of a moment:
    regenerating it next week from the same title gives a different document, and two of
    those saying different things is exactly what a dated, filed report exists to avoid.
    """
    if kind not in KINDS:
        raise HTTPException(422, f"No such deliverable: {kind!r}. "
                                 f"Available: {', '.join(sorted(KINDS))}.")
    payload = figures_for(ws)
    if not payload["records"]:
        raise HTTPException(409, "There are no committed records to report on. Commit "
                                 "this company's books first.")
    row = {
        "id": db.uid("doc"),
        "kind": kind,
        "title": f"{KINDS[kind]} · {payload['workspace']['period']}",
        "requested_by": requested_by,
        "thread_id": thread_id,
        "snapshot_id": payload["snapshot_id"],
        "created_at": db.now(),
    }
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO deliverables (id, ws, kind, title, requested_by, thread_id,"
            " payload, snapshot_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (row["id"], ws, kind, row["title"], requested_by, thread_id,
             db.encode(payload), row["snapshot_id"], row["created_at"]))
    return row | {"payload": payload}


@router.post("/deliverables", status_code=201)
def make(ws: str, body: Request):
    """Produce a deliverable. Free and instant: no model is called."""
    ingestion.workspace_config(ws)
    return create(ws, body.kind, requested_by=body.requested_by, thread_id=body.thread_id)


@router.get("/deliverables")
def listing(ws: str, limit: int = 50):
    """What has been produced for this company, newest first.

    Nothing is produced on its own. An empty list means nobody asked for anything, which
    is a different statement from having nothing to say.
    """
    ingestion.workspace_config(ws)
    current = ingestion.coverage(ws).get("snapshot") or {}
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT id, kind, title, requested_by, thread_id, snapshot_id, created_at"
            " FROM deliverables WHERE ws=? ORDER BY rowid DESC LIMIT ?",
            (ws, min(limit, 200))).fetchall()
    return {
        "deliverables": [
            dict(row) | {
                # A document drawn from records that have since been superseded is not
                # wrong, it is historical — and saying which is the reader's business.
                "stale": bool(current.get("id")) and row["snapshot_id"] != current["id"],
                "kind_label": KINDS.get(row["kind"], row["kind"]),
            } for row in rows],
        "kinds": [{"id": k, "label": v} for k, v in sorted(KINDS.items())],
        "note": "Nothing is produced unless it was asked for. An empty list means nobody "
                "asked, not that there is nothing to report.",
    }


@router.get("/deliverables/{document_id}")
def read(ws: str, document_id: str):
    """One deliverable, exactly as it was when it was made."""
    ingestion.workspace_config(ws)
    current = ingestion.coverage(ws).get("snapshot") or {}
    with db.connect() as connection:
        row = connection.execute(
            "SELECT * FROM deliverables WHERE ws=? AND id=?", (ws, document_id)).fetchone()
    if row is None:
        raise HTTPException(404, "No such deliverable in this company.")
    return {
        "id": row["id"], "kind": row["kind"], "kind_label": KINDS.get(row["kind"], row["kind"]),
        "title": row["title"], "requested_by": row["requested_by"],
        "thread_id": row["thread_id"], "snapshot_id": row["snapshot_id"],
        "created_at": row["created_at"],
        "stale": bool(current.get("id")) and row["snapshot_id"] != current["id"],
        # Frozen at creation. Deliberately not recomputed on read: a document that
        # changes when you reopen it is not a document.
        "payload": json.loads(row["payload"]),
    }
