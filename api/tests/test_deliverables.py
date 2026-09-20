import pytest
import pypdfium2
from app import db
from app.agents.registry import AGENTS
from app.agents.tools import Toolbox
from app.agents.budget import Meter
from app.agents.deliverables import deliverable, pdf
from tests.test_agent_runtime import ws, run, FakeModel, ap_result  # noqa: F401


def test_runtime_saves_the_requested_task_and_its_output(ws):
    output = run(ws, "A1", "Review only invoice VI-1 for duplicates.", FakeModel([
        ([("read_records", {"role": "vendor_invoices"})], None),
        ([], ap_result())]))
    saved = deliverable(ws, output.decision_id)
    assert saved["objective"] == "Review only invoice VI-1 for duplicates."
    assert saved["result"]["summary"] == output.result.summary
    assert saved["legacy"] is False
    assert saved["stale"] is False
    assert saved["evidence"][0]["source_name"]
    assert saved["evidence"][0]["line"] >= 2
    response = pdf(ws, output.decision_id)
    document = pypdfium2.PdfDocument(response.body)
    text = " ".join(document[i].get_textpage().get_text_range() for i in range(len(document)))
    assert "Review only invoice VI-1" in text
    assert "Accounts Payable" in text
    with pytest.raises(Exception) as error:
        deliverable("not-this-workspace", output.decision_id)
    assert error.value.status_code == 404


@pytest.mark.parametrize("agent", [key for key, spec in AGENTS.items() if spec.tier == "subagent"])
def test_every_specialist_has_a_deliverable_without_rerunning(ws, agent):
    from app import ingestion
    config = ingestion.workspace_config(ws)
    snap = ingestion.coverage(ws)["snapshot"]["id"]
    box = Toolbox(ws, AGENTS[agent], Meter(), [], config, snap, "test")
    decision = box.record_decision(agent=agent, action="Review result", summary="Recorded answer",
                                  why="Recorded rationale", confidence=None, evidence=[], model="test", cost_cents=0)
    data = deliverable(ws, decision)
    assert data["agent_name"] == AGENTS[agent].name
    assert data["result"]["summary"] == "Recorded answer"
    assert data["objective"] is None  # Never invent missing historical prompts.
    assert pdf(ws, decision).body.startswith(b"%PDF-")


def test_historical_and_long_outputs_remain_exportable(ws):
    from app import ingestion
    config = ingestion.workspace_config(ws)
    box = Toolbox(ws, AGENTS["A1"], Meter(), [], config, "old-snapshot", "test")
    decision = box.record_decision(agent="A1", action="Long result", summary="<b>untrusted & literal</b> " * 600,
                                  why="Long rationale " * 400, confidence=None, evidence=[], model="test", cost_cents=0)
    assert deliverable(ws, decision)["stale"] is True
    assert len(pypdfium2.PdfDocument(pdf(ws, decision).body)) > 1
