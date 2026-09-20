"""The only way an agent touches anything.

Every read is scoped, budgeted and recorded. An agent holds a `Toolbox`, never a
database connection, never the record list, and never a path. That is what makes the
guarantees checkable rather than promised: an agent cannot read a role it did not
declare, because the declaration is what built the box.

**Attenuation.** A delegation narrows authority. `Toolbox.narrow()` produces a box whose
roles and record keys are a subset of this one's; there is no operation that widens one.
The registry checks the static half of this at import, and this class enforces the
dynamic half at call time.

**Nothing here writes financial data.** The two writes are `record_decision` and
`record_link`, which describe what an agent concluded and what it matched. Neither can
create, alter or supersede a record, post a journal, or decide an approval.
"""

from __future__ import annotations

import json
from typing import Any

from .. import db
from ..accounting import cash, match, reconcile
from .budget import BudgetExceeded, Meter


class ScopeError(PermissionError):
    """An agent reached outside what it was delegated. Always a bug, never a refusal
    the agent can talk its way past."""


class Toolbox:
    def __init__(self, ws: str, spec, meter: Meter, records: list[dict], config: dict,
                 snapshot_id: str, thread_id: str, *, record_keys: tuple[str, ...] = (),
                 event_ids: tuple[str, ...] = ()):
        self.ws, self.spec, self.meter = ws, spec, meter
        self.config, self.snapshot_id, self.thread_id = config, snapshot_id, thread_id
        self._roles = frozenset(spec.roles)
        self._record_keys = frozenset(record_keys)
        self._event_ids = frozenset(event_ids)
        # The slice this agent may see, computed once. Everything below reads from here,
        # so there is no path to a record outside scope even by mistake.
        #
        # Roles are the authority boundary. `record_keys` is a *focus*, not a second
        # filter: "review invoice VI-1" means act on that invoice, and an agent that
        # could not also read the order, the receipt and the approval behind it could
        # not match it at all. Narrowing the readable set to the subject alone made
        # every match fail for want of its own evidence.
        self._records = [r for r in records if r["role"] in self._roles]
        #: Everything actually read, so a citation can be checked against it.
        self.read_keys: set[str] = set()
        self.read_sources: set[str] = set()
        self.calculations: dict[str, dict] = {}

    # ----------------------------------------------------------------- scope --
    @property
    def roles(self) -> frozenset[str]:
        return self._roles

    def narrow(self, spec, *, record_keys=(), event_ids=()) -> "Toolbox":
        """A child's box. Never wider than this one, in roles or in records."""
        child_roles = set(spec.roles)
        if not child_roles <= self._roles:
            raise ScopeError(
                f"{spec.id} would read {sorted(child_roles - self._roles)}, which "
                f"{self.spec.id} cannot read. A delegation cannot widen scope.")
        keys = frozenset(record_keys) if record_keys else self._record_keys
        if self._record_keys and not keys <= self._record_keys:
            raise ScopeError(f"{spec.id} was given record keys outside {self.spec.id}'s scope.")
        return Toolbox(self.ws, spec, self.meter, self._records, self.config,
                       self.snapshot_id, self.thread_id,
                       record_keys=tuple(keys), event_ids=tuple(event_ids or self._event_ids))

    def _charge(self, tool: str) -> None:
        if tool not in self.spec.tools:
            raise ScopeError(f"{self.spec.id} does not hold the tool {tool!r}.")
        self.meter.charge_tool_call(self.spec.id, self.spec.budget)

    # ------------------------------------------------------------------ reads --
    def read_records(self, role: str, limit: int = 50, offset: int = 0) -> dict:
        """Committed records of one role, inside scope."""
        self._charge("read_records")
        if role not in self._roles:
            raise ScopeError(
                f"{self.spec.id} may read {sorted(self._roles)}; {role!r} is not among them.")
        rows = [r for r in self._records if r["role"] == role]
        window = rows[offset:offset + min(limit, 200)]
        for row in window:
            self.read_keys.add(row["record_key"])
        return {
            "role": role, "total": len(rows), "offset": offset,
            "records": [{"record_key": r["record_key"], "payload": r["payload"],
                         "source_id": r["source_id"], "line": r["locator"]} for r in window],
            "note": "Supplied records only. Nothing here implies the population is complete.",
        }

    def read_source(self, source_id: str, start: int = 1, limit: int = 80) -> dict:
        """A span of an original uploaded file, exactly as it was supplied."""
        self._charge("read_source")
        if not any(r["source_id"] == source_id for r in self._records):
            raise ScopeError(
                f"{self.spec.id} may only read sources behind its own records; "
                f"{source_id!r} is not one of them.")
        from ..ingestion import source_view
        body = source_view(self.ws, source_id, start, min(limit, 200))
        self.read_sources.add(source_id)
        return {"source_id": source_id, "name": body["name"], "line_count": body["line_count"],
                "lines": body["lines"]}

    def read_event(self, event_id: str) -> dict:
        """Everything carrying one economic event id: Invariant 1, as a query."""
        self._charge("read_event")
        with db.connect() as connection:
            event = connection.execute(
                "SELECT * FROM economic_events WHERE ws=? AND id=?", (self.ws, event_id)).fetchone()
            links = connection.execute(
                "SELECT * FROM links WHERE ws=? AND event_id=? ORDER BY rowid",
                (self.ws, event_id)).fetchall()
        related = [r for r in self._records if r["payload"].get("event_ref") == event_id]
        for row in related:
            self.read_keys.add(row["record_key"])
        return {
            "event": dict(event) if event else None,
            "links": [dict(link) for link in links],
            "records": [{"role": r["role"], "record_key": r["record_key"],
                         "payload": r["payload"]} for r in related],
        }

    # ----------------------------------------------------- deterministic work --
    def three_way_match(self, invoice_key: str) -> dict:
        """Match an invoice to its order and receipt. Arithmetic, not judgment."""
        self._charge("three_way_match")
        if self._record_keys and invoice_key not in self._record_keys:
            raise ScopeError(f"{invoice_key!r} is outside this delegation.")
        result = match.three_way(self._records, invoice_key, self.config).as_dict()
        # A claim may only cite what the agent actually retrieved, so matching counts
        # as retrieval of everything it looked at.
        for citation in result["citations"]:
            self.read_keys.add(citation["record_key"])
            self.read_sources.add(citation["source_id"])
        self.calculations[f"match:{invoice_key}"] = result
        return result

    def find_duplicates(self, invoice_key: str = "") -> dict:
        self._charge("find_duplicates")
        found = match.find_duplicates(self._records, invoice_key)
        for candidate in found:
            for citation in candidate["citations"]:
                self.read_keys.add(citation["record_key"])
            self.calculations[candidate["id"]] = candidate
        return {"candidates": found,
                "note": "Exact-key repeats only. A candidate is not a confirmed duplicate "
                        "payment, and payment status was not tested."}

    def check_policy(self, invoice_key: str) -> dict:
        """Policy tests that need this workspace's own thresholds."""
        self._charge("check_policy")
        result = match.three_way(self._records, invoice_key, self.config).as_dict()
        policy_codes = {"over_approval_limit", "self_approved", "missing_approval",
                        "approval_limit_unknown"}
        return {"exceptions": [e for e in result["exceptions"] if e["code"] in policy_codes],
                "settings": self.config.get("settings") or {}}


    def reconcile_bank(self) -> dict:
        """Agree bank activity to the books, by recorded reference."""
        self._charge("reconcile_bank")
        result = reconcile.reconcile_bank(self._records, self.config)
        for bucket in ("matched", "unmatched_bank", "unmatched_book"):
            for item in result[bucket]:
                for citation in item.get("citations", []):
                    self.read_keys.add(citation["record_key"])
                    self.read_sources.add(citation["source_id"])
        self.calculations["reconcile"] = result
        return result

    def decompose_payout(self, payout_key: str = "") -> dict:
        """Split a processor payout into gross, deductions and what reached the bank."""
        self._charge("decompose_payout")
        payouts = reconcile.decompose_payout(self._records, payout_key)
        for payout in payouts:
            for citation in payout["citations"]:
                self.read_keys.add(citation["record_key"])
                self.read_sources.add(citation["source_id"])
            self.calculations[f"payout:{payout['payout_key']}"] = payout
        return {"payouts": payouts}

    def project_cash(self, horizon_days: int = 45) -> dict:
        """Cash now, and what is committed to move next."""
        self._charge("project_cash")
        result = cash.project(self._records, self.config, horizon_days)
        result["position"] = cash.position(self._records, self.config)
        for bucket in ("outflows", "inflows"):
            for item in result[bucket]:
                for citation in item["citations"]:
                    self.read_keys.add(citation["record_key"])
                    self.read_sources.add(citation["source_id"])
        self.calculations["cash"] = result
        return result

    # ----------------------------------------------------------------- writes --
    def record_decision(self, *, agent: str, action: str, summary: str, why: str,
                        confidence: int | None, evidence: list[dict], model: str,
                        cost_cents: int, event_id: str | None = None,
                        reviewer: str | None = None, verdict: str | None = None,
                        escalated: bool = False,
                        memory_checks: list[dict] | None = None) -> str:
        """Write one row of the defensible trail. The only record of what happened."""
        decision_id = db.uid("decision")
        with db.connect() as connection:
            connection.execute(
                "INSERT INTO agent_decisions (id, ws, event_id, thread_id, run_id, agent,"
                " parent_agent, action, summary, why, confidence, evidence, reviewer,"
                " review_verdict, escalated, model, cost_cents, memory_checks, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (decision_id, self.ws, event_id, self.thread_id, self.thread_id, agent,
                 self.spec.parent, action, summary, why, confidence,
                 db.encode(evidence), reviewer, verdict, int(escalated), model, cost_cents,
                 db.encode(memory_checks or []), db.now()))
        return decision_id

    def record_link(self, *, from_type: str, from_id: str, to_type: str, to_id: str,
                    kind: str, method: str, confidence: int, rationale: str,
                    event_id: str | None = None) -> None:
        """Draw one typed edge, carrying how it was established.

        `method` separates an exact reference match from a fuzzy or inferred one, which
        is the difference a reviewer most needs to see. `confidence` comes from the
        rubric in `accounting/match.py`; nothing a model says reaches this column.
        """
        if method not in {"exact", "fuzzy", "inferred", "human"}:
            raise ValueError("A link must say how it was established")
        with db.connect() as connection:
            connection.execute(
                "INSERT INTO links (id, ws, event_id, from_type, from_id, to_type, to_id,"
                " kind, method, confidence, rationale, created_by, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(ws, from_type, from_id, to_type, to_id, kind) DO NOTHING",
                (db.uid("link"), self.ws, event_id, from_type, from_id, to_type, to_id,
                 kind, method, confidence, rationale, self.spec.id, db.now()))

    # ------------------------------------------------------------ validation --
    def validate_citations(self, citations: list[Any]) -> None:
        """Refuse a conclusion that cites evidence this agent never retrieved.

        The check that stops a plausible-looking citation from being invented: an agent
        may only point at rows it actually read through this box during this task.
        """
        for citation in citations:
            key = getattr(citation, "record_key", "") or ""
            source = getattr(citation, "source_id", "") or ""
            if key and key not in self.read_keys:
                raise ScopeError(
                    f"{self.spec.id} cited record {key!r}, which it did not retrieve.")
            if source and source not in self.read_sources:
                raise ScopeError(
                    f"{self.spec.id} cited source {source!r}, which it did not read.")


