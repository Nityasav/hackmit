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

from .. import db, events, memory, roles
from ..accounting import (accruals, audit, cash, close, controls, match, planning,
                          receivables, reconcile, reporting, statements, variance)
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
        self.track_activity = False

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
        if self.track_activity:
            from .activity import emit
            emit(self.ws, self.thread_id, self.spec.id, "tool", tool)

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
            # The source id is in the output this agent is about to read, so citing it
            # is citing what it saw. Recording only the record key meant a legitimate
            # citation was refused as fabricated, which is a far worse failure than the
            # one the check exists to prevent: the guard must catch invention, not
            # punish an agent for quoting the evidence it was handed.
            self.read_sources.add(row["source_id"])
        return {
            "role": role, "total": len(rows), "offset": offset,
            "records": [{"record_key": r["record_key"],
                         # What a person should read. A composite key joined by an
                         # invisible separator prints as one run-on identifier, and an
                         # agent quoting it sends a reviewer looking for a document
                         # that does not exist.
                         "display": roles.readable_key(r["role"], r["record_key"]),
                         "payload": r["payload"],
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


    def _receivables(self, name: str, as_of: str = "") -> dict:
        self._charge(name)
        calculate = receivables.age_receivables if name == "age_receivables" else receivables.match_remittances
        result = calculate(self._records, self.config, as_of or None)
        for bucket in ("applications", "unapplied", "invoices"):
            for item in result[bucket]:
                for citation in item["citations"]:
                    self.read_keys.add(citation["record_key"])
                    self.read_sources.add(citation["source_id"])
        self.calculations[name] = result
        return result

    def age_receivables(self, as_of: str = "") -> dict:
        return self._receivables("age_receivables", as_of)

    def match_remittance(self, as_of: str = "") -> dict:
        return self._receivables("match_remittance", as_of)

    def build_statements(self) -> dict:
        """Income statement, balance sheet and cash flow, from the ledger.

        Deterministic end to end. B3 holds this tool and no model writes any figure it
        returns; the agent's job is to notice when something does not tie and to say so.
        """
        self._charge("build_statements")
        result = statements.statements(self._records, self.config)
        self.calculations["statements"] = result
        return result

    def close_checklist(self) -> dict:
        """What is outstanding before the period can be closed."""
        self._charge("close_checklist")
        result = close.checklist(self._records, self.config)
        self.calculations["close"] = result
        return result

    def propose_journal(self) -> dict:
        """Accruals the period owes, from deliveries with no invoice against them.

        Proposals only. Every journal is balanced before it is returned, and nothing
        downstream of this can post one.
        """
        self._charge("propose_journal")
        result = accruals.unbilled_receipts(self._records, self.config)
        for proposal in result["proposals"]:
            for citation in proposal["evidence"]:
                self.read_keys.add(citation["record_key"])
                self.read_sources.add(citation["source_id"])
            self.calculations[proposal["id"]] = proposal
        return result

    def reperform(self) -> dict:
        """Recompute the close independently, for a reviewer that trusts nothing.

        B4 must not accept a figure because a preparer reported it. This runs the same
        deterministic code against the same records and returns the answer directly, so
        a disagreement is visible rather than negotiable.
        """
        self._charge("reperform")
        result = {
            "statements": statements.statements(self._records, self.config),
            "close": close.checklist(self._records, self.config),
        }
        self.calculations["reperformed"] = {
            "balances": result["statements"]["balance_sheet"]["balances"],
            "ties": result["statements"]["cash_flow"]["ties"],
            "ready": result["close"]["ready"],
        }
        return result


    def roll_up(self) -> dict:
        """The budget and the actuals gathered into the chart's own categories."""
        self._charge("roll_up")
        result = planning.roll_up(self._records, self.config)
        self.calculations["roll_up"] = result
        return result

    def forecast_series(self) -> dict:
        """How the forecast did, account by account, with the basis each one recorded."""
        self._charge("forecast_series")
        result = planning.forecast_accuracy(self._records, self.config)
        for account in result["accounts"]:
            for citation in account["evidence"]:
                self.read_keys.add(citation["record_key"])
                self.read_sources.add(citation["source_id"])
        self.calculations["forecast"] = result
        return result

    def decompose_variance(self, account: str = "", plan: str = "budgets") -> dict:
        """A variance broken into the transactions that caused it.

        One account when named, otherwise the largest variances in the period. Every
        driver carries the ledger lines behind it, so what the agent writes about a
        variance is constrained to what the arithmetic already attributed.
        """
        self._charge("decompose_variance")
        if account:
            result = variance.decompose(self._records, account, self.config, plan=plan)
            explained = [result]
        else:
            result = variance.explain(self._records, self.config, plan=plan)
            explained = result["explained"]
        for item in explained:
            for driver in item.get("drivers", []):
                for citation in driver["evidence"]:
                    self.read_keys.add(citation["record_key"])
                    self.read_sources.add(citation["source_id"])
        # Scored so an escalation threshold has something to read. `attributed_pct` is the
        # share of the activity that reached a named transaction, which is exactly what
        # confidence in an explanation should mean.
        self.calculations["variance:" + (account or "period")] = {
            "confidence": result["attributed_pct"],
            "amount_cents": abs(result.get("variance_cents") or result.get("amount_cents") or 0),
            "unexplained_cents": result["unexplained_cents"],
            "detail": result,
        }
        return result

    def model_scenario(self, revenue_growth_pct: int = 0, expense_growth_pct: int = 0,
                       headcount_change: int = 0, periods: int = 3) -> dict:
        """Project this period forward under supplied assumptions.

        A projection, never a measurement. C4 escalates unconditionally because there is
        nothing to score one against.
        """
        self._charge("model_scenario")
        result = planning.scenario(
            self._records, self.config, revenue_growth_pct=revenue_growth_pct,
            expense_growth_pct=expense_growth_pct, headcount_change=headcount_change,
            periods=periods)
        self.calculations["scenario"] = result
        return result

    def build_report(self) -> dict:
        """The period's reporting, assembled from figures that already tie.

        Returns sections with their figures and an `intent` for the prose that belongs in
        each. There is no slot for a figure, which is what makes "writes prose, never
        numbers" a property of the tool rather than an instruction in a prompt.
        """
        self._charge("build_report")
        result = reporting.management_report(self._records, self.config)
        for section in result["sections"]:
            for item in section.get("drivers", []):
                for driver in item.get("drivers", []):
                    for citation in driver["evidence"]:
                        self.read_keys.add(citation["record_key"])
                        self.read_sources.add(citation["source_id"])
        self.calculations["report"] = result
        return result


    def run_controls(self) -> dict:
        """Every control test, over the committed records.

        A passing test is returned as a finding, not as silence. D2 judges the cases the
        rules cannot settle; it does not decide whether a rule fired.
        """
        self._charge("run_controls")
        found = controls.checks(self._records, self.config)
        for finding in found:
            for citation in finding["evidence"]:
                self.read_sources.add(citation["source_id"])
            for key in finding["record_keys"]:
                self.read_keys.add(key)
        result = {
            "checks": found,
            "exceptions": [c for c in found if c["status"] == "attention"],
            "passes": [c for c in found if c["status"] == "pass"],
            "gaps": [c for c in found if c["status"] == "gap"],
            "note": "Deterministic tests. A pass is a statement that this test found "
                    "nothing, which is narrower than a statement that nothing is wrong.",
        }
        self.calculations["controls"] = result
        return result

    def select_sample(self, role: str = "vendor_invoices", size: int = 10) -> dict:
        """A reproducible sample, with everything material taken in full."""
        self._charge("select_sample")
        result = audit.select(self._records, self.config, role=role, size=size)
        for item in result["selected"]:
            self.read_keys.add(item["record_key"])
            for citation in item["evidence"]:
                self.read_sources.add(citation["source_id"])
        self.calculations["sample"] = result
        return result

    def trace_transaction(self, invoice_key: str) -> dict:
        """Follow one purchase from the order that started it to the entries that recorded it."""
        self._charge("trace_transaction")
        result = audit.trace(self._records, invoice_key)
        for step in result.get("steps", []):
            for citation in step["evidence"]:
                self.read_keys.add(citation["record_key"])
                self.read_sources.add(citation["source_id"])
        self.calculations["trace:" + invoice_key] = result
        return result

    def read_decisions(self, limit: int = 50) -> dict:
        """What the agents have already decided in this workspace, newest first.

        D3 generates nothing. This returns the trail as it was written at the time, so an
        evidence pack is assembled out of what happened rather than reconstructed
        afterwards from what the records now look like.
        """
        self._charge("read_decisions")
        with db.connect() as connection:
            rows = connection.execute(
                "SELECT id, agent, action, summary, why, confidence, evidence, reviewer,"
                " review_verdict, escalated, model, cost_cents, created_at, thread_id,"
                " event_id FROM agent_decisions WHERE ws=? ORDER BY rowid DESC LIMIT ?",
                (self.ws, max(1, min(limit, 200)))).fetchall()
        decisions = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item["evidence"] or "[]")
            item["escalated"] = bool(item["escalated"])
            decisions.append(item)
        return {"decisions": decisions, "count": len(decisions),
                "note": "Written as the work happened. Nothing here was reconstructed."}

    def build_evidence_pack(self, event_id: str = "") -> dict:
        """Everything behind one transaction, or the workspace's whole trail.

        Collected, never generated: the records, the decisions that cite them, the links
        that were drawn and how each was established, and the precedent checks made. A
        reader who disagrees with a conclusion can follow it back to the bytes.
        """
        self._charge("build_evidence_pack")
        with db.connect() as connection:
            if event_id:
                event = events.view(connection, self.ws, event_id)
                decisions = connection.execute(
                    "SELECT * FROM agent_decisions WHERE ws=? AND event_id=?"
                    " ORDER BY rowid", (self.ws, event_id)).fetchall()
                links = connection.execute(
                    "SELECT * FROM links WHERE ws=? AND event_id=? ORDER BY rowid",
                    (self.ws, event_id)).fetchall()
            else:
                event = None
                decisions = connection.execute(
                    "SELECT * FROM agent_decisions WHERE ws=? ORDER BY rowid LIMIT 200",
                    (self.ws,)).fetchall()
                links = connection.execute(
                    "SELECT * FROM links WHERE ws=? ORDER BY rowid LIMIT 200",
                    (self.ws,)).fetchall()
            checks = memory.history(connection, self.ws)

        pack = {
            "event": event,
            "decisions": [dict(row) | {"evidence": json.loads(row["evidence"] or "[]")}
                          for row in decisions],
            "links": [dict(row) for row in links],
            "precedent_checks": checks,
            "assembled_at": db.now(),
            "note": "Assembled from what was recorded at the time. Nothing in this pack "
                    "was generated, inferred or filled in, and an empty section means "
                    "nothing of that kind was recorded rather than that none exists.",
        }
        self.calculations["evidence_pack"] = {
            "decisions": len(pack["decisions"]), "links": len(pack["links"]),
            "precedent_checks": len(checks)}
        return pack

    def check_precedents(self) -> dict:
        """Re-test what a person decided in earlier periods against this one.

        Never applies anything. Each precedent is checked, the outcome is written to the
        trail either way, and a finding a person has already decided keeps its exception
        and gains the earlier decision beside it.
        """
        self._charge("check_precedents")
        found = controls.checks(self._records, self.config)
        with db.connect() as connection:
            result = memory.apply_to_findings(connection, self.ws, found,
                                              actor=self.spec.id)
        result["findings"] = found
        self.calculations["precedents"] = {
            "applied": result["applied"], "declined": result["declined"]}
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
            db.event(connection, self.ws, "agent.decision_snapshot",
                     {"decision_id": decision_id, "snapshot_id": self.snapshot_id})
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
        "age_receivables": toolbox.age_receivables,
        "match_remittance": toolbox.match_remittance,
        "build_statements": toolbox.build_statements,
        "close_checklist": toolbox.close_checklist,
        "propose_journal": toolbox.propose_journal,
        "reperform": toolbox.reperform,
        "roll_up": toolbox.roll_up,
        "forecast_series": toolbox.forecast_series,
        "decompose_variance": toolbox.decompose_variance,
        "model_scenario": toolbox.model_scenario,
        "build_report": toolbox.build_report,
        "run_controls": toolbox.run_controls,
        "select_sample": toolbox.select_sample,
        "trace_transaction": toolbox.trace_transaction,
        "read_decisions": toolbox.read_decisions,
        "build_evidence_pack": toolbox.build_evidence_pack,
        "check_precedents": toolbox.check_precedents,
    }
    handler = handlers.get(name)
    if handler is None:
        raise ScopeError(f"{name!r} is not a tool this runtime implements.")
    return handler(**arguments)


def tool_definitions(spec) -> list[dict]:
    """JSON schemas for the tools one spec holds, for the provider's tool-calling API."""
    catalogue = {
        "age_receivables": {
            "description": "Age outstanding receivables after uniquely referenced cash allocations. Ambiguous receipts stay unapplied.",
            "properties": {"as_of": {"type": "string", "description": "YYYY-MM-DD; omit for workspace end."}},
            "required": []},
        "match_remittance": {
            "description": "Propose cash allocations using exact customer, currency and invoice references. No financial records are changed.",
            "properties": {"as_of": {"type": "string", "description": "YYYY-MM-DD; omit for workspace end."}},
            "required": []},
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
        "build_statements": {
            "description": "Income statement, balance sheet and cash flow computed from "
                           "the ledger in exact cents, with the checks that say whether "
                           "they tie. You do not write any of these figures.",
            "properties": {}, "required": []},
        "close_checklist": {
            "description": "Every close question, answered from the records, with what "
                           "is blocking the period and what is merely outstanding.",
            "properties": {}, "required": []},
        "propose_journal": {
            "description": "Accruals for deliveries inside the period with no invoice "
                           "against them. Balanced proposals; nothing posts.",
            "properties": {}, "required": []},
        "reperform": {
            "description": "Recompute the statements and the close independently, so a "
                           "preparer's figure can be checked rather than believed.",
            "properties": {}, "required": []},
        "roll_up": {
            "description": "Budget and actuals gathered into the chart's own reporting "
                           "categories, with headcount where it was supplied.",
            "properties": {}, "required": []},
        "forecast_series": {
            "description": "How the recorded forecast did against the actuals, account "
                           "by account, with the basis each forecast claimed for itself.",
            "properties": {}, "required": []},
        "decompose_variance": {
            "description": "A variance broken into the economic events that caused it, "
                           "each naming the ledger lines behind it. Name an account, or "
                           "leave it out for the largest variances in the period. You "
                           "explain what the drivers mean; you never compute one.",
            "properties": {"account": {"type": "string"},
                           "plan": {"type": "string", "enum": ["budgets", "forecasts"]}},
            "required": []},
        "model_scenario": {
            "description": "Project this period forward under assumptions you are given. "
                           "The result is a projection about a period that has not "
                           "happened, and must be reported as one.",
            "properties": {
                "revenue_growth_pct": {"type": "integer", "minimum": -100, "maximum": 200},
                "expense_growth_pct": {"type": "integer", "minimum": -100, "maximum": 200},
                "headcount_change": {"type": "integer", "minimum": -500, "maximum": 500},
                "periods": {"type": "integer", "minimum": 1, "maximum": 24}},
            "required": []},
        "build_report": {
            "description": "The period's reporting assembled from figures that already "
                           "tie, as sections each naming the prose that belongs in it. "
                           "Write the prose; every figure is already computed.",
            "properties": {}, "required": []},
        "run_controls": {
            "description": "Every control test over the committed records, with passes "
                           "reported as findings rather than as silence. You judge the "
                           "cases the rules cannot settle; you do not decide whether a "
                           "rule fired.",
            "properties": {}, "required": []},
        "select_sample": {
            "description": "A reproducible sample of one record type, with everything at "
                           "or above materiality taken in full. Returns the method and "
                           "the coverage alongside the selection.",
            "properties": {"role": {"type": "string", "enum": sorted(spec.roles)},
                           "size": {"type": "integer", "minimum": 1, "maximum": 50}},
            "required": []},
        "trace_transaction": {
            "description": "Follow one purchase from the order that started it to the "
                           "entries that recorded it, naming any step that is missing.",
            "properties": {"invoice_key": {"type": "string"}},
            "required": ["invoice_key"]},
        "read_decisions": {
            "description": "What the agents have already decided here, as it was written "
                           "at the time.",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 200}},
            "required": []},
        "build_evidence_pack": {
            "description": "Everything recorded behind one transaction, or the whole "
                           "workspace's trail: records, decisions, links and precedent "
                           "checks. Collected, never generated.",
            "properties": {"event_id": {"type": "string"}}, "required": []},
        "check_precedents": {
            "description": "Re-test what a person decided in earlier periods against "
                           "this one. Records every check, including the ones it "
                           "declines, and applies nothing on its own.",
            "properties": {}, "required": []},
    }
    return [{
        "type": "function", "name": name,
        "description": catalogue[name]["description"],
        "parameters": {"type": "object", "properties": catalogue[name]["properties"],
                       "required": catalogue[name]["required"], "additionalProperties": False},
    } for name in spec.tools if name in catalogue]
