#!/usr/bin/env python
"""Manual smoke test: ask the Internal Auditor to independently review a finding.

Usage:
    uv run python scripts/ask_auditor.py F-11

Reads OPENAI_API_KEY from api/.env (gitignored) or the environment. Makes a
real, billed API call; not part of the test suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app import store  # noqa: E402
from app.agents.run_loop import run_auditor_agent  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/ask_auditor.py <finding_id>")
        raise SystemExit(1)
    finding_id = sys.argv[1]

    bundle = store.get_bundle("sandbox")
    finding = next((f for f in bundle.findings if f.id == finding_id), None)
    if finding is None:
        print(f"No such finding: {finding_id}")
        raise SystemExit(1)

    print(f"Finding {finding_id}: [{finding.status}] {finding.title}")
    print(f"Filed by: {finding.agent}, currently verified_by: {finding.verified_by}\n")

    question = (
        f"Independently review finding {finding_id}. Re-read the original invoice/vendor/PO/approval "
        "records yourself with your own tool calls — do not just agree with the summary. Then call "
        "submit_review with your decision."
    )
    result = run_auditor_agent(question)

    print("=== Auditor's answer ===")
    print(result.answer or "(no final answer text)")
    print(f"\nStop reason: {result.stop_reason}")
    print(f"Tool calls used: {result.tool_calls_used}/{result.tool_budget}")
    for call in result.tool_calls:
        print(f"  - {call['tool']}({call['input']}) -> {call['output']}")

    after = store.get_bundle("sandbox")
    updated = next(f for f in after.findings if f.id == finding_id)
    print(f"\nFinding {finding_id} is now: [{updated.status}] verified_by={updated.verified_by}")


if __name__ == "__main__":
    main()
