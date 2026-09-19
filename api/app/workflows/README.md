# Workflows (owner: Workflows)

- `definitions.py` — the 5 workflows and their stages: month-end close, payroll, AP & payments,
  grant compliance, audit prep. Each stage names its owner agent and whether it is a human gate.
- `scenarios.py` — demo actions: reset, inject_issue, add_evidence (60/40 and 80/20 fixtures), next_month
- `fixtures/` — synthetic Sandbox University records + the MIT public-report source manifest

Hidden ground truth stays OUT of this package (DATA_AND_EVALUATION.md §3): agents must never be able
to read the answer key.
