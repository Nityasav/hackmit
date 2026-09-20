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

## Held-out abstention benchmark

`tests/test_abstention_benchmark.py` runs the CFO agent against the 50 public rows of
vals-ai/finance_agent_benchmark (CC-BY-4.0): SEC-filing research questions about public
companies, none of it answerable from a district snapshot. The expected behaviour is the
same for every row and known without an adjudicator, so the run is pass/fail rather than a
score awaiting review: retrieve nothing, assert nothing, request what is missing.

It differs from `test_agent_live.py` in where the pressure comes from. That file plants an
adversarial *document* inside the workspace. This one asks an adversarial *question* from
outside it, against evidence that cannot answer it, where pre-training alone supplies a
fluent wrong answer.

Grading is independent of `validate_result`, which the product runs on itself. That matters:
`_money_mentions` only recognises amounts carrying `$` or a currency code, so a bare `10.82`
for "Netflix ARPU" passes the product's guard untouched. The benchmark inverts the dataset's
`Answer` column into figures and multi-word proper nouns that must *not* appear, after
subtracting anything the fixtures or the question already contain, and re-reads every
citation from the uploaded bytes. 44 of 50 rows carry a figure or name to check; the
remaining 6 are checkable on citations alone and each case records which applied, so
coverage is never overstated. Abstention is recorded but is not the pass criterion -- a run
can file an evidence request and still fabricate in its briefing.

```powershell
uv run python scripts/fetch_finance_benchmark.py     # caches the rows once, with a digest
$env:SCHOOLTRACE_ABSTENTION_EVAL = '1'
$env:SCHOOLTRACE_EVAL_OUTPUT = '<absolute output dir>'
$env:SCHOOLTRACE_ABSTENTION_LIMIT = '5'              # price a pass before buying all 50
uv run pytest -s tests/test_abstention_benchmark.py
```

Billable and opt-in; the detectors themselves are unit-tested in the default suite. Scores
are a floor, not a ranking: these are the publicly previewed rows of a 537-question
benchmark and the ones most likely to sit in a model's training data.

## Rubric benchmark over our own fixtures

`tests/test_rubric_benchmark.py` is the other half. The abstention benchmark asks whether
the agent stays quiet about what it cannot know; this one asks whether it produces the
answer when the answer is in the workspace. Rows live in `tests/data/rubric/` in the column
layout of vals-ai/finance_agent_benchmark — Question, Answer, Question Type, Expert time
(mins), Rubric — so a rubric written here and one written there are graded by the same code.
`money_in.json` seeds five rows whose reference answers restate the engine-verified table in
`tests/data/money_in/README.md`.

Operators are the upstream `correctness` and `contradiction` plus a local `prohibition`: a
finding is something a person acts on, so the dangerous failures here are assertions that
should never have been made — calling a reconciling difference stolen money, summing four
amounts that measure different things. A research benchmark has no need for that operator.

Scoring keeps **blocked** apart from **unmet**. `eval_support.reachable_amounts` computes,
as an upper bound, every amount the agent could get past `validate_result` by reading every
source and paging every record role its tool schema exposes. A criterion naming an amount
outside that set cannot be satisfied at any level of competence, and counting it as an
ordinary miss would blame the model for a gap in the tools. Two of this pack's four planted
amounts were exactly that case until `compute_money_in_checks` landed; all four are
reachable now, and the distinction stays because the next pack will find the next gap.

Only the objective checks gate: a contradiction, a prohibition breach, or a citation that
does not quote the uploaded bytes. The correctness percentage is reported rather than
asserted unless `SCHOOLTRACE_RUBRIC_FLOOR` is set, because a judge's reading of
natural-language criteria drifts between model versions and a suite that fails on that drift
is one people learn to ignore. The judge must be a different model from the one under test;
`SCHOOLTRACE_ALLOW_SELF_JUDGE=1` is required to override that.

```powershell
$env:SCHOOLTRACE_RUBRIC_EVAL = '1'
$env:SCHOOLTRACE_EVAL_OUTPUT = '<absolute output dir>'
$env:SCHOOLTRACE_JUDGE_MODEL = '<a model that is not OPENAI_MODEL>'
uv run pytest -s tests/test_rubric_benchmark.py
```

### Money-in calculations (`compute_money_in_checks`)

`list_records`' role enum used to be the slice `roles[1:8]` — chart through invoice — and
`compute_ledger_totals` covers the ledger alone, so none of the four money-in roles was
reachable by any calculation. Reading the CSVs put each record's own amount into
`allowed_amounts`, so the agent could cite COL-008's 1,500.00 and COL-009's 900.00, but
their 2,400.00 total and the 150.00 DEP-REF-0004 shortfall are derived figures that no
single record carries. `validate_result` rejected them, and the failure was not a bad
answer but a dead run: the agent spent 10 of its 12 tool calls on rejected submissions and
ended 502 with no analysis.

`compute_money_in_checks` closes it by calling `accounting.collections.collection_checks` —
the same code behind the director review, not a second implementation that could drift —
and putting every amount it returns into `allowed_amounts`. It reads through `_records`,
pinned to the run's snapshot manifest, rather than `ingestion.active_records`, so a commit
landing mid-run cannot change what the run computed. The enums now name the money-in roles
explicitly instead of slicing the list, which is what made the omission easy to miss.

The tool returns money-in checks only, each with its derived amount in cents and the exact
source lines behind it, and carries the engine's own caveat: these amounts measure different
things, none establishes theft or loss, and they must never be summed. `tests/test_money_in_tool.py`
holds the before-and-after as a parametrized pair — the same claim submits at 201 with the
calculation and still fails closed at 502 without it — and ties the output to the review scan
so the two readers of one engine cannot diverge.

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
