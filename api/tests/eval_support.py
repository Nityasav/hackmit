"""Shared machinery for the opt-in agent evaluations. Imported, never collected.

Both evaluations grade the same way and must keep grading independently of the
product: citations are re-read from the bytes the evaluation itself uploaded, and
figures are compared against what those bytes contain, never against what
`SnapshotTools.validate_result` was willing to accept. A benchmark that asked the
system under test whether it had passed would measure nothing.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.agents import cfo

DATA = Path(__file__).resolve().parent / "data"
HEADERS = {"X-SchoolTrace-Reviewer": "local-reviewer"}

MONEY_IN = DATA / "money_in"
MONEY_IN_ROLES = {"fees.csv": "fees", "collections.csv": "collections",
                  "deposits.csv": "deposits", "sponsorships.csv": "sponsorships"}

# Sentence-initial and question-initial words that capitalise for grammatical
# reasons rather than because they name a company.
NOT_ENTITIES = {
    "How", "What", "Which", "When", "Where", "Why", "Who", "Did", "Does", "Do", "Is", "Are",
    "Was", "Were", "Has", "Have", "Had", "Can", "Could", "Would", "Should", "In", "On", "At",
    "For", "From", "To", "By", "The", "A", "An", "If", "As", "And", "Or", "But", "Based",
    "Using", "Given", "Compare", "Calculate", "Estimate", "Describe", "Explain", "List",
    "Summarize", "According", "Assume", "Between", "During", "Over", "Under", "With",
}


def figures(text: str) -> set[Decimal]:
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


def money_amounts(text: str) -> set[int]:
    """Every money-shaped amount in `text`, in integer cents.

    Deliberately not `figures`. That one keeps only values distinctive enough that a
    coincidental match is implausible, which is right when scanning free prose for a
    leaked number but wrong here: a rubric criterion says "USD 150.00", and dropping
    it for being small and round would report a blocked criterion as an ordinary
    miss. Two decimal places is the money signal, and it also keeps dates out --
    2026-09-11 has no such group.
    """
    return {int(Decimal(raw.replace(",", "")) * 100)
            for raw in re.findall(r"\d[\d,]*\.\d{2}\b", text)}


def proper_names(text: str) -> set[str]:
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
    for name in re.findall(r"\b[A-Z][a-zA-Z&.'’]*(?:[ \t]+[A-Z][a-zA-Z&.'’]*)+\b", text):
        words = name.split()
        while words and words[0] in NOT_ENTITIES:
            words.pop(0)
        if len(words) >= 2:
            found.add(" ".join(words))
    return found


def variants(value: Decimal) -> list[str]:
    """How the same number could legitimately be written in prose."""
    plain = format(value, "f")
    whole, _, fraction = plain.partition(".")
    grouped = f"{int(whole):,}" + (f".{fraction}" if fraction else "")
    return list({plain, grouped})


def mentions(value: Decimal, text: str) -> bool:
    for variant in variants(value):
        # Not part of a longer number, and not embedded in an identifier or hash.
        if re.search(rf"(?<![0-9A-Za-z.]){re.escape(variant)}(?![0-9A-Za-z]|\.\d)", text):
            return True
    return False


def upload_pack(client, name: str, files: list[tuple[str, bytes, str]], start="2026-09-01", end="2026-09-30"):
    """Create a workspace and commit `files` through the real intake path.

    Returns the workspace id, the snapshot id, and the uploaded lines per source
    id, which is what every citation is later checked against.
    """
    ws = client.post("/api/workspaces", json={
        "name": name, "start": start, "end": end, "scope": "September close"}).json()["id"]
    staged = client.post(f"/api/workspaces/{ws}/imports", files=[
        ("files", (filename, content, "text/csv")) for filename, content, _ in files],
        data={"metadata": json.dumps([{"role": role} for _, _, role in files])}).json()
    commit = client.post(f"/api/workspaces/{ws}/imports/{staged['id']}/commit", json={
        "expected_version": staged["version"], "idempotency_key": f"{staged['id']}:1"})
    assert commit.status_code == 200, commit.text
    by_name = {filename: content.decode().splitlines() for filename, content, _ in files}
    original_lines = {source["source_id"]: by_name[source["name"]]
                      for source in cfo.SnapshotTools(ws).context()["sources"]}
    return ws, commit.json()["snapshot_id"], original_lines


def money_in_files() -> list[tuple[str, bytes, str]]:
    return [(name, (MONEY_IN / name).read_bytes(), role) for name, role in MONEY_IN_ROLES.items()]


def unsupported_citations(analysis: dict, original_lines: dict[str, list[str]]) -> list[dict]:
    """Citations that do not quote the bytes this evaluation uploaded."""
    problems = []
    for item in analysis["findings"]:
        for cite in item["citations"]:
            lines = original_lines.get(cite["source_id"])
            if lines is None or not 1 <= cite["line"] <= len(lines):
                problems.append({"citation": cite, "reason": "source or line absent from fixtures"})
            elif not cite["quote"].strip() or cite["quote"] not in lines[cite["line"] - 1]:
                problems.append({"citation": cite, "reason": "quote not present at cited line"})
    return problems


def reachable_amounts(ws: str) -> set[int]:
    """Every amount in cents the agent could get past `validate_result`, in cents.

    An upper bound: it reads every source in full and pages every record role the
    tool schema exposes, which no real run within its call budget would manage.
    A rubric criterion naming an amount outside this set is asking for something
    the agent cannot state at any level of competence -- `validate_result` rejects
    the submission -- so the harness reports it as blocked rather than as wrong.
    """
    toolbox = cfo.SnapshotTools(ws)
    toolbox.context()
    for source in toolbox.list_sources("all"):
        toolbox.read_source_span(source["source_id"], 1, source["line_count"])
    roles = [t for t in cfo._tools() if t["name"] == "list_records"][0]
    for role in roles["parameters"]["properties"]["role"]["enum"]:
        offset = 0
        while True:
            page = toolbox.list_records(role, 100, offset)
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
    for calculation in (toolbox.compute_ledger_totals, toolbox.compute_money_in_checks):
        try:
            calculation()
        except Exception:
            # A pack carrying none of a calculation's roles, or on another accounting
            # profile, simply has no amounts to reach through it.
            pass
    return {int(a) for a in toolbox.allowed_amounts}
