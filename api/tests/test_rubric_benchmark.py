"""Opt-in, billable rubric benchmark over this project's own fixtures.

    SCHOOLTRACE_RUBRIC_EVAL=1 SCHOOLTRACE_EVAL_OUTPUT=/absolute/output \
        SCHOOLTRACE_JUDGE_MODEL=<a model that is not the one under test> \
        uv run pytest -s tests/test_rubric_benchmark.py

The abstention benchmark next door asks whether the agent stays quiet about things
it cannot know. This one asks the harder question: when the answer *is* in the
workspace, does the agent actually produce it. Rows live in `tests/data/rubric/`
in the column layout of vals-ai/finance_agent_benchmark -- Question, Answer,
Question Type, Expert time (mins), Rubric -- so a rubric written here and a rubric
written there are graded by the same code.

Three operators. `correctness` and `contradiction` are the upstream pair: the
response should assert the criterion, and must not contradict the reference text.
`prohibition` is a local addition, because a finding is something a person acts on
and the dangerous failures here are assertions that should never have been made --
calling a reconciling difference stolen money, summing four amounts that measure
different things. An upstream research benchmark has no need for that operator.

Scoring separates three outcomes that a single percentage would blur:

  * **met** -- the judge found the criterion asserted.
  * **unmet** -- the agent could have satisfied it and did not.
  * **blocked** -- the criterion names a monetary amount that `validate_result`
    would reject whatever the agent wrote, because no tool in the agent's schema
    can put that amount within reach. `reachable_amounts` computes that set as an
    upper bound. Two of this pack's four planted amounts are derived totals with
    no money-in calculation tool behind them, so they are blocked, and counting
    them as ordinary misses would quietly blame the model for a gap in the tools.

Only the objective checks gate the test: a contradiction, a prohibition breach, or
a citation that does not quote the uploaded bytes fails the run. The correctness
percentage is reported, not asserted, unless SCHOOLTRACE_RUBRIC_FLOOR is set. A
judge's reading of natural-language criteria drifts between model versions, and a
suite that fails on that drift is one people learn to ignore.
"""

import ast
import hashlib
import json
import os
import subprocess
import time
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.agents import cfo
from . import eval_support as support


ROWS = support.DATA / "rubric"

JUDGE_INSTRUCTIONS = """You grade one response from a financial investigation agent against a rubric.

For each criterion you are given an operator. Apply it exactly:

- correctness: met=true only if the response actually asserts this. A response that
  neither states nor denies it is met=false. Do not credit a near miss: a different
  amount, a different record id or a hedge that stops short of the claim is met=false.
- contradiction: met=true only if the response states something that cannot be true
  alongside the reference text. Silence is not contradiction. A response that omits
  part of the reference text is met=false; only an actual conflict is met=true.
- prohibition: met=true if the response asserts the described thing. This is the
  behaviour that must not appear, so met=true is a failure.

Judge only what the response says. Do not use your own knowledge of the underlying
records, and do not reward fluent writing. `evidence` must quote the response
verbatim where met=true, and be empty where met=false."""

JUDGE_TOOL = {
    "type": "function", "name": "report_verdicts", "strict": True,
    "description": "Report one verdict per criterion, in the order given.",
    "parameters": {"type": "object", "additionalProperties": False, "required": ["verdicts"],
                   "properties": {"verdicts": {"type": "array", "items": {
                       "type": "object", "additionalProperties": False,
                       "required": ["index", "met", "evidence"],
                       "properties": {"index": {"type": "integer"},
                                      "met": {"type": "boolean"},
                                      "evidence": {"type": "string"}}}}}},
}


def rubric_of(row: dict) -> list[dict]:
    """Accept both this project's JSON rubrics and the upstream repr strings.

    vals-ai ships `Rubric` as a Python repr with single quotes, which `json.loads`
    cannot read; rows authored here are ordinary JSON. Taking both means one judge
    grades either source.
    """
    rubric = row["Rubric"]
    if isinstance(rubric, list):
        return rubric
    try:
        return json.loads(rubric)
    except json.JSONDecodeError:
        return ast.literal_eval(rubric)


def response_text(analysis: dict) -> str:
    """The agent's answer as prose, without the scaffolding a judge should ignore."""
    parts = [analysis["executive_briefing"], f"Scope assessed: {analysis['scope_assessed']}"]
    for finding in analysis["findings"]:
        cites = "; ".join(f"{c['source_id']}:{c['line']} \"{c['quote']}\"" for c in finding["citations"])
        parts.append(f"Finding [{finding['status']}] {finding['title']}: {finding['summary']} "
                     f"Citations: {cites or 'none'}. "
                     f"Limitations: {'; '.join(finding['limitations']) or 'none'}.")
    for request in analysis["evidence_requests"]:
        parts.append(f"Evidence requested ({request['role']}): {request['title']} -- {request['reason']}")
    parts.append(f"Limitations: {'; '.join(analysis['limitations']) or 'none'}.")
    return "\n".join(parts)


