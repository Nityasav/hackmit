#!/usr/bin/env python
"""Manual smoke test: ask the AP & Payments agent a real question via a live OpenAI call.

Usage:
    uv run python scripts/ask_ap_agent.py "Should invoice INV-2302 be paid?"

Reads OPENAI_API_KEY from api/.env (gitignored — never commit it) or the process
environment. This makes a real, billed API call; it is not part of the test suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app import store  # noqa: E402
from app.agents.run_loop import run_ap_agent  # noqa: E402

DEFAULT_QUESTION = (
    "Should invoice INV-2302 be paid? Investigate using the available tools and explain your reasoning."
)


def main() -> None:
    question = " ".join(sys.argv[1:]) or DEFAULT_QUESTION
    print(f"Question: {question}\n")

    before = store.get_bundle("sandbox")
    seen_findings = {f.id for f in before.findings}
    seen_approvals = {a.id for a in before.approvals}

    result = run_ap_agent(question)

    print("=== Answer ===")
    print(result.answer or "(no final answer text — see stop reason below)")
    print()
    print(f"Stop reason: {result.stop_reason}")
    print(f"Tool calls used: {result.tool_calls_used}/{result.tool_budget}")
    if result.tool_calls:
        print("\nTool calls:")
        for call in result.tool_calls:
            print(f"  - {call['tool']}({call['input']}) -> {call['output']}")

    after = store.get_bundle("sandbox")
    new_findings = [f for f in after.findings if f.id not in seen_findings]
    new_approvals = [a for a in after.approvals if a.id not in seen_approvals]
    if new_findings or new_approvals:
        print("\n=== What this run added to the bundle ===")
        for finding in new_findings:
            print(f"  finding {finding.id}: [{finding.status}] {finding.title}")
            print(f"    verified_by: {finding.verified_by} (auditor sets this, not the agent)")
        for approval in new_approvals:
            print(f"  approval {approval.id}: [{approval.kind}/{approval.status}] {approval.title}")


if __name__ == "__main__":
    main()
