# Agents

## Implementation note — a sixth Revenue & Collections (`rc`) specialist (2026-09-20)

Not implemented, deliberately. The specialist class itself is nearly free: `SnapshotSpecialist`
builds any non-`py` role through the generic `EvidenceSpecialist`, so `rc` needs only a focus line
and a prompt. Switching it on is the part that is not local, and a partial switch-on does not
degrade — it takes the working five down with it.

**Declaring the role and registering the adapter must land in the same commit.**

- `app/cfo/schemas.py` — the `Role` and `Source.domain` literals. `Plan` is handed to the live
  planner as a JSON-schema enum, so widening `Role` is by itself enough for the model to emit
  `role="rc"` unprompted, with no prompt change anywhere.
- `app/integrations/cfo_factory.py` — the `("ap", "py", "gr")` tuple. `CFOEngine._validate_plan`
  raises `BoundaryError` for a role with no registered adapter, and it runs inside `execute`'s
  outer `try`, so a single `rc` task in the plan fails the **whole run** — AP, Payroll and Grants
  results included. Widening the literal without registering the adapter is therefore strictly
  worse than doing neither. `app/cfo/api.py`'s live gate is an `issubset` check and needs no edit.

**It also has nothing of its own to read until the money-in records exist.**

- `app/ingestion.py` — `FIELDS` for `fees`, `collections`, `deposits`, `sponsorships`.
- `app/integrations/cfo_intake.py` — `DOMAINS`, which maps an intake role onto a specialist domain.
  Until it does, those sources arrive tagged `shared`: `rc` cannot be scoped to its own evidence,
  and a coverage task would hand it every other domain's sources as well.
- Amounts stay unavailable longer than evidence does. `calculate` fails closed for a domain with no
  published engine, so `rc` could cite a fees or deposits source and describe an unreconciled
  difference, but could not state its size until `app/accounting/` publishes a receipts-to-deposits
  calculation. Until then the adapter drops any claim marked `substantiated`, which is the correct
  outcome and not something to work around.

**Do not add `rc` to `engine.py`'s `five_agent` coverage loop.**
`tests/test_five_agent_workflow.py` registers three specialists and asserts exactly three task roles
and six model instances; a fourth coverage task fails those runs outright. The loop only fills in
roles a planner omitted, so a live planner can still assign `rc` without it.

What remains genuinely unwritten is the brief, not the wiring: trace fees charged → receipts
collected → bank deposits → sponsor pledges, cite the record on both sides of every link, and where
one side is absent ask for the slip. An undeposited receipt is an unreconciled difference and never
a theft; each finding states what it does not establish; amounts from separate checks are never
summed or described as recovered.

Three implementations currently live here, built independently on separate branches and merged
without being unified yet. All three reached working agent behaviour at roughly the same time from
different directions. Consolidate before the next milestone — see PROJECT_TRACKER.md.

**Direct-run family** (`cfo.py`, `grants.py`, `auditor.py`): each agent runs standalone against a
snapshot with its own bounded loop, citations, and persistence. `cfo.py` is read-only triage. `grants.py`
adds the Grants & Compliance agent (own prompt, deterministic award-window/ceiling checks). `auditor.py`
independently reviews exact CFO/Grants finding IDs — fresh source reads, original-CSV reparsing, required
calculation reperformance, up to four verdicts per run (accept/reject/needs_evidence, not financial
approval; optional `AUDITOR_MODEL`/`GRANTS_MODEL` overrides). Command center lets a human select the role;
there is no automatic dispatch between these agents yet.

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

**Ports family** (`payroll.py`, `model.py`, `prompts.py`, `__main__.py`): plugs into the bounded
coordinator in `app/cfo/` through `app/cfo/ports.py`, which owns scheduling, budgets, the evidence
gateway and the review gate. Covers the Payroll & Budget role, which the other two families leave
planned. Detailed below.

Runs store concise decisions and tool metadata, never private chain-of-thought. The local extraction model
and its gated offline improvement loop are specified for a later implementation.

## Payroll & Budget (`py`, ports family)

### Merged evaluation checkpoint (2026-09-19)

All five role implementations now exist, but **not one five-agent live pipeline**. The factory in
`integrations/cfo_factory.py` registers Payroll only; AP, Grants and the central Auditor adapters are
still missing. AP reads its sandbox JSON, not arbitrary uploaded intake snapshots. Do not report
scripted coordinator runs as live five-agent benchmarks.

Offline tests plus opt-in `tests/test_agent_live.py` and `tests/test_merged_agents_live.py` exercise the
separate runtime paths. AP's loop supports `AP_MODEL`, falling back to `OPENAI_MODEL`, then its original
default. CFO handoffs now return explicit finding IDs, Auditor can retrieve the exact finding, rejected
review submissions do not mark tasks done, and a retrieved but unfiled Auditor verdict gets one bounded
reminder. Payment proposals deduplicate invoice IDs and hold vendors on hold, missing invoice approvals
and conflicting rejections. A human must resolve approval conflicts; date ordering alone does not
establish supersession. These controls do not make the sandbox a production payment system.

Ties out payroll and tests fund allocations. The split of responsibility is the point of the design:

- the **model** chooses what evidence to retrieve and what it means
- the **engine** (`app/accounting/payroll.py`) decides every amount
- the **auditor** reperforms that same amount through the same code

So a claim carries a `calculation_id`, never a number the model wrote. Amounts are integer cents, and a
fund reclassification always reports a zero cash delta.

Each attempt is two bounded model calls:

1. **Evidence selection** — pick sources and calculations from the delegated scope, within the
   evidence-call allowance the coordinator granted.
2. **Findings** — draw claims strictly from what came back.

The adapter then drops any claim that cites unretrieved evidence, names a calculation it did not run,
states a currency amount in prose, or is marked `substantiated` without an exception in the engine's
result. Dropped claims become visible notes, not silent omissions, and never reach the coordinator as
boundary violations that would fail the whole task.

Evidence selection deliberately reads award, policy and service documents alongside the CSVs: they carry
the criterion an allocation is tested against, and an amount tested against no criterion supports nothing.

### Configuration

```powershell
$env:SPECIALIST_MODEL = '<structured-output-model-id>'   # falls back to CFO_MODEL
# OPENAI_API_KEY is read from the server environment, never a NEXT_PUBLIC_* variable.
```

`SPECIALIST_PROVIDER` (`openai` or `local`) and `SPECIALIST_LOCAL_BASE_URL` fall back to their `CFO_*`
equivalents, so one configuration serves both. The local path accepts loopback hosts only and passes a
dummy credential; the hosted key is never forwarded to it.

### Running it against real records

A full live `app/cfo/` run also needs `ap` and `gr` adapters and an auditor registered against
`app/cfo/ports.py`. The direct-run family's Grants and Auditor agents are not yet wired to those ports,
so the payroll agent has its own entry point for real records in the meantime:

```powershell
uv run python -m app.agents ws-0123456789abcdef
```

It uses the real intake snapshot, the real evidence gateway with real budgets and a real model call.
Nothing is approved, posted or written back, and the claims it prints have **not** been independently
reviewed.

### What it will not do

- assert an amount the accounting engine did not produce
- read an allocation percentage out of a document's prose — that needs a structured allocation record,
  and the agent asks for one instead
- treat a document's embedded instruction as anything but quoted text
- approve, post, pay or apply anything
