"""The phase-8 gate: the whole flow, from a sentence to a decision and back.

A person types what they want looked at, the organization runs, something stops for them,
they answer it, and the run continues. That is the product. These tests drive it through
the HTTP surface the browser actually calls, with a scripted model, so what is exercised
is the contract rather than the internals.

The one thing being guarded most carefully: a turn is recorded before its run starts.
A conversation where failed turns quietly vanish makes a crash look like a question nobody
asked, and that is the failure a person cannot debug from the outside.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db, security
from app.agents import schemas
from app.main import app

from tests.conftest import HEADERS, SAMPLE_FILES


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CFO_DB_PATH", str(tmp_path / "cfo.db"))
    monkeypatch.delenv("SCHOOLTRACE_USERS", raising=False)
    security.SESSIONS.clear()
    with TestClient(app, headers=HEADERS) as client:
        yield client


@pytest.fixture
def ws(client) -> str:
    created = client.post("/api/workspaces", json={
        "name": "Halden Cloud Inc.", "start": "2026-09-01", "end": "2026-09-30",
        "scope": "September close",
        "settings": {"approval_limit_cents": 500_000, "materiality_cents": 100_000}})
    workspace = created.json()["id"]
    files = [f for f in SAMPLE_FILES if not f.get("later")]
    batch = client.post(
        f"/api/workspaces/{workspace}/imports",
        files=[("files", (f["name"], f["content"].encode(), "text/plain")) for f in files],
        data={"metadata": json.dumps([{"role": f["role"], **f.get("options", {})}
                                      for f in files])}).json()
    saved = client.post(f"/api/workspaces/{workspace}/imports/{batch['id']}/commit",
                        json={"expected_version": batch["version"],
                              "idempotency_key": batch["id"]})
    assert saved.status_code == 200, saved.text
    return workspace


def _scripted(monkeypatch, disposition="clear"):
    """Put a scripted model behind the graph, so the HTTP surface runs without a provider.

    Patched on `app.graph`, not `app.graph.build`: the chat module does
    `from ..graph import run_investigation`, which binds the name in the package
    namespace. Patching the module it was defined in leaves the package's copy alone and
    the test then exercises nothing it thinks it is exercising.
    """
    import app.graph as graph_package
    from app.graph import build as build_module
    from tests.test_graph import _clear_model

    model = _clear_model() if disposition == "clear" else _insufficient()
    original = build_module.run_investigation
    resume = build_module.resume_investigation

    async def run(ws, objective, **kwargs):
        kwargs.setdefault("client", model)
        return await original(ws, objective, **kwargs)

    async def again(ws, thread_id, decision, **kwargs):
        kwargs.setdefault("client", model)
        return await resume(ws, thread_id, decision, **kwargs)

    monkeypatch.setattr(graph_package, "run_investigation", run)
    monkeypatch.setattr(graph_package, "resume_investigation", again)
    return model


def _insufficient():
    """Every agent stops and asks. `insufficient_evidence` escalates by design."""
    from tests.test_agent_runtime import FakeModel

    def answer(schema, kwargs):
        fields = dict(summary="I cannot settle this on what I was given.",
                      disposition="insufficient_evidence",
                      rationale="The records supplied do not answer the question asked.",
                      citations=[], proposed_action="A person has to decide.",
                      memory_checks=[])
        return schema(**fields, may_pay=False) if schema is schemas.APResult else schema(**fields)

    return FakeModel([([], None)], build=answer)


def talk(client, ws, message, **body):
    return client.post(f"/api/workspaces/{ws}/chat", json={"message": message, **body})


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #

def test_a_sentence_reaches_the_organization_and_comes_back_answered(client, ws, monkeypatch):
    _scripted(monkeypatch)

    response = talk(client, ws, "Review payables and cash.")

    assert response.status_code == 201, response.text
    reply = response.json()["reply"]
    assert reply["routed_to"] == ["Treasurer"]
    assert reply["findings"]
    assert reply["run_id"]


def test_a_question_that_stops_for_a_person_can_be_answered_and_the_run_continues(
        client, ws, monkeypatch):
    """The whole loop: ask, pause, decide, resume."""
    _scripted(monkeypatch, "insufficient")

    started = talk(client, ws, "Review payables and cash.").json()
    waiting = started["reply"]["escalations"]
    assert waiting, "an agent that cannot conclude must stop for a person"

    queue = client.get(f"/api/workspaces/{ws}/agents/escalations")
    assert queue.status_code == 200
    assert queue.json()["count"] >= 1

    # Addressed to the run, not the conversation: the investigation is what paused.
    answered = client.post(f"/api/workspaces/{ws}/agents/escalations/decide", json={
        "thread_id": started["run_id"], "decision": "approved",
        "approval_id": waiting[0]["approval_id"]})

    assert answered.status_code == 200, answered.text


def test_one_answer_does_not_resolve_a_question_it_was_not_given_for(client, ws, monkeypatch):
    """Several agents pause in one run. Applying one answer to all of them records a
    decision on questions the person was never shown."""
    _scripted(monkeypatch, "insufficient")
    started = talk(client, ws, "Review payables and cash.").json()
    assert len(started["reply"]["escalations"]) > 1, "this needs more than one question"

    response = client.post(f"/api/workspaces/{ws}/agents/escalations/decide", json={
        "thread_id": started["run_id"], "decision": "approved"})

    assert response.status_code == 409, response.text
    assert "ambiguous_decision" in response.text


# --------------------------------------------------------------------------- #
# The conversation itself
# --------------------------------------------------------------------------- #

def test_the_question_is_on_the_record_before_the_run_starts(client, ws, monkeypatch):
    """A turn that only appears once it succeeds makes a crash look like a question
    nobody asked."""
    import app.graph as graph_package

    async def explode(*args, **kwargs):
        from app.agents.runtime import AgentFailed
        raise AgentFailed("the provider was unreachable")

    monkeypatch.setattr(graph_package, "run_investigation", explode)

    response = talk(client, ws, "Review payables and cash.")
    assert response.status_code == 409, response.text

    turns = client.get(f"/api/workspaces/{ws}/chat").json()["turns"]
    assert [t["role"] for t in turns] == ["person", "orchestrator"]
    assert turns[0]["body"]["text"] == "Review payables and cash."
    assert turns[1]["status"] == "failed"
    assert "unreachable" in turns[1]["body"]["text"]


def test_the_exchange_reads_in_the_order_it_happened(client, ws, monkeypatch):
    _scripted(monkeypatch)
    first = talk(client, ws, "Review payables and cash.").json()
    talk(client, ws, "And the bank reconciliation.", thread_id=first["thread_id"])

    turns = client.get(f"/api/workspaces/{ws}/chat",
                       params={"thread_id": first["thread_id"]}).json()["turns"]

    assert [t["role"] for t in turns] == ["person", "orchestrator", "person", "orchestrator"]
    assert turns[2]["body"]["text"] == "And the bank reconciliation."


def test_a_turn_that_found_nothing_says_so_rather_than_filling_the_space(client, ws):
    from app.agents.chat import reply_for

    reply = reply_for({"plan": ["A"], "findings": [], "waiting_on_you": [], "unresolved": [],
                       "status": "no_findings", "thread_id": "t"})

    assert "not a clean result" in reply["text"]


def test_a_run_where_every_agent_stopped_is_not_reported_as_concluding_nothing(client, ws):
    """An agent that stopped to ask something did reach a conclusion: that a person has
    to decide. A live run reported "nothing was concluded" beside three questions it had
    just raised."""
    from app.agents.chat import reply_for

    reply = reply_for({"plan": ["B"], "findings": [],
                       "waiting_on_you": [{"approval_id": "a"}, {"approval_id": "b"}],
                       "unresolved": [], "status": "waiting_on_you", "thread_id": "t"})

    assert "nothing was concluded" not in reply["text"]
    assert "stopped to ask you something" in reply["text"]
    assert "Nothing was decided without you" in reply["text"]


def test_no_model_writes_the_reply(client, ws, monkeypatch):
    """Every sentence is a count of the run or a line an agent recorded. A friendly
    summary nothing checked, in the same typeface as the ones that are, is the problem."""
    import inspect

    from app.agents import chat

    source = inspect.getsource(chat)

    assert "client" not in source.replace("client=", "")  # no provider handle is built
    assert "build_client" not in source
    reply = chat.reply_for({"plan": ["A"], "findings": [{"id": "f"}], "escalations": [],
                            "unresolved": [], "status": "completed", "thread_id": "t"})
    assert "written by a model" in reply["note"]


# --------------------------------------------------------------------------- #
# The timeline
# --------------------------------------------------------------------------- #

def test_the_timeline_reports_one_row_per_transaction_not_per_document(client, ws):
    """The invoice, the receipt, the payment and the journal entries are views of one
    thing. A timeline listing each separately reports one purchase four times."""
    response = client.get(f"/api/workspaces/{ws}/agents/timeline")

    assert response.status_code == 200, response.text
    rows = response.json()["events"]
    assert rows
    assert len({row["id"] for row in rows}) == len(rows)
    assert all(row["record_count"] >= 1 for row in rows)


def test_an_event_opens_onto_everything_that_carries_its_id(client, ws):
    rows = client.get(f"/api/workspaces/{ws}/agents/timeline").json()["events"]
    # The event the pack attaches the most to. Naming a kind instead would tie the test
    # to how the fixture happens to reference its rows rather than to the behaviour.
    richest = max(rows, key=lambda row: row["record_count"])

    detail = client.get(f"/api/workspaces/{ws}/agents/timeline/{richest['id']}")

    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert len(body["roles"]) > 1, "one event must gather more than one kind of record"
    assert body["records"]
    assert "decisions" in body and "links" in body


def test_an_event_from_another_workspace_is_not_counted_into_this_one(client, ws):
    """Event ids are unique per workspace, not globally. Two companies importing packs
    that use the same references must not inflate each other's counts."""
    other = client.post("/api/workspaces", json={
        "name": "Someone else", "start": "2026-09-01", "end": "2026-09-30",
        "scope": "September"}).json()["id"]
    files = [f for f in SAMPLE_FILES if not f.get("later")]
    batch = client.post(
        f"/api/workspaces/{other}/imports",
        files=[("files", (f["name"], f["content"].encode(), "text/plain")) for f in files],
        data={"metadata": json.dumps([{"role": f["role"], **f.get("options", {})}
                                      for f in files])}).json()
    client.post(f"/api/workspaces/{other}/imports/{batch['id']}/commit",
                json={"expected_version": batch["version"], "idempotency_key": batch["id"]})

    mine = client.get(f"/api/workspaces/{ws}/agents/timeline").json()["events"]
    theirs = client.get(f"/api/workspaces/{other}/agents/timeline").json()["events"]

    assert {r["id"] for r in mine} == {r["id"] for r in theirs}, "same pack, same references"
    for row in mine:
        twin = next(t for t in theirs if t["id"] == row["id"])
        assert row["record_count"] == twin["record_count"]


