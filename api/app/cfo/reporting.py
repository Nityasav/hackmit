"""Render money from validated calculations; preserve omissions and disagreements."""

import re

from .schemas import Narrative, Run


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    units, remainder = divmod(abs(cents), 100)
    return f"{sign}${units:,}.{remainder:02d}"


def validate_narrative(narrative: Narrative, run: Run) -> None:
    accepted = {item.claim.id for item in run.accepted}
    ids = [item.claim_id for item in narrative.items]
    if len(ids) != len(set(ids)) or set(ids) != accepted:
        raise ValueError("Narrative must cover every accepted claim exactly once, without adding claims.")
    for item in narrative.items:
        # Financial values are injected by the renderer, never model-authored.
        if re.search(r"[\d$%€£]", item.explanation + item.proposed_next_step):
            raise ValueError("Narrative prose must omit numbers; use the deterministic financial fields.")


def render(run: Run, narrative: Narrative | None = None) -> None:
    scope = run.scope
    explanations = {item.claim_id: item for item in narrative.items} if narrative else {}
    scope_name = f"{scope.institution} — {scope.period}" if scope else run.request.workspace
    run.briefing = (
        f"{scope_name}: {len(run.accepted)} independently reviewed conclusions; "
        f"{len(run.unresolved)} unresolved items. Run status: {run.status}. "
        "No financial changes have been approved or applied by the CFO agent."
    )
    lines = [f"# CFO review — {scope_name}", "", f"Run: {run.id}",
             f"Mode: {run.request.mode}; model: {run.model_label}",
             f"Snapshot: {scope.snapshot_id if scope else 'unavailable'}", "", run.briefing,
             "", "## Reviewed conclusions", ""]
    for item in run.accepted:
        claim = item.claim
        lines += [f"### {claim.id}: {claim.title}", "", claim.conclusion,
                  f"Disposition: {claim.disposition}. Reviewed by Internal Auditor.",
                  "Evidence: " + ", ".join(claim.evidence_ids)]
        if item.calculation:
            calc = item.calculation
            amount = f"{calc.category}: {money(calc.amount_cents)}; cash impact: {money(calc.cash_delta_cents)}"
            lines += [f"Calculation {calc.id}: {amount}."]
            run.briefing += f" {claim.id} — {amount}."
        if claim.id in explanations:
            prose = explanations[claim.id]
            lines += [f"CFO commentary: {prose.explanation}",
                      f"Proposed next step: {prose.proposed_next_step}"]
            run.briefing += f" {claim.id}: {prose.explanation}"
        lines += [f"Proposed owner: {item.role}; proposed action: {claim.proposed_action}",
                  "Dependency: authorized human review before any financial change. Due date: not agreed.", ""]
    if not run.accepted:
        lines += ["No accepted conclusions. This does not imply a clean audit or absence of errors.", ""]
    lines += ["## Unresolved matters", ""]
    lines += [f"- {item}" for item in run.unresolved] or ["- None identified within this run's limited scope."]
    lines += ["", "## Limitations", "",
              "- This is an internal review, not an external audit opinion.",
              "- Reviewer acceptance is not human approval. No ledger entries or payments were applied.",
              "- Citations and calculation provenance are checked in code; semantic claim accuracy still depends on the reviewer.",
              f"- CFO model calls: {run.model_calls}; observed evidence tool calls: {run.tool_calls}.",
              f"- CFO tokens: {run.cfo_input_tokens} input, {run.cfo_output_tokens} output. Specialist model tokens are tracked by specialist adapters."]
    run.report_markdown = "\n".join(lines) + "\n"
