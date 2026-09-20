"""Human review reaches the agents, and the agents cannot forge it.

The loop existed on the coordinator the pivot deleted, so agents went back to
running with no knowledge of what a person had already decided. `approvals.py`
still wrote precedent and the UI still had a panel for it; nothing read it.

These cover the half that is a safety property rather than a feature: a run may
read precedent and count a use, and may not invent one.
"""

from __future__ import annotations

import json

import pytest

from app import approvals, db
from app.agents import schemas
from app.agents.runtime import checked_memory, system_prompt
from app.agents.registry import AGENTS

from tests.test_agent_runtime import (  # noqa: F401
    FakeModel, ap_result, invoice_key, run, ws,
)

OFFERED = [
    {"id": "PB-real", "pattern": "Invoice without a purchase order",
     "verdict": "approved", "guidance": "Re-check against the current snapshot."},
]


def _result(checks):
    return ap_result(memory_checks=[schemas.MemoryCheck(**c) for c in checks])


def test_a_declined_precedent_is_kept_as_prominently_as_an_applied_one():
    """Declining is the mechanism working. Keeping only applications would make
    a correctly cautious run look like one that never checked."""
    kept, notes = checked_memory(
        _result([{"precedent_id": "PB-real", "applied": False,
                  "reason": "This snapshot shows a different vendor and no matching order."}]),
        OFFERED)

    assert [(c["precedent_id"], c["applied"]) for c in kept] == [("PB-real", False)]
    assert notes == []


def test_a_run_cannot_invent_a_precedent_it_was_never_offered():
    """The safety property. A model can put any string in `precedent_id`. Taken
    at face value a run could manufacture its own memory: claim it consulted
    guidance nobody gave, have it counted as a use, and have it displayed as a
    human decision."""
    kept, notes = checked_memory(
        _result([{"precedent_id": "PB-real", "applied": True, "reason": "Same situation."},
                 {"precedent_id": "PB-invented", "applied": True, "reason": "Asserting this exists."}]),
        OFFERED)

    assert [c["precedent_id"] for c in kept] == ["PB-real"]
    assert any("PB-invented" in note for note in notes)


def test_silence_is_not_a_check():
    """A run offered guidance that never mentions it has not re-checked
    anything, and must not read as though it had."""
    kept, notes = checked_memory(_result([]), OFFERED)

    assert kept == []
    assert any("PB-real" in note and "not addressed" in note for note in notes)


def test_the_same_precedent_twice_counts_once():
    kept, _ = checked_memory(
        _result([{"precedent_id": "PB-real", "applied": True, "reason": "Same situation."},
                 {"precedent_id": "PB-real", "applied": False, "reason": "Changed my mind."}]),
        OFFERED)

    assert len(kept) == 1


def test_an_agent_offered_no_precedent_is_not_told_to_weigh_any():
    """The rule is appended only when memory actually exists, so a fresh
    workspace never instructs an agent about guidance it was not given."""
    spec = AGENTS["A1"]
    assert "reviewed_precedents" not in system_prompt(spec)
    assert "reviewed_precedents" in system_prompt(spec, precedents=True)


def test_the_result_schema_requires_memory_checks():
    """Strict structured output rejects a schema whose properties contain a key
    missing from `required`. A default here would make every live call fail
    while fake-response tests kept passing — which is exactly how this was
    shipped broken once already."""
    schema = schemas.APResult.model_json_schema()
    assert "memory_checks" in schema["required"]


def test_a_run_records_what_it_did_with_memory_and_counts_the_use(ws):  # noqa: F811
    """End to end through run_agent: the decision row carries the check, and
    the precedent's use counter moves."""
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO precedents (id, ws, pattern, verdict, guidance, scope,"
            " decided_by, created_at, status, uses) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("PB-live", ws, "Invoice without a purchase order", "approved",
             "Re-check against the current snapshot.", "workspace",
             "a reviewer", db.now(), "active", 0))

    key = invoice_key(ws, "INV-100")
    checks = [{"precedent_id": "PB-live", "applied": False,
               "reason": "The invoice in this snapshot carries an order reference, so "
                         "the situation that decision covered is not this one."}]
    model = FakeModel([
        ([("three_way_match", {"invoice_key": key})], None),
        ([], ap_result(
            citations=[schemas.Citation(role="vendor_invoices", record_key=key)],
            memory_checks=[schemas.MemoryCheck(**c) for c in checks],
            matched_po="PO-1", matched_receipt="GR-1")),
    ])
    result = run(ws, "A1", f"Review invoice {key}.", model, record_keys=(key,))
    assert result.decision_id

    with db.connect() as connection:
        row = connection.execute(
            "SELECT memory_checks FROM agent_decisions WHERE id=?", (result.decision_id,)
        ).fetchone()
        stored = json.loads(row["memory_checks"])
        assert [(c["precedent_id"], c["applied"]) for c in stored] == [("PB-live", False)]
        assert approvals.active_precedents(connection, ws)[0]["uses"] == 1
