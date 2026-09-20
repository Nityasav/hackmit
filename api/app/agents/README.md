# Agents

- `cfo.py` is the first live slice: OpenAI Responses API, immutable-snapshot scope, bounded read-only
  evidence tools, strict structured submission, citation verification and persisted telemetry.
- `grants.py` adds the Grants & Compliance agent with its own prompt and deterministic supplied-payroll
  award-window/ceiling checks. It reuses the CFO module's bounded loop, citations and persistence.
- Command center selects the role; both agents' latest current-snapshot findings coexist. The coordinator
  does not automatically dispatch these direct-run agents yet. AP and Payroll remain planned.
- `auditor.py` independently reviews exact CFO/Grants finding IDs with explicit fresh source reads,
  original-CSV reparsing and required calculation reperformance. Up to four verdicts per run, with
  accept/reject/needs_evidence distinct from financial approval; optional `AUDITOR_MODEL` override.
- No extra service or directory was added; `GRANTS_MODEL` optionally overrides `OPENAI_MODEL` for this role.

Runs store concise decisions and tool metadata, never private chain-of-thought. The local extraction model
and its gated offline improvement loop are specified for a later implementation.