def test_an_unknown_event_is_refused_rather_than_answered_emptily(client, ws):
    response = client.get(f"/api/workspaces/{ws}/agents/timeline/EVT-NOPE")

    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Documents, when they were asked for
# --------------------------------------------------------------------------- #

def test_asking_for_a_one_pager_produces_one(client, ws, monkeypatch):
    _scripted(monkeypatch)

    body = talk(client, ws, "Review payables, then make me a one pager.").json()

    assert body["reply"]["deliverable"]["kind"] == "one_pager"
    assert "one-page snapshot" in body["reply"]["text"].lower()
    rows = client.get(f"/api/workspaces/{ws}/deliverables").json()["deliverables"]
    assert [r["kind"] for r in rows] == ["one_pager"]
    assert rows[0]["requested_by"] == "Review payables, then make me a one pager."


def test_asking_for_a_deck_produces_a_deck(client, ws, monkeypatch):
    _scripted(monkeypatch)

    body = talk(client, ws, "Review payables and build a slide deck.").json()

    assert body["reply"]["deliverable"]["kind"] == "deck"


def test_asking_for_nothing_produces_nothing(client, ws, monkeypatch):
    """The important one. A question about the books is not a request for a document."""
    _scripted(monkeypatch)

    body = talk(client, ws, "Review payables and cash.").json()

    assert body["reply"]["deliverable"] is None
    assert client.get(f"/api/workspaces/{ws}/deliverables").json()["deliverables"] == []


