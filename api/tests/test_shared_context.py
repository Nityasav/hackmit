"""Collaboration is attributed, scoped and bounded; it never grants evidence access."""
import json
import pytest
from app import db, ingestion
from app.agents.registry import AGENTS
from app.agents.budget import Meter
from app.agents.tools import Toolbox
from app.agents.shared_context import retrieve, refresh, MAX_ITEMS, MAX_CHARS
from app.agents.runtime import bounded_context
from tests.test_agent_runtime import ws  # noqa: F401


def box(ws, agent="B1", thread="current"):
    return Toolbox(ws, AGENTS[agent], Meter(), ingestion.financial_records(ws)["records"],
                   ingestion.workspace_config(ws), ingestion.coverage(ws)["snapshot"]["id"], thread)


def publish(ws, agent="B3", thread="current", snapshot=None, summary="The ledger needs a review.", decision="result-1"):
    snapshot = snapshot or ingestion.coverage(ws)["snapshot"]["id"]
    with db.connect() as c:
        db.event(c, ws, "agent.deliverable", {"decision_id": decision, "thread_id": thread,
            "snapshot_id": snapshot, "readable_roles": list(AGENTS[agent].roles),
            "output": {"agent_id": agent, "result": {"summary": summary, "disposition": "exception", "citations": []}}})


def test_colleague_handoff_is_delivered_once_and_does_not_authorize_citations(ws):
    publish(ws)
    target = box(ws)
    items = refresh(target)
    assert len(items) == 1 and items[0]["kind"] == "handoff"
    assert items[0]["from_agent"] == "B3"
    assert not target.read_keys
    assert refresh(target) == []
    with db.connect() as c:
        payload = json.loads(c.execute("SELECT payload FROM events WHERE kind='agent.activity' ORDER BY rowid DESC LIMIT 1").fetchone()[0])
        assert payload["agent"] == "B1" and payload["status"] == "handoff"


def test_memory_does_not_cross_company_roles_or_snapshot(ws):
    publish(ws, snapshot="earlier-snapshot", thread="prior")
    old = retrieve(box(ws))[0]
    assert old["kind"] == "historical_context" and old["same_snapshot"] is False
    assert retrieve(box(ws, agent="A2")) == []
    foreign = box(ws)
    foreign.ws = "another-company"
    assert retrieve(foreign) == []


def test_shared_context_stays_bounded_and_leaves_room_for_live_handoffs(ws):
    for i in range(20):
        publish(ws, thread=f"prior-{i}", snapshot=f"old-{i}", summary="Long result " * 2000, decision=f"prior-{i}")
    target = box(ws)
    assert len(refresh(target)) <= 3
    publish(ws, decision="new-live")
    assert any(item["decision_id"] == "new-live" for item in refresh(target))
    assert len(target.shared_context) <= MAX_ITEMS
    assert len(json.dumps(list(target.shared_context.values()))) <= MAX_CHARS


def test_compaction_preserves_call_pairs_and_marks_omitted_evidence():
    messages = [{"role": "system", "content": "Never invent evidence."},
                {"type": "function_call", "call_id": "read-1", "name": "read_records", "arguments": "{}"},
                {"type": "function_call_output", "call_id": "read-1", "output": "data " * 20000}]
    bounded = bounded_context(messages, limit=10000)
    assert bounded[0] == messages[0] and bounded[1] == messages[1]
    assert bounded[2]["call_id"] == "read-1"
    assert json.loads(bounded[2]["output"])["compacted"] is True
    assert len(json.dumps(bounded)) < 10000
    assert len(messages[2]["output"]) == 100000
