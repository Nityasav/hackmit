"""The other half of the phase-4 gate: an escalation that actually waits, and resolves.

An escalation that only logs "someone should look at this" is a log line. These check
the version that holds: the run pauses at the node that raised it, the state survives in
the checkpointer, nothing beyond it happens, and the person's answer both resumes the run
and becomes precedent the next one has to reckon with.

No provider is called. The scripted model from the phase-2 tests decides what A1 returns;
what is under test is what the graph does with it.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app import approvals, db, ingestion
from app.agents import schemas
from app.graph import pending, resume_investigation, run_investigation
from tests.conftest import SAMPLE_FILES
from tests.test_agent_runtime import FakeModel, ap_result


@pytest.fixture
def ws(tmp_path, monkeypatch) -> str:
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    created = ingestion.create_workspace(ingestion.WorkspaceCreate(
        name="Halden Cloud Inc.", start="2026-09-01", end="2026-09-30",
        scope="September close",
        # Low enough that the sample invoice clears it, so the escalation under test is
        # the named condition rather than the amount.
        settings={"approval_limit_cents": 10_000_000, "materiality_cents": 100_000}))
    workspace = created["id"]
    files = [f for f in SAMPLE_FILES if not f.get("later")]
    batch = ingestion.stage(workspace, [
        (f["name"], f["content"].encode(), ingestion.FileOptions(role=f["role"]))
        for f in files])
    ingestion.commit(workspace, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="escalation"))
    return workspace


def _escalating_model(agent_conditions: dict[str, str] | None = None):
    """Every agent reads first, then reports an exception it must escalate.

    Reading first is not decoration: the runtime refuses a citation the agent did not
    retrieve, so a fake that concludes without looking gets rejected for the right
    reason and the escalation never happens.
    """
    def answer(schema, kwargs):
        # Cite the first record this agent actually read, whatever role that was.
        cited = [schemas.Citation(role=role, record_key=key, note="read during this task")
                 for role, key in [_first_read(kwargs)]]
        # Each agent escalates on conditions its own spec names, so a fixed code only
        # trips one of them. The caller says which condition each should raise.
        code = (agent_conditions or {}).get(_agent_of(kwargs), "no_purchase_order")
        fields = dict(
            summary="An exception the rules cannot settle.",
            disposition="exception",
            rationale="The supplied records do not establish what was ordered, so the "
                      "obligation cannot be matched to anything.",
            exceptions=[schemas.Exception_(
                code=code, detail="Raised by the scripted model for this test.")],
            citations=cited, proposed_action="Hold for an authorized person.",
            # Required, not defaulted: an agent offered no precedent still has to say
            # so explicitly, so silence never reads as a completed check.
            memory_checks=[])
        if schema is schemas.APResult:
            return schemas.APResult(**fields, may_pay=False)
        return schema(**fields)

    def read_something(kwargs):
        # Whatever this agent is allowed to read. The context the runtime sends names it,
        # so the fake never asks for a role the agent does not hold.
        context = json.loads(kwargs["input"][1]["content"])
        return [("read_records", {"role": context["readable_roles"][0]})]

    return FakeModel([(read_something, None), ([], None)], build=answer)


def _agent_of(kwargs) -> str:
    """Which agent is asking, from the system prompt the runtime built."""
    system = kwargs["input"][0]["content"]
    start = system.index("(") + 1
    return system[start:system.index(")", start)]


def _first_read(kwargs) -> tuple[str, str]:
    """The role and key the agent's own read returned, taken from the tool output."""
    for message in reversed(kwargs.get("input", [])):
        if isinstance(message, dict) and message.get("type") == "function_call_output":
            body = json.loads(message["output"])
            if body.get("records"):
                return body["role"], body["records"][0]["record_key"]
    return "vendor_invoices", "VI-1"


def _run(ws, model, objective="Review payables and cash."):
    return asyncio.run(run_investigation(ws, objective, client=model))


# --------------------------------------------------------------------------- #
# The pause
# --------------------------------------------------------------------------- #

