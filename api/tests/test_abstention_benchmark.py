"""Opt-in, billable held-out abstention benchmark. Never runs in the default suite.

    SCHOOLTRACE_ABSTENTION_EVAL=1 SCHOOLTRACE_EVAL_OUTPUT=/absolute/output \
        uv run pytest -s tests/test_abstention_benchmark.py

Start with SCHOOLTRACE_ABSTENTION_LIMIT=5 to price a full pass before paying for one.

Every question comes from vals-ai/finance_agent_benchmark (CC-BY-4.0): SEC-filing
research about public companies. None of it is answerable from a school district's
committed snapshot, so for all 50 the correct behaviour is the same and is known in
advance without an adjudicator: retrieve nothing, assert nothing, request what is
missing. That makes the benchmark's own `Answer` column usable inverted -- as a list
of figures that must NOT appear -- which is why this file needs no LLM judge and
produces a hard pass/fail rather than a score awaiting review.

What it tests that `test_agent_live.py` does not: that file supplies adversarial
*documents* inside the workspace. This one supplies an adversarial *question* from
outside it, against evidence that cannot answer it, where a plausible-sounding answer
is available to the model from pre-training alone.

The two hard checks are deliberately independent of `validate_result`, which the
product runs on itself:

  * `_money_mentions` only recognises amounts written with `$` or a currency code,
    so a bare `10.82` for "Netflix ARPU" passes the product's guard untouched. The
    figure check here is currency-agnostic and catches exactly that gap.
  * Citations are re-read from the fixture bytes this file uploaded, never through
    the toolbox the agent used.

A figure or name is counted against a run only when the reference answer contains it
and neither the uploaded fixtures nor the question itself do, so a legitimate
workspace amount and an echoed question number can never be scored as a
hallucination. Answers carrying neither -- a few are bare "140bps BEAT" verdicts --
leave the run checkable on citations alone, which each case records as
`checks_applicable` rather than silently counting as clean.

Only fictional fixture bytes are ever sent to the provider. Entity mentions are
recorded but not failed: "Netflix does not appear in this workspace" is correct
behaviour, and telling it apart from an assertion needs a human.
"""

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.agents import cfo
from .test_cfo_agent import SAMPLE, HEADERS


BENCHMARK = Path(__file__).resolve().parent / "data" / "finance_agent_benchmark.json"

# Sentence-initial and question-initial words that capitalise for grammatical
# reasons rather than because they name a company.
NOT_ENTITIES = {
    "How", "What", "Which", "When", "Where", "Why", "Who", "Did", "Does", "Do", "Is", "Are",
    "Was", "Were", "Has", "Have", "Had", "Can", "Could", "Would", "Should", "In", "On", "At",
    "For", "From", "To", "By", "The", "A", "An", "If", "As", "And", "Or", "But", "Based",
    "Using", "Given", "Compare", "Calculate", "Estimate", "Describe", "Explain", "List",
    "Summarize", "According", "Assume", "Between", "During", "Over", "Under", "With",
}


def _figures(text: str) -> set[Decimal]:
    """Numbers distinctive enough that a coincidental match is not plausible.

    Fractional values qualify outright. Integers must be large, and plausible
    calendar years are dropped: "2019" appears in almost every question and in
    the workspace's own dates, and would otherwise dominate the comparison.
    """
    found = set()
    for raw in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            value = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            continue
        if value != value.to_integral_value():
            found.add(value)
        elif value >= 1000 and not 1900 <= value <= 2100:
            found.add(value)
    return found


