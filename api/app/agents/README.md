# Agents

Two parallel implementations currently live here, built independently on separate branches and merged
without being unified yet. Both reached "CFO + independent Internal Auditor review" at roughly the same
time from different directions. Consolidate before the next milestone — see PROJECT_TRACKER.md.

**Direct-run family** (`cfo.py`, `grants.py`, `auditor.py`): each agent runs standalone against a
snapshot with its own bounded loop, citations, and persistence. `cfo.py` is read-only triage. `grants.py`
adds the Grants & Compliance agent (own prompt, deterministic award-window/ceiling checks). `auditor.py`
independently reviews exact CFO/Grants finding IDs — fresh source reads, original-CSV reparsing, required
calculation reperformance, up to four verdicts per run (accept/reject/needs_evidence, not financial
approval; optional `AUDITOR_MODEL`/`GRANTS_MODEL` overrides). Command center lets a human select the role;
there is no automatic dispatch between these agents yet. AP and Payroll remain planned here.

**Orchestrated family** (`ap_tools.py` / `ap_write_tools.py` / `au_write_tools.py` / `tool_gateway.py` /
`decision_tools.py` / `cfo_tools.py` / `run_loop.py`): a CFO that actually dispatches. `run_cfo_agent`'s
`assign_task` tool creates a real Task, hands its exact question to a named specialist (`ap` or `au`),
runs it synchronously, and keeps that Task's board state (`column`/`steps`/`progress`) derived from what
the specialist's tool calls actually did — never the model's own account of itself. AP's write tools
(`submit_finding` / `request_evidence` / `prepare_payment_batch`) and the Auditor's `submit_review` enforce
separation of duties in code: an agent can never verify its own finding, an approval can only be created
`pending`, and the auditor is refused if it tries to review its own work. `tool_gateway.py`'s per-run
budget enforcement (spec.md §8's default of 12) is shared by every role in this family. Verified against
the live OpenAI API end to end: CFO → AP files a finding → Auditor independently reviews it.

Runs store concise decisions and tool metadata, never private chain-of-thought. The local extraction model
and its gated offline improvement loop are specified for a later implementation.