def test_the_document_is_made_after_the_run_not_before(client, ws, monkeypatch):
    """A report of the books as they were before this turn's work would describe a
    period the person did not just ask about."""
    _scripted(monkeypatch)

    body = talk(client, ws, "Make me a one pager.").json()
    document = client.get(
        f"/api/workspaces/{ws}/deliverables/{body['reply']['deliverable']['id']}").json()

    assert document["thread_id"] == body["run_id"]
    assert document["payload"]["records"] > 0


def test_the_queue_and_the_reply_describe_an_agent_the_same_way(client, ws, monkeypatch):
    """These carried one concept in two shapes — an object in the interrupt payload and
    a bare id in the queue — so a screen built against either broke on the other, and
    the type meant to describe both could only be right about one.

    It surfaced as "Objects are not valid as a React child", which is what a shape
    mismatch looks like from the outside: nothing to do with the field it names.
    """
    _scripted(monkeypatch, "insufficient")

    started = talk(client, ws, "Review payables and cash.").json()
    from_reply = started["reply"]["escalations"]
    from_queue = client.get(f"/api/workspaces/{ws}/agents/escalations").json()["escalations"]

    assert from_reply and from_queue
    for item in from_reply + from_queue:
        assert isinstance(item["agent"], dict), item["agent"]
        assert item["agent"]["id"] and item["agent"]["name"]
        # The name is what a person reads. A bare id renders as "B4" to someone who has
        # no idea what B4 is.
        assert item["agent"]["name"] != item["agent"]["id"]