def grade(client, model: str, question: str, response: str, criteria: list[dict]) -> list[dict]:
    listing = "\n".join(f"[{i}] ({c['operator']}) {c['criteria']}" for i, c in enumerate(criteria))
    reply = client.responses.create(
        model=model, instructions=JUDGE_INSTRUCTIONS, tools=[JUDGE_TOOL],
        tool_choice="required", parallel_tool_calls=False, store=False, timeout=120,
        input=[{"role": "user", "content":
                f"QUESTION PUT TO THE AGENT:\n{question}\n\n"
                f"AGENT RESPONSE:\n{response}\n\nCRITERIA:\n{listing}"}])
    call = next(item for item in reply.output if getattr(item, "type", None) == "function_call")
    verdicts = {v["index"]: v for v in json.loads(call.arguments)["verdicts"]}
    assert len(verdicts) == len(criteria), f"Judge returned {len(verdicts)} verdicts for {len(criteria)} criteria"
    return [verdicts[i] for i in range(len(criteria))]


@pytest.fixture(scope="module")
def suite():
    path = ROWS / os.getenv("SCHOOLTRACE_RUBRIC_SUITE", "money_in.json")
    if not path.exists():
        pytest.fail(f"No rubric suite at {path}")
    return json.loads(path.read_text())


@pytest.mark.skipif(os.getenv("SCHOOLTRACE_RUBRIC_EVAL") != "1",
                    reason="Opt-in billable model evaluation")
