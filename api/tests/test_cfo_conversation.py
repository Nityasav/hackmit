import asyncio
import json
from types import SimpleNamespace
import pytest
from app import db
from app.agents import chat
from app.agents.cfo_conversation import CFOResponse, converse, context_for, SYSTEM
from app.agents.budget import Meter, spent_today
from app.agents.runtime import AgentFailed
from tests.test_chat import client, ws  # noqa: F401


def response(**changes):
    return CFOResponse(**{**dict(mode="answer", text="The saved results need further evidence.", agent_ids=[],
                                 objective="", source_decision_ids=[], title="Cash review memo"), **changes})


class Provider:
    def __init__(self, answer):
        self.answer = answer; self.responses = self; self.calls = []
    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.answer, usage=SimpleNamespace(input_tokens=100, output_tokens=100))


def test_conversation_is_scoped_metered_and_retains_followups(client, ws):
    with db.connect() as c:
        chat._record(c, ws, {"id": "prior", "thread_id": "prior", "role": "person", "body": {"text": "Focus on cash."}, "status": "sent", "created_at": db.now()})
    provider = Provider(response())
    answer, context = asyncio.run(converse(ws, "Explain that", "new", Meter(), provider=provider))
    assert answer.mode == "answer" and context["recent_turns"][0]["text"] == "Focus on cash."
    assert provider.calls[0]["store"] is False
    assert "accounting-only" in SYSTEM and "untrusted" in SYSTEM
    with db.connect() as c:
        assert spent_today(c, ws) > 0


@pytest.mark.parametrize("message,expected", [("Run the FP&A agents", {"C1", "C2", "C3", "C4", "C5"}),
                                             ("Use A2 and C3", {"A2", "C3"})])
def test_explicit_specialists_are_honored(client, ws, message, expected):
    answer, _ = asyncio.run(converse(ws, message, "new", Meter(), provider=Provider(response())))
    assert answer.mode == "run_agents" and set(answer.agent_ids) == expected


def test_unknown_citations_are_refused(client, ws):
    with pytest.raises(AgentFailed, match="unavailable"):
        asyncio.run(converse(ws, "Explain cash", "new", Meter(), provider=Provider(response(source_decision_ids=["made-up"])) ))


def test_answer_does_not_launch_specialists_and_exports_exact_response(client, ws, monkeypatch):
    async def answer(*args):
        return response(), {"snapshot_id": "test-snapshot"}
    monkeypatch.setattr(chat, "converse", answer)
    import app.graph
    async def forbidden(*args, **kwargs):
        raise AssertionError("Explanation must not rerun agents")
    monkeypatch.setattr(app.graph, "run_investigation", forbidden)
    result = client.post(f"/api/workspaces/{ws}/chat", json={"message": "Create a memo explaining the saved result"})
    assert result.status_code == 201, result.text
    body = result.json()
    assert body["run"] is None
    pdf = client.get(f"/api/workspaces/{ws}/chat/{body['turn_id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    import pypdfium2
    doc = pypdfium2.PdfDocument(pdf.content)
    text = " ".join(p.get_textpage().get_text_range() for p in doc)
    assert "Cash review memo" in text and "saved results need further evidence" in text
    other = client.post("/api/workspaces", json={"name": "Other", "start": "2026-09-01", "end": "2026-09-30", "scope": "test"}).json()["id"]
    assert client.get(f"/api/workspaces/{other}/chat/{body['turn_id']}/pdf").status_code == 404
    assert context_for(other, "new")["recent_turns"] == []