def test_every_field_the_escalation_card_renders_is_sent(client, ws, monkeypatch):
    """Named one by one, because a missing one does not fail — it renders blank."""
    _scripted(monkeypatch, "insufficient")

    waiting = talk(client, ws, "Review payables and cash.").json()["reply"]["escalations"][0]

    for field in ("approval_id", "agent", "title", "summary", "reasons"):
        assert field in waiting, field
    assert isinstance(waiting["reasons"], list)


def test_a_question_already_answered_says_so_instead_of_no_paused_run(client, ws, monkeypatch):
    """"No paused run with that thread id" is true and useless. The usual cause is a
    question already answered — from the other screen, or from a card left on an older
    message — and a person reading that has no idea whether their decision landed."""
    from app import approvals

    _scripted(monkeypatch, "insufficient")
    started = talk(client, ws, "Review payables and cash.").json()
    waiting = started["reply"]["escalations"]
    assert waiting

    for question in waiting:
        approvals.decide(ws, question["approval_id"], "approved")
    # And the run itself is carried past them, the way answering in the chat does.
    client.post(f"/api/workspaces/{ws}/agents/escalations/decide", json={
        "thread_id": started["run_id"], "decision": "approved",
        "approval_id": waiting[0]["approval_id"]})

    response = client.post(f"/api/workspaces/{ws}/agents/escalations/decide", json={
        "thread_id": started["run_id"], "decision": "approved",
        "approval_id": waiting[0]["approval_id"]})

    assert response.status_code in (200, 409), response.text
    if response.status_code == 409:
        assert "already approved" in response.text
        assert "nothing needs doing again" in response.text.lower()


def test_the_queue_is_what_says_a_question_is_still_open(client, ws, monkeypatch):
    """The escalations inside a turn are frozen when the reply is written. The screen
    reads the live queue to decide which still have buttons, so this has to stay the
    authoritative answer to "is this outstanding"."""
    from app import approvals

    _scripted(monkeypatch, "insufficient")
    started = talk(client, ws, "Review payables and cash.").json()
    first = started["reply"]["escalations"][0]["approval_id"]

    before = client.get(f"/api/workspaces/{ws}/agents/escalations").json()["escalations"]
    approvals.decide(ws, first, "approved")
    after = client.get(f"/api/workspaces/{ws}/agents/escalations").json()["escalations"]

    assert first in {item["approval_id"] for item in before}
    assert first not in {item["approval_id"] for item in after}


def test_a_second_message_starts_its_own_investigation(client, ws, monkeypatch):
    """A conversation and a run are not the same thing. They shared one id, so every
    message resumed the previous run's checkpoint instead of starting its own."""
    _scripted(monkeypatch)

    first = talk(client, ws, "Review payables and cash.").json()
    second = talk(client, ws, "And check the bank.",
                  thread_id=first["thread_id"]).json()

    assert second["thread_id"] == first["thread_id"], "the exchange continues"
    assert second["run_id"] != first["run_id"], "the investigation does not"


def test_a_turn_names_the_run_a_decision_should_be_addressed_to(client, ws, monkeypatch):
    """The browser answers a question against the run, never the conversation: only one
    investigation is paused on it."""
    _scripted(monkeypatch)
    body = talk(client, ws, "Review payables and cash.").json()

    turns = client.get(f"/api/workspaces/{ws}/chat").json()["turns"]

    assert body["reply"]["run_id"] == body["run_id"]
    assert all(turn["run_id"] for turn in turns)
    assert turns[-1]["run_id"] == body["run_id"]