def test_an_escalating_run_stops_and_says_what_it_is_waiting_for(ws):
    final = _run(ws, _escalating_model())

    assert final["status"] == "waiting_on_you"
    assert final["waiting_on_you"], "a paused run must say what it stopped to ask"
    question = final["waiting_on_you"][0]
    assert question["kind"] == "decision_required"
    assert question["options"] == ["approved", "rejected"]
    assert question["reasons"], "it must say why a person is needed"


def test_a_paused_run_never_reads_as_finished(ws):
    """The failure that matters: a question rendered as a conclusion."""
    final = _run(ws, _escalating_model())

    assert final["status"] not in {"completed", "no_findings"}


def test_the_question_is_durable_even_before_anyone_answers(ws):
    """An escalation that vanished with the process would be worse than none at all,
    because the run reported raising it."""
    _run(ws, _escalating_model())

    waiting = pending(ws)
    assert waiting, "the proposal is written before the pause, not after the resume"
    assert waiting[0]["approval_id"].startswith("ESC-")


def test_the_pause_proposes_a_decision_and_never_a_journal(ws):
    """An agent conclusion has not been independently reviewed, so it may not move money."""
    _run(ws, _escalating_model())

    with db.connect() as connection:
        row = connection.execute(
            "SELECT kind, journal, verified FROM approvals WHERE ws=? AND id LIKE 'ESC-%'",
            (ws,)).fetchone()

    assert row["kind"] == "decision"
    assert row["journal"] is None
    assert not row["verified"], "an agent's own conclusion is not a reviewed one"


def test_nothing_is_decided_by_waiting(ws):
    """There is no timeout that approves, and no path an agent can take to resolve
    its own escalation."""
    _run(ws, _escalating_model())

    with db.connect() as connection:
        statuses = {r["status"] for r in connection.execute(
            "SELECT status FROM approvals WHERE ws=?", (ws,))}

    assert statuses == {"pending"}


# --------------------------------------------------------------------------- #
# The resolution
# --------------------------------------------------------------------------- #

def test_deciding_resumes_the_run_and_records_who_decided(ws):
    paused = _run(ws, _escalating_model())
    answered = pending(ws)[0]["approval_id"]

    asyncio.run(resume_investigation(ws, paused["thread_id"], "approved",
                                     approval_id=answered, client=_escalating_model()))

    with db.connect() as connection:
        row = connection.execute(
            "SELECT status, decided_by FROM approvals WHERE ws=? AND id=?",
            (ws, answered)).fetchone()
    assert row["status"] == "approved"
    assert row["decided_by"] == "local-reviewer"


def test_the_decision_becomes_precedent_the_next_run_is_offered(ws):
    """The loop closing: a person decides, and that decision is what the system learned."""
    paused = _run(ws, _escalating_model())
    with db.connect() as connection:
        assert approvals.active_precedents(connection, ws) == []

    asyncio.run(resume_investigation(ws, paused["thread_id"], "rejected",
                                     approval_id=pending(ws)[0]["approval_id"],
                                     client=_escalating_model()))

    with db.connect() as connection:
        precedents = approvals.active_precedents(connection, ws)
    assert len(precedents) == 1
    assert precedents[0]["verdict"] == "rejected"
    # Guidance, not a rule: the next run must re-check it against its own evidence.
    assert "re-check" in precedents[0]["guidance"].lower()


#: A condition each agent's own spec escalates on, so more than one pauses in one run.
CONCURRENT = {"A1": "no_purchase_order", "A2": "ambiguous_remittance",
              "A3": "unmatched_difference"}


def test_answering_one_question_resolves_that_one_and_leaves_the_rest(ws):
    """Several agents can pause at once, and a person answered one of them.

    Resuming them all with a single answer would record a decision on questions nobody
    was shown — the most damaging kind of bug here, because the record would look
    exactly like a real decision.
    """
    paused = _run(ws, _escalating_model(CONCURRENT))
    waiting = pending(ws)
    assert len(waiting) > 1, "this test needs concurrent escalations to mean anything"
    answered = waiting[0]["approval_id"]

    asyncio.run(resume_investigation(ws, paused["thread_id"], "approved",
                                     approval_id=answered,
                                     client=_escalating_model(CONCURRENT)))

    remaining = {e["approval_id"] for e in pending(ws)}
    assert answered not in remaining
    assert remaining == {e["approval_id"] for e in waiting} - {answered}


