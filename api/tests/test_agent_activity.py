"""The board is written while the work happens, not reconstructed after it.

The task board used to be derived from `agent_decisions`, which is only written once a
task is over. Every card therefore arrived finished: column `done`, progress 100, zero
tool calls, one step that was a copy of the summary. These tests pin the properties that
made that impossible to notice — a card exists while its agent is working, its steps are
the tool calls it actually made, and a task that ends without a result says so instead
of spinning forever.

No provider is called. `FakeModel` from the runtime tests replays a scripted exchange,
so what is under test is what the runtime records rather than what a model says.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app import db, ingestion, projection
from app.agents import activity, schemas
from app.agents.budget import Meter
from app.agents.registry import AGENTS
from app.agents.runtime import AgentFailed, run_agent
from tests.conftest import SAMPLE_FILES
from tests.test_agent_runtime import FakeModel, ap_result, invoice_key


@pytest.fixture
def ws(tmp_path, monkeypatch) -> str:
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    created = ingestion.create_workspace(ingestion.WorkspaceCreate(
        name="Fictional SaaS company", start="2026-09-01", end="2026-09-30",
        scope="September close",
        settings={"approval_limit_cents": 500_000, "materiality_cents": 100_000},
    ))
    workspace = created["id"]
    files = [f for f in SAMPLE_FILES if not f.get("later")]
    batch = ingestion.stage(workspace, [
        (f["name"], f["content"].encode(), ingestion.FileOptions(role=f["role"]))
        for f in files])
    ingestion.commit(workspace, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="activity"))
    return workspace


def matched_run(ws: str):
    """A1 reads its invoice, matches it, and concludes. Two real tool calls."""
    key = invoice_key(ws, "INV-100")
    model = FakeModel([
        ([("read_records", {"role": "vendor_invoices"}),
          ("three_way_match", {"invoice_key": key})], None),
        ([], ap_result(citations=[schemas.Citation(role="vendor_invoices", record_key=key)])),
    ])
    return asyncio.run(run_agent(ws, "A1", "Review invoice INV-100", meter=Meter(),
                                 thread_id="t-1", client=model))


def only_task(ws: str) -> dict:
    tasks = activity.board(ws)
    assert len(tasks) == 1, tasks
    return tasks[0]


# --------------------------------------------------------------------------- #
# What a finished task records
# --------------------------------------------------------------------------- #

def test_a_run_writes_one_card_carrying_the_tool_calls_it_actually_made(ws):
    run = matched_run(ws)
    card = only_task(ws)

    assert card["agent"] == "A1"
    assert card["tool_calls"]["used"] == 2, card["steps"]
    assert card["tool_calls"]["budget"] == AGENTS["A1"].budget.tool_calls
    assert card["column"] in {"done", "needs_you"}
    assert card["decision_id"] is None or card["decision_id"] == run.decision_id


def test_the_steps_are_the_work_not_a_restatement_of_the_summary(ws):
    matched_run(ws)
    titles = [step["title"] for step in only_task(ws)["steps"]]

    # The tool calls, in the order they were made, plus the model turns around them.
    assert "Read the records" in titles
    assert "Matched invoice, order and receipt" in titles
    assert "Wrote its conclusion" in titles
    # The old board's single step was the summary text. Nothing here is.
    assert not any(title.startswith("The invoice matches") for title in titles)


def test_a_step_names_what_the_call_was_about(ws):
    matched_run(ws)
    read = next(s for s in only_task(ws)["steps"] if s["title"] == "Read the records")

    assert read["detail"] == "role: vendor_invoices"


def test_an_escalating_run_parks_the_card_on_a_person_with_its_reasons(ws):
    key = invoice_key(ws, "INV-200")  # No order, no receipt: A1 must escalate.
    model = FakeModel([
        ([("read_records", {"role": "vendor_invoices"}),
          ("three_way_match", {"invoice_key": key})], None),
        ([], ap_result(citations=[schemas.Citation(role="vendor_invoices", record_key=key)],
                       may_pay=False)),
    ])
    run = asyncio.run(run_agent(ws, "A1", "Review invoice INV-200", meter=Meter(),
                                thread_id="t-2", client=model))
    card = only_task(ws)

    assert run.escalated and card["column"] == "needs_you"
    assert card["todos"], "the reasons a person is needed belong on the card"
    assert set(card["todos"]) <= set(run.escalation_reasons)
    assert card["note_tone"] == "warn"


# --------------------------------------------------------------------------- #
# What an unfinished task records
# --------------------------------------------------------------------------- #

def test_a_task_that_fails_is_reported_as_stopped_rather_than_left_running(ws):
    """The failure mode that matters: a card that claims to be working when nothing is."""
    model = FakeModel([([], None)])  # No tool calls and no parsed result.

    with pytest.raises(AgentFailed):
        asyncio.run(run_agent(ws, "A1", "Review invoice INV-100", meter=Meter(),
                              thread_id="t-3", client=model))

    with db.connect() as connection:
        row = connection.execute("SELECT state, error FROM agent_tasks WHERE ws=?",
                                 (ws,)).fetchone()
    assert row["state"] == "failed"
    assert "AgentFailed" in row["error"]
    assert only_task(ws)["note"]


def test_a_working_card_that_stopped_reporting_is_not_shown_as_running(ws):
    activity.start(ws, "t-4", "A1", "Review invoice INV-100")
    with db.connect() as connection:
        connection.execute("UPDATE agent_tasks SET updated_at=? WHERE ws=?",
                           ("2020-01-01T00:00:00+00:00", ws))

    card = only_task(ws)
    assert card["column"] == "needs_you"
    assert "No progress recorded" in card["note"]


def test_a_queued_card_claims_no_progress(ws):
    activity.seed(ws, "t-5", ["A1", "A2"], "Look at September")
    cards = {card["agent"]: card for card in activity.board(ws)}

    assert cards["A1"]["column"] == "queued" and cards["A1"]["progress"] == 0
    assert cards["A2"]["tool_calls"]["used"] == 0
    assert cards["A1"]["steps"] == []


def test_seeding_twice_does_not_duplicate_a_card(ws):
    activity.seed(ws, "t-6", ["A1"], "Look at September")
    activity.seed(ws, "t-6", ["A1"], "Look at September")

    assert len(activity.board(ws)) == 1


def test_a_working_card_never_claims_to_be_finished(ws):
    task_id = activity.start(ws, "t-7", "A1", "Review invoice INV-100")
    for _ in range(AGENTS["A1"].budget.tool_calls * 2):
        activity.step(task_id, "Read the records", counts_as_tool=True)

    assert only_task(ws)["progress"] < 100


# --------------------------------------------------------------------------- #
# What the screens read
# --------------------------------------------------------------------------- #

def test_the_bundle_serves_the_same_cards_the_board_does(ws):
    matched_run(ws)
    bundle = projection.bundle(ws)

    assert [task.id for task in bundle.tasks] == [card["id"] for card in activity.board(ws)]
    assert bundle.tasks[0].tool_calls.used == 2


def test_telemetry_never_takes_down_the_work_it_describes(ws):
    """A board write that fails must cost a step, never the run."""
    activity.step("task-that-does-not-exist", "Read the records", counts_as_tool=True)
    activity.finish("task-that-does-not-exist", state="done")


def test_the_endpoint_says_whether_anything_is_still_moving(ws, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    activity.seed(ws, "t-8", ["A1"], "Look at September")
    with TestClient(app) as client:
        view = client.get(f"/api/workspaces/{ws}/agents/activity").json()

    assert view["active"] == 1
    assert view["tasks"][0]["agent"] == "A1"
    assert view["spend"]["day_cap_cents"] > 0
