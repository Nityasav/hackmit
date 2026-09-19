# Agents (owner: Agent design)

- `adapter.py` — model adapter (Anthropic `claude-sonnet-5`) + a replay adapter that reads a saved run
- `tools.py` — typed tool gateway (spec.md §8): search_sources, read_source_span, query_financial_records,
  traverse_context, calculate, retrieve_precedents, submit_finding, propose_adjustment, request_evidence,
  submit_review, propose_playbook, prepare_payment_batch
- `prompts.py` — the 5 role prompts from schooltrace/AGENT_PROMPTS.md
- `orchestrator.py` — CFO Agent plans → specialists run → Internal Auditor reviews → human queue

Every action must emit a `Decision` (see app/models.py) so it shows up in the Reasoning log:
when / how (tool calls) / why / alternatives / memory checks / outcome.