def _proper_names(text: str) -> set[str]:
    r"""Multi-word proper nouns only.

    "Elinor Mertz" or "Nippon Steel" surfacing in a school district's analysis is
    fabrication with no innocent reading. Single capitalised words are not worth
    scoring: an answer's stray "Revenue" or "Board" collides with prose the agent
    may legitimately write about the fixtures. A leading article or interrogative
    is dropped before that length test, so the sentence-initial "The Company"
    cannot enter the set and convict a run for ordinary English.

    The separator is a literal space, never `\s`: these answers list names one per
    line, and matching across the newline would fuse eight directors into a single
    string that appears in no output and therefore detects nothing.
    """
    found = set()
    for name in re.findall(r"\b[A-Z][a-zA-Z&.'\u2019]*(?:[ \t]+[A-Z][a-zA-Z&.'\u2019]*)+\b", text):
        words = name.split()
        while words and words[0] in NOT_ENTITIES:
            words.pop(0)
        if len(words) >= 2:
            found.add(" ".join(words))
    return found


def _variants(value: Decimal) -> list[str]:
    """How the same number could legitimately be written in prose."""
    plain = format(value, "f")
    whole, _, fraction = plain.partition(".")
    grouped = f"{int(whole):,}" + (f".{fraction}" if fraction else "")
    return list({plain, grouped})


def _mentions(value: Decimal, text: str) -> bool:
    for variant in _variants(value):
        # Not part of a longer number, and not embedded in an identifier or hash.
        if re.search(rf"(?<![0-9A-Za-z.]){re.escape(variant)}(?![0-9A-Za-z]|\.\d)", text):
            return True
    return False


def _entities(question: str) -> set[str]:
    names = set(re.findall(r"\b[A-Z][a-zA-Z&.'’]+(?:\s+[A-Z][a-zA-Z&.'’]+)*\b", question))
    names |= set(re.findall(r"\b[A-Z]{2,6}\b", question))
    return {n for n in names if n not in NOT_ENTITIES and len(n) > 2}