def dispatch(toolbox: Toolbox, name: str, arguments: dict) -> dict:
    """Run one named tool call. Unknown names are refused, never guessed at."""
    handlers = {
        "read_records": toolbox.read_records,
        "read_source": toolbox.read_source,
        "read_event": toolbox.read_event,
        "three_way_match": toolbox.three_way_match,
        "find_duplicates": toolbox.find_duplicates,
        "check_policy": toolbox.check_policy,
        "reconcile_bank": toolbox.reconcile_bank,
        "decompose_payout": toolbox.decompose_payout,
        "project_cash": toolbox.project_cash,
    }
    handler = handlers.get(name)
    if handler is None:
        raise ScopeError(f"{name!r} is not a tool this runtime implements.")
    return handler(**arguments)


def tool_definitions(spec) -> list[dict]:
    """JSON schemas for the tools one spec holds, for the provider's tool-calling API."""
    catalogue = {
        "read_records": {
            "description": "Committed records of one role, inside this task's scope.",
            "properties": {"role": {"type": "string", "enum": sorted(spec.roles)},
                           "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                           "offset": {"type": "integer", "minimum": 0}},
            "required": ["role"]},
        "read_source": {
            "description": "A span of an original uploaded file, exactly as supplied.",
            "properties": {"source_id": {"type": "string"},
                           "start": {"type": "integer", "minimum": 1},
                           "limit": {"type": "integer", "minimum": 1, "maximum": 200}},
            "required": ["source_id"]},
        "read_event": {
            "description": "Everything that carries one economic event id.",
            "properties": {"event_id": {"type": "string"}}, "required": ["event_id"]},
        "three_way_match": {
            "description": "Match a vendor invoice to its purchase order and goods "
                           "receipt. Returns a computed confidence and its inputs.",
            "properties": {"invoice_key": {"type": "string"}}, "required": ["invoice_key"]},
        "find_duplicates": {
            "description": "Invoices sharing vendor, number, amount and currency exactly.",
            "properties": {"invoice_key": {"type": "string"}}, "required": []},
        "check_policy": {
            "description": "Policy tests using this workspace's own thresholds.",
            "properties": {"invoice_key": {"type": "string"}}, "required": ["invoice_key"]},
        "reconcile_bank": {
            "description": "Agree bank activity to the books by recorded reference. "
                           "Returns matched lines, differences and both unmatched sides.",
            "properties": {}, "required": []},
        "decompose_payout": {
            "description": "Split a processor payout into gross, fees, refunds, "
                           "chargebacks and the net that reached the bank.",
            "properties": {"payout_key": {"type": "string"}}, "required": []},
        "project_cash": {
            "description": "Cash position now, and the commitments already recorded "
                           "against it over a horizon in days.",
            "properties": {"horizon_days": {"type": "integer", "minimum": 1, "maximum": 180}},
            "required": []},
    }
    return [{
        "type": "function", "name": name,
        "description": catalogue[name]["description"],
        "parameters": {"type": "object", "properties": catalogue[name]["properties"],
                       "required": catalogue[name]["required"], "additionalProperties": False},
    } for name in spec.tools if name in catalogue]