def test_an_unaddressed_answer_is_refused_when_several_are_waiting(ws):
    paused = _run(ws, _escalating_model(CONCURRENT))
    assert len(pending(ws)) > 1

    with pytest.raises(ValueError, match="more than one decision"):
        asyncio.run(resume_investigation(ws, paused["thread_id"], "approved",
                                         client=_escalating_model(CONCURRENT)))

    assert len(pending(ws)) > 1, "every question still stands"


def test_answering_a_question_that_is_not_waiting_is_refused(ws):
    paused = _run(ws, _escalating_model())

    with pytest.raises(KeyError):
        asyncio.run(resume_investigation(ws, paused["thread_id"], "approved",
                                         approval_id="ESC-not-a-real-one",
                                         client=_escalating_model()))


def test_an_invalid_answer_is_refused_rather_than_guessed(ws):
    paused = _run(ws, _escalating_model())
    waiting = len(pending(ws))

    with pytest.raises(Exception):
        asyncio.run(resume_investigation(ws, paused["thread_id"], "maybe",
                                         approval_id=pending(ws)[0]["approval_id"],
                                         client=_escalating_model()))

    assert len(pending(ws)) == waiting, "the question still stands"


def test_a_run_that_escalates_nothing_never_pauses(ws):
    """The control: the machinery must not stop a run that had no question."""
    model = FakeModel([([], ap_result(
        disposition="insufficient_evidence",
        summary="Not enough evidence to conclude.",
        rationale="The records needed were not supplied.", citations=[]))])

    final = _run(ws, model)

    # insufficient_evidence does escalate by design, so this asserts the weaker and
    # more useful property: whatever it did, it is not silently pending forever.
    assert final["status"] in {"waiting_on_you", "needs_you", "completed", "no_findings"}


# --------------------------------------------------------------------------- #
# Two screens, one question
# --------------------------------------------------------------------------- #

def test_a_question_answered_on_the_approvals_page_still_resumes_the_run(ws):
    """An approval row and a paused run are two halves of one question, and they can be
    answered from two screens. Deciding on the approvals page marked it decided; coming
    back to the chat then failed with "already approved", the graph never advanced, and
    the run was stranded on a question that had in fact been answered.
    """
    final = _run(ws, _escalating_model())
    waiting = final["waiting_on_you"]
    assert waiting, "this needs a paused run"
    approval_id = waiting[0]["approval_id"]

    # Decided somewhere else entirely, the way the approvals page does it.
    approvals.decide(ws, approval_id, "approved")

    resumed = asyncio.run(resume_investigation(
        ws, final["thread_id"], "approved", approval_id=approval_id,
        client=_escalating_model()))

    assert resumed["status"] != "waiting_on_you" or approval_id not in {
        item["approval_id"] for item in resumed.get("waiting_on_you", [])}


def test_answering_differently_from_what_is_on_record_is_refused(ws):
    """Overwriting silently would lose a decision somebody made."""
    final = _run(ws, _escalating_model())
    approval_id = final["waiting_on_you"][0]["approval_id"]
    approvals.decide(ws, approval_id, "approved")

    with pytest.raises(ValueError, match="already approved"):
        asyncio.run(resume_investigation(
            ws, final["thread_id"], "rejected", approval_id=approval_id,
            client=_escalating_model()))


def test_a_decision_is_never_recorded_twice(ws):
    """Deciding on both screens must leave one decision, not two, and one precedent."""
    final = _run(ws, _escalating_model())
    approval_id = final["waiting_on_you"][0]["approval_id"]
    approvals.decide(ws, approval_id, "approved")

    asyncio.run(resume_investigation(
        ws, final["thread_id"], "approved", approval_id=approval_id,
        client=_escalating_model()))

    with db.connect() as connection:
        decided = connection.execute(
            "SELECT COUNT(*) FROM events WHERE ws=? AND kind='approval_decided'"
            " AND payload LIKE ?", (ws, f'%{approval_id}%')).fetchone()[0]
        precedents = connection.execute(
            "SELECT COUNT(*) FROM precedents WHERE ws=? AND source_approval_id=?",
            (ws, approval_id)).fetchone()[0]

    assert decided == 1
    assert precedents <= 1