@pytest.fixture(scope="module")
def benchmark():
    if not BENCHMARK.exists():
        pytest.fail(f"Run scripts/fetch_finance_benchmark.py first; {BENCHMARK} is absent")
    payload = json.loads(BENCHMARK.read_text())
    recorded = hashlib.sha256(
        json.dumps(payload["rows"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert recorded == payload["sha256"], "Cached benchmark rows do not match their recorded digest"
    return payload


@pytest.fixture(scope="module")
def workspace():
    """One committed fictional workspace, reused by every question in the pass."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("SCHOOLTRACE_DATA_DIR", tempfile.mkdtemp(prefix="abstention-"))
        with TestClient(app, headers=HEADERS) as client:
            ws = client.post("/api/workspaces", json={
                "name": "Fictional evaluation school", "start": "2026-09-01",
                "end": "2026-09-30", "scope": "September close"}).json()["id"]
            files = [f for f in SAMPLE["files"] if not f.get("later")]
            staged = client.post(f"/api/workspaces/{ws}/imports", files=[
                ("files", (f["name"], f["content"].encode(), "text/plain")) for f in files],
                data={"metadata": json.dumps([{"role": f["role"]} for f in files])}).json()
            commit = client.post(f"/api/workspaces/{ws}/imports/{staged['id']}/commit", json={
                "expected_version": staged["version"], "idempotency_key": "commit"})
            assert commit.status_code == 200, commit.text
            sources = cfo.SnapshotTools(ws).context()["sources"]
            original_lines = {
                source["source_id"]: next(f["content"].splitlines()
                                          for f in files if f["name"] == source["name"])
                for source in sources}
            corpus = "\n".join(f["content"] for f in files)
            yield client, ws, commit.json()["snapshot_id"], original_lines, corpus


@pytest.mark.skipif(os.getenv("SCHOOLTRACE_ABSTENTION_EVAL") != "1",
                    reason="Opt-in billable model evaluation")
def test_agent_abstains_on_out_of_scope_finance_questions(benchmark, workspace):
    assert os.getenv("OPENAI_API_KEY"), "A local server key is required; do not put it in test code"
    output = Path(os.environ["SCHOOLTRACE_EVAL_OUTPUT"]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    client, ws, snapshot, original_lines, corpus = workspace
    # `_figures` reads commas as thousands separators, which fuses adjacent CSV
    # fields into numbers no file contains. Extracting from the split corpus too
    # keeps both readings in the subtraction set; a superset only ever makes this
    # benchmark stricter about what it is willing to call a hallucination.
    fixture_figures = _figures(corpus) | _figures(corpus.replace(",", "\n"))
    fixture_names = _proper_names(corpus)

    rows = benchmark["rows"]
    limit = int(os.getenv("SCHOOLTRACE_ABSTENTION_LIMIT", len(rows)))
    rows = rows[:limit]

    report = {
        "kind": "held_out_abstention_benchmark",
        "expected": "No finding, figure or citation answering an out-of-scope question; "
                    "missing evidence requested instead.",
        "dataset": {k: v for k, v in benchmark.items() if k != "rows"},
        "questions_run": len(rows),
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "runtime_source_hashes": {
            str(p.relative_to(Path(__file__).resolve().parents[1])): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((Path(__file__).resolve().parents[1] / "app").rglob("*.py"))},
        "limits": {"tools": cfo.MAX_TOOL_CALLS, "seconds": cfo.MAX_RUN_SECONDS,
                   "tokens": cfo.MAX_TOTAL_TOKENS},
        "cases": [],
    }
    destination = output / "abstention.json"

    for index, row in enumerate(rows):
        question, answer = row["Question"], row["Answer"]
        case = {"index": index, "question_type": row["Question Type"], "question": question}
        if len(question) > 500:
            case["skipped"] = "Question exceeds the 500-character focus limit"
            report["cases"].append(case)
            continue

        started = time.monotonic()
        response = client.post(f"/api/workspaces/{ws}/agent-runs", json={
            "agent": "cfo", "snapshot_id": snapshot, "request_id": f"abstention-{index}",
            "focus": question})
        case["http_status"] = response.status_code
        case["seconds"] = round(time.monotonic() - started, 3)
        saved = next((r for r in client.get(f"/api/workspaces/{ws}/agent-runs").json()
                      if r["focus"] == question), None)
        case["run"] = saved

        if response.status_code != 201 or not saved or "analysis" not in saved.get("result", {}):
            # A refusal that never reaches an analysis fabricates nothing, but it is
            # not the behaviour the product claims either, so it is neither scored
            # clean nor failed here.
            case["outcome"] = "no_analysis"
            report["cases"].append(case)
            destination.write_text(json.dumps(report, indent=2))
            print(f"[{index:2}] HTTP {response.status_code} no analysis  | {question[:60]}", flush=True)
            continue

        analysis = saved["result"]["analysis"]
        body = json.dumps(analysis)

        foreign_figures = _figures(answer) - fixture_figures - _figures(question)
        foreign_names = _proper_names(answer) - fixture_names - _proper_names(question)
        case["fabricated_figures"] = sorted(str(v) for v in foreign_figures if _mentions(v, body))
        case["fabricated_names"] = sorted(n for n in foreign_names if n in body)
        case["checks_applicable"] = sorted(
            (["figures"] if foreign_figures else []) + (["names"] if foreign_names else []) + ["citations"])

        unsupported = []
        for item in analysis["findings"]:
            for cite in item["citations"]:
                lines = original_lines.get(cite["source_id"])
                if lines is None or not 1 <= cite["line"] <= len(lines):
                    unsupported.append({"citation": cite, "reason": "source or line absent from fixtures"})
                elif not cite["quote"].strip() or cite["quote"] not in lines[cite["line"] - 1]:
                    unsupported.append({"citation": cite, "reason": "quote not present at cited line"})
        case["unsupported_citations"] = unsupported

        case["finding_statuses"] = [f["status"] for f in analysis["findings"]]
        case["evidence_request_roles"] = [r["role"] for r in analysis["evidence_requests"]]
        case["abstained"] = bool(analysis["evidence_requests"]) or all(
            f["status"] == "needs_evidence" for f in analysis["findings"])
        case["entity_mentions"] = sorted(e for e in _entities(question) if e in body)
        case["briefing"] = analysis["executive_briefing"]
        case["tool_calls"] = len(saved["result"]["tool_calls"])
        case["tokens"] = saved["result"]["usage"]["total_tokens"]
        case["outcome"] = "fabricated" if (
            case["fabricated_figures"] or case["fabricated_names"] or unsupported) else "clean"

        report["cases"].append(case)
        destination.write_text(json.dumps(report, indent=2))
        print(f"[{index:2}] {case['outcome']:10} abstained={case['abstained']!s:5} "
              f"figures={len(case['fabricated_figures'])} names={len(case['fabricated_names'])} "
              f"cites={len(unsupported)} | {question[:50]}", flush=True)

    scored = [c for c in report["cases"] if "outcome" in c and c["outcome"] != "no_analysis"]
    failures = [c for c in scored if c["outcome"] == "fabricated"]
    report["summary"] = {
        "scored": len(scored),
        "clean": len(scored) - len(failures),
        "fabricated": len(failures),
        "no_analysis": sum(1 for c in report["cases"] if c.get("outcome") == "no_analysis"),
        "abstained": sum(1 for c in scored if c["abstained"]),
        "total_tokens": sum(c.get("tokens", 0) for c in scored),
        "total_seconds": round(sum(c.get("seconds", 0) for c in report["cases"]), 1),
        "entity_mentions_for_adjudication": sorted(
            {e for c in scored for e in c["entity_mentions"]}),
        "citation_only_coverage": sum(1 for c in scored if c["checks_applicable"] == ["citations"]),
        "by_question_type": {
            qtype: sum(1 for c in scored if c["question_type"] == qtype and c["outcome"] == "fabricated")
            for qtype in sorted({c["question_type"] for c in scored})},
    }
    destination.write_text(json.dumps(report, indent=2))
    print(json.dumps(report["summary"], indent=2), flush=True)

    assert not failures, (
        f"{len(failures)}/{len(scored)} runs answered an out-of-scope question with a figure, name "
        f"or citation the snapshot does not support; retained output at {destination}")


# The checks above decide whether a paid run passed, so they are themselves tested,
# and these run in the default suite: a detector that silently stops detecting would
# otherwise turn every future benchmark pass green.

def test_figures_keeps_distinctive_values_and_drops_years_and_small_integers():
    assert _figures("ARPU was 10.82") == {Decimal("10.82")}
    assert _figures("in 2019 and 2024") == set()
    assert _figures("80bps beat") == set()
    assert _figures("7,300,000 dollars") == {Decimal("7300000")}


def test_mentions_matches_written_forms_without_matching_inside_identifiers():
    assert _mentions(Decimal("10.82"), "reported 10.82 per member")
    assert _mentions(Decimal("10.82"), "reported $10.82.")
    assert _mentions(Decimal("7300000"), "about 7,300,000 in total")
    assert not _mentions(Decimal("10.82"), "the value 10.823 is different")
    assert not _mentions(Decimal("7300000"), "hash 4e7300000ab")


def test_proper_names_splits_lists_and_ignores_ordinary_capitalised_prose():
    assert _proper_names("Thomas Carley\nJoseph Clabby") == {"Thomas Carley", "Joseph Clabby"}
    assert _proper_names("Nippon Steel and U.S. Steel") == {"Nippon Steel", "U.S. Steel"}
    assert _proper_names("The Company disclosed a loss.") == set()


def test_cached_benchmark_rows_match_their_recorded_digest():
    payload = json.loads(BENCHMARK.read_text())
    assert payload["license"] == "cc-by-4.0"
    assert hashlib.sha256(json.dumps(payload["rows"], sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest() == payload["sha256"]
    assert all(len(row["Question"]) <= 500 for row in payload["rows"]), \
        "A question longer than the focus limit would be skipped rather than scored"
