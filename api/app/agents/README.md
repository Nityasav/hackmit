# Agents

Two parallel implementations currently live here, built independently on separate branches and merged
without being unified yet. Consolidate before the next milestone.

- `cfo.py` — a read-only CFO triage slice: OpenAI Responses API, immutable-snapshot scope, bounded
  read-only evidence tools, strict structured submission, citation verification, persisted telemetry.
  Does not yet dispatch to specialists.
- `ap_tools.py` / `ap_write_tools.py` — typed AP & Payments tools (read tools, plus submit_finding /
  request_evidence / prepare_payment_batch). Separation-of-duties rules — an agent can't verify its own
  finding, an approval can only be created `pending` — are enforced in the write-tool code, not the prompt.
- `au_write_tools.py` — the Internal Auditor's submit_review: the only path that may set
  `Finding.verified_by`, and it refuses to let the auditor review its own finding.
- `tool_gateway.py` — OpenAI function-calling schemas (`TOOL_SPECS` / `AUDITOR_TOOL_SPECS`) plus
  per-run tool-call budget enforcement (spec.md §8's default of 12), shared by every role.
- `decision_tools.py` — the shared `record_decision` schema; `run_loop.py` binds its executable side
  per run, since filing a decision needs run-scoped context (timing, the real tool-call log) a plain
  function signature can't carry.
- `cfo_tools.py` / `run_loop.py` — a second CFO implementation: `run_cfo_agent`'s `assign_task` tool
  creates a real Task, hands its exact question to a named specialist (`ap` or `au`), runs it
  synchronously, and keeps that Task's board state (`column`/`steps`/`progress`) derived from what the
  specialist's tool calls actually did — never the model's own account of itself. Verified against the
  live OpenAI API end to end: CFO → AP files a finding → Auditor independently reviews it.

Runs store concise decisions and tool metadata, never private chain-of-thought. The local extraction model
and its gated offline improvement loop are specified for a later implementation.
