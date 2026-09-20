"""Economic events: Invariant 1, made real at commit time.

A vendor invoice, the order behind it, the receipt that proves delivery, the payment that
settles it, the bank line it cleared on and the journal entries for all of it are six
views of **one thing that happened**. This module is where that thing gets an identity.

Materialization runs inside the commit transaction, so an event exists exactly when the
records that constitute it do. Nothing is inferred by an agent and nothing is guessed
from amounts and dates: the grouping comes from `event_ref`, a column the source
supplies, and records that carry none simply have no event — reference data like a chart
of accounts or a vendor list is not something that *happened*.

Why grouping is not matching: matching decides whether an invoice and an order belong
together on the evidence, and that judgment lives in `accounting/match.py` with a
confidence attached. Grouping is bookkeeping. Conflating them would let a weak match
silently become an identity, which is the one thing the event id must never be.
"""

from __future__ import annotations

from collections import defaultdict

from . import db

#: Which record role decides what kind of event this is, most specific first. A group
#: holding both an invoice and a payment is still a purchase; the payment is part of it.
KIND_BY_ROLE: tuple[tuple[str, str], ...] = (
    ("processor_payouts", "processor_payout"),
    ("payroll", "payroll"),
    ("vendor_invoices", "purchase"),
    ("customer_invoices", "sale"),
    ("expenses", "expense"),
    ("payments", "payment"),
    ("remittances", "receipt"),
    ("bank_transactions", "bank_movement"),
    ("ledger", "journal"),
)

#: The date field that best describes when each kind of record happened.
DATE_BY_ROLE: dict[str, str] = {
    "vendor_invoices": "invoice_date", "customer_invoices": "invoice_date",
    "purchase_orders": "order_date", "goods_receipts": "received_date",
    "payments": "payment_date", "remittances": "received_date",
    "bank_transactions": "settlement_date", "processor_payouts": "payout_date",
    "payroll": "pay_date", "expenses": "expense_date", "ledger": "date",
    "approvals": "approved_at",
}

#: Roles that describe the thing that happened, rather than a consequence of it. A
#: title should name the obligation, not the bank line that settled it.
TITLE_PRIORITY = ("vendor_invoices", "customer_invoices", "processor_payouts",
                  "payroll", "expenses", "payments", "remittances")


def _kind(roles: set[str]) -> str:
    for role, kind in KIND_BY_ROLE:
        if role in roles:
            return kind
    return "other"


def _occurred_on(records: list[dict], fallback: str) -> str:
    """The earliest date any record in the group carries.

    Earliest, not latest: an event happens when the obligation arises, and the payment
    that settles it weeks later is part of the same event rather than a new one.
    """
    dates = [record["payload"].get(DATE_BY_ROLE.get(record["role"], ""), "")
             for record in records]
    supplied = sorted(d for d in dates if d)
    return supplied[0] if supplied else fallback


def _title(records: list[dict]) -> str:
    by_role = {record["role"]: record for record in records}
    for role in TITLE_PRIORITY:
        record = by_role.get(role)
        if not record:
            continue
        payload = record["payload"]
        who = payload.get("vendor_id") or payload.get("customer_id") or payload.get("employee_id", "")
        what = (payload.get("invoice_number") or payload.get("processor")
                or payload.get("category") or role.replace("_", " "))
        return f"{what} · {who}".strip(" ·") or role
    return sorted(by_role)[0].replace("_", " ") if by_role else "Unattributed records"


def materialize(connection, ws: str, fallback_date: str) -> dict:
    """Create the events this workspace's committed records describe, and link them.

    Idempotent: an event already recorded keeps its identity and its created_at, so
    re-committing or adding a later record to an existing event neither duplicates it
    nor rewrites its history. Only the record's own `event_id` is (re)set.
    """
    rows = connection.execute(
        "SELECT id, role, record_key, payload, event_id FROM records WHERE ws=? AND active=1",
        (ws,)).fetchall()

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        import json
        payload = json.loads(row["payload"])
        reference = (payload.get("event_ref") or "").strip()
        if reference:
            grouped[reference].append(
                {"id": row["id"], "role": row["role"], "payload": payload})

    known = {row["id"] for row in
             connection.execute("SELECT id FROM economic_events WHERE ws=?", (ws,))}
    created = 0
    for reference, members in sorted(grouped.items()):
        # The source's own reference is the identity, so the same event keeps the same
        # id across imports and periods. A generated id would mint a new event every
        # time a later record arrived for one that already exists.
        event_id = reference
        roles = {member["role"] for member in members}
        occurred = _occurred_on(members, fallback_date)
        if event_id not in known:
            connection.execute(
                "INSERT INTO economic_events (id, ws, kind, title, occurred_on, period,"
                " status, created_at, created_by) VALUES (?,?,?,?,?,?,'open',?,'intake')",
                (event_id, ws, _kind(roles), _title(members), occurred, occurred[:7], db.now()))
            created += 1
        connection.executemany(
            "UPDATE records SET event_id=? WHERE id=?",
            [(event_id, member["id"]) for member in members])

    return {"events": len(grouped), "created": created,
            "records_linked": sum(len(m) for m in grouped.values())}


def view(connection, ws: str, event_id: str) -> dict | None:
    """One event and everything that carries its id.

    The query Invariant 1 exists to make possible: given any artifact, what else in the
    business is the same transaction?
    """
    import json

    event = connection.execute(
        "SELECT * FROM economic_events WHERE ws=? AND id=?", (ws, event_id)).fetchone()
    if event is None:
        return None
    records = connection.execute(
        "SELECT role, record_key, payload, source_id, locator FROM records"
        " WHERE ws=? AND event_id=? AND active=1 ORDER BY role, record_key",
        (ws, event_id)).fetchall()
    links = connection.execute(
        "SELECT * FROM links WHERE ws=? AND event_id=? ORDER BY rowid", (ws, event_id)).fetchall()
    decisions = connection.execute(
        "SELECT * FROM agent_decisions WHERE ws=? AND event_id=? ORDER BY rowid",
        (ws, event_id)).fetchall()
    return {
        "event": dict(event),
        "records": [{"role": r["role"], "record_key": r["record_key"],
                     "payload": json.loads(r["payload"]), "source_id": r["source_id"],
                     "line": r["locator"]} for r in records],
        "links": [dict(link) for link in links],
        "decisions": [dict(decision) for decision in decisions],
        "roles": sorted({r["role"] for r in records}),
    }


def timeline(connection, ws: str, limit: int = 100) -> list[dict]:
    """Events in this workspace, newest first, with how much is attached to each."""
    # `r.ws = e.ws` is not redundant. An event id is unique per workspace, not globally,
    # so joining on the id alone counts another company's records into this one's totals
    # the moment two workspaces import a pack that uses the same references.
    rows = connection.execute(
        "SELECT e.*, COUNT(r.id) AS record_count FROM economic_events e"
        " LEFT JOIN records r ON r.event_id = e.id AND r.ws = e.ws AND r.active = 1"
        " WHERE e.ws=? GROUP BY e.id ORDER BY e.occurred_on DESC, e.rowid DESC LIMIT ?",
        (ws, min(limit, 500))).fetchall()
    return [dict(row) for row in rows]