def test_agent_answers_its_own_fixtures(suite, tmp_path, monkeypatch):
    from openai import OpenAI

    assert os.getenv("OPENAI_API_KEY"), "A local server key is required; do not put it in test code"
    output = Path(os.environ["SCHOOLTRACE_EVAL_OUTPUT"]).resolve()
    output.mkdir(parents=True, exist_ok=True)

    under_test = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
    judge_model = os.environ.get("SCHOOLTRACE_JUDGE_MODEL", "")
    assert judge_model, "Set SCHOOLTRACE_JUDGE_MODEL; a rubric score needs a named judge"
    if judge_model == under_test:
        # A model grading its own transcript marks its own phrasing as correct far
        # more often than an independent reader does. Allowed, but never by default.
        assert os.getenv("SCHOOLTRACE_ALLOW_SELF_JUDGE") == "1", (
            f"Judge and agent are both {under_test}; set SCHOOLTRACE_ALLOW_SELF_JUDGE=1 to accept that")

    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    floor = float(os.getenv("SCHOOLTRACE_RUBRIC_FLOOR", "0"))
    judge = OpenAI(timeout=120, max_retries=1, base_url="https://api.openai.com/v1")

    with TestClient(app, headers=support.HEADERS) as client:
        ws, snapshot, original_lines = support.upload_pack(
            client, "Fictional evaluation school", support.money_in_files())
        reachable = support.reachable_amounts(ws)

        report = {
            "kind": "rubric_benchmark",
            "suite": suite.get("pack"),
            "suite_note": suite.get("note"),
            "model_under_test": under_test,
            "judge_model": judge_model,
            "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "runtime_source_hashes": {
                str(p.relative_to(Path(__file__).resolve().parents[1])): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((Path(__file__).resolve().parents[1] / "app").rglob("*.py"))},
            "reachable_amounts_cents": sorted(reachable),
            "cases": [],
        }
        destination = output / "rubric.json"

        for index, row in enumerate(suite["rows"]):
            criteria = rubric_of(row)
            case = {"index": index, "question_type": row["Question Type"],
                    "question": row["Question"], "expert_minutes": row["Expert time (mins)"]}

            # A criterion naming an amount no tool can bring within reach is blocked
            # before the agent is asked, so a miss on it is never read as a mistake.
            case["blocked_criteria"] = [
                {"index": i, "criteria": c["criteria"],
                 "unreachable_cents": sorted(support.money_amounts(c["criteria"]) - reachable)}
                for i, c in enumerate(criteria)
                if c["operator"] == "correctness"
                and support.money_amounts(c["criteria"]) - reachable]

            started = time.monotonic()
            response = client.post(f"/api/workspaces/{ws}/agent-runs", json={
                "agent": suite.get("agent", "cfo"), "snapshot_id": snapshot,
                "request_id": f"rubric-{index}", "focus": row["Question"]})
            case["http_status"] = response.status_code
            case["seconds"] = round(time.monotonic() - started, 3)
            saved = next((r for r in client.get(f"/api/workspaces/{ws}/agent-runs").json()
                          if r["focus"] == row["Question"]), None)
            case["run"] = saved

            if response.status_code != 201 or not saved or "analysis" not in saved.get("result", {}):
                case["outcome"] = "no_analysis"
                report["cases"].append(case)
                destination.write_text(json.dumps(report, indent=2))
                print(f"[{index}] HTTP {response.status_code} no analysis | {row['Question'][:50]}", flush=True)
                continue

            analysis = saved["result"]["analysis"]
            answer = response_text(analysis)
            case["agent_response"] = answer
            case["unsupported_citations"] = support.unsupported_citations(analysis, original_lines)
            case["tool_calls"] = len(saved["result"]["tool_calls"])
            case["tokens"] = saved["result"]["usage"]["total_tokens"]

            verdicts = grade(judge, judge_model, row["Question"], answer, criteria)
            blocked = {b["index"] for b in case["blocked_criteria"]}
            scored = []
            for i, (criterion, verdict) in enumerate(zip(criteria, verdicts)):
                scored.append({"index": i, "operator": criterion["operator"],
                               "criteria": criterion["criteria"], "met": verdict["met"],
                               "evidence": verdict["evidence"], "blocked": i in blocked})
            case["verdicts"] = scored

            correctness = [v for v in scored if v["operator"] == "correctness" and not v["blocked"]]
            case["correctness_met"] = sum(1 for v in correctness if v["met"])
            case["correctness_total"] = len(correctness)
            case["correctness_score"] = (round(case["correctness_met"] / len(correctness), 3)
                                         if correctness else None)
            case["blocked_and_missed"] = [v["criteria"] for v in scored if v["blocked"] and not v["met"]]
            case["contradictions"] = [v["criteria"] for v in scored
                                      if v["operator"] == "contradiction" and v["met"]]
            case["prohibition_breaches"] = [v["criteria"] for v in scored
                                            if v["operator"] == "prohibition" and v["met"]]
            case["outcome"] = "fail" if (case["contradictions"] or case["prohibition_breaches"]
                                         or case["unsupported_citations"]) else "pass"

            report["cases"].append(case)
            destination.write_text(json.dumps(report, indent=2))
            print(f"[{index}] {case['outcome']:4} correctness={case['correctness_met']}/"
                  f"{case['correctness_total']} blocked={len(blocked)} "
                  f"contradictions={len(case['contradictions'])} "
                  f"prohibited={len(case['prohibition_breaches'])} "
                  f"cites={len(case['unsupported_citations'])} | {row['Question'][:45]}", flush=True)

        graded = [c for c in report["cases"] if c.get("outcome") in {"pass", "fail"}]
        met = sum(c["correctness_met"] for c in graded)
        total = sum(c["correctness_total"] for c in graded)
        failures = [c for c in graded if c["outcome"] == "fail"]
        report["summary"] = {
            "graded": len(graded),
            "no_analysis": sum(1 for c in report["cases"] if c.get("outcome") == "no_analysis"),
            "passed": len(graded) - len(failures),
            "correctness_met": met, "correctness_total": total,
            "correctness_score": round(met / total, 3) if total else None,
            "blocked_criteria": sum(len(c["blocked_criteria"]) for c in graded),
            "contradictions": sum(len(c["contradictions"]) for c in graded),
            "prohibition_breaches": sum(len(c["prohibition_breaches"]) for c in graded),
            "unsupported_citations": sum(len(c["unsupported_citations"]) for c in graded),
            "total_tokens": sum(c.get("tokens", 0) for c in graded),
        }
        destination.write_text(json.dumps(report, indent=2))
        print(json.dumps(report["summary"], indent=2), flush=True)

        assert not failures, (
            f"{len(failures)}/{len(graded)} cases contradicted the reference answer, asserted a "
            f"prohibited claim, or cited text the sources do not contain; output at {destination}")
        if floor:
            assert report["summary"]["correctness_score"] >= floor, (
                f"Correctness {report['summary']['correctness_score']} below floor {floor}")


def test_every_rubric_suite_is_well_formed():
    """Runs in the default suite: a malformed rubric must not surface as a paid failure."""
    suites = sorted(ROWS.glob("*.json"))
    assert suites, "No rubric suites found"
    for path in suites:
        suite = json.loads(path.read_text())
        assert suite["rows"], f"{path.name} has no rows"
        for row in suite["rows"]:
            for column in ["Question", "Answer", "Question Type", "Expert time (mins)", "Rubric"]:
                assert column in row, f"{path.name}: row missing {column}"
            assert len(row["Question"]) <= 500, f"{path.name}: question exceeds the focus limit"
            criteria = rubric_of(row)
            assert criteria, f"{path.name}: empty rubric"
            for criterion in criteria:
                assert criterion["operator"] in {"correctness", "contradiction", "prohibition"}
                assert criterion["criteria"].strip()
            assert any(c["operator"] == "contradiction" for c in criteria), \
                f"{path.name}: every row needs a contradiction criterion over its reference answer"
