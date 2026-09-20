# Working on this together

Read this before your first commit on the rework. It says what is stable, what is about
to be rewritten, and where the best parallel work is.

Background: [schooltrace/AGENT_SYSTEM_PLAN.md](schooltrace/AGENT_SYSTEM_PLAN.md) — the
plan, the phases and why each decision was taken.

## The pivot, stated plainly

The product is now an **agentic office of the CFO for a SaaS company**: one orchestrator,
four worker agents and seventeen subagents over vendors, purchase orders, goods receipts,
customers, bank activity and processor payouts.

The **school-finance domain is gone** — fees, collections, deposits, sponsorships, grants
and everything under the name "money-in". That was a deliberate removal, not an oversight.
`accounting/{payroll,grants,collections,ap,review}.py` and `agents/{cfo,grants,auditor}.py`
were deleted with their tests.

`main` was merged into this work rather than replaced by it, so every commit made
while the rework was in progress is still in the history. What was *carried across*:

| Ported | How |
| --- | --- |
| `detect_saved_sources` | Verbatim. It read `roles.FIELDS` instead of restating role names, so it recognizes the new twenty-one roles with no edit |
| `source-detection.ts` | Rewritten to fetch `/api/roles` rather than carry its own copy of the schema table, which is what used to make it go stale |
| `extraction/serve.py` and its benchmark | Untouched. Extraction survives the pivot, and the measured results stand |
| The 20s client timeout fix, the health probe and origin regex | Untouched |

What was **not** carried across, and why: the money-in checks, the triage agent's
guardrails, and the rubric benchmark built on them. They test behaviour this rework
deleted. The grading principle behind that benchmark is worth keeping, though, and is
written down under "Evaluating" below.

## Safe to build on

These are stable. Build against them freely.

| Area | Files |
| --- | --- |
| Record vocabulary | `api/app/roles.py` |
| What Books asks for | `api/app/requirements.py` |
| Schema (v7) | `api/app/db.py` |
| Exact money | `api/app/accounting/money.py` |
| Matching, duplicates, policy | `api/app/accounting/match.py` |
| Agent organization | `api/app/agents/registry.py`, `schemas.py`, `budget.py`, `tools.py` |
| Event identity | `api/app/events.py` |
| Bank reconciliation, cash | `api/app/accounting/reconcile.py`, `cash.py` |
| The graph | `api/app/graph/` (add a worker by writing its subagents' tools) |
| Control tests | `api/app/accounting/controls.py` |
| Escalation and resume | `api/app/graph/escalation.py` |
| Data generation | `fixtures/generate_saas.py` |
| Books requirement UI | `web/src/components/DataRequirements.tsx` |

## Do not touch yet

Phase 3 landed, so most of this list is now safe. What remains is what the next phases
rewrite.

| File | Why |
| --- | --- |
| `api/app/graph/` | Phase 4 adds `interrupt()` and the preparer/reviewer edges |
| `web/src/components/investigation/Investigation.tsx` | Becomes a chat surface in phase 8 |

**One coordination rule.** `AgentId` exists in three places — `api/app/models.py`,
`web/src/lib/types.ts` and `contracts/`. Whoever changes it changes all three in one
commit. A bundle that fails to parse renders an error instead of a workspace, so a
half-done rename takes the whole dashboard down. `web/src/lib/schemas.ts` carries the
same enum for parsing and moves with them.

**`db.connect()` takes an immediate write lock.** Two of them on one thread deadlock
against each other for the full fifteen-second timeout. Read what you need before
opening a connection, and never call a helper that opens its own from inside a
`with db.connect()` block.

## The best parallel work

**The deterministic accounting modules.** Roughly half the system, no dependency on
LangGraph, and therefore no possible collision with phase 3.

| Module | Agent | Job |
| --- | --- | --- |
| `accounting/statements.py` | B3 | Income statement, balance sheet, cash flow, from the ledger |
| `accounting/variance.py` | C3 | Decompose budget-to-actual into named drivers |
| `accounting/close.py` | B1 | Close checklist state and readiness |

Each is a pure function over `(records, config)` returning plain dicts. Testable with no
model and no network. **Copy `accounting/match.py`** — it is the worked example, and its
docstrings explain the conventions below.

Second-best: more defects in `fixtures/generate_saas.py`. `--defects` plants six and
three lookalikes today; the catalogue in the plan has more, and every one you add is
another thing the checks can be *measured* against rather than assumed to catch.

**Write the clean case first, and prove it is silent.** Three separate bugs in this
repo were the same mistake: a check whose clean baseline was full of exceptions. A real
finding then arrives indistinguishable from the noise, and a reviewer learns to skim
past both. `tests/test_controls.py` shows the shape — clean pack, planted pack, scored
against a truth file the application cannot reach.

### Wiring a new module in

1. Write the pure function in `accounting/`.
2. Add a method to `Toolbox` in `agents/tools.py` that calls it and charges a tool call.
3. Add one line to `dispatch()` and one entry to `tool_definitions()`.
4. Name the tool in the agent's `tools=(...)` in `agents/registry.py`.

If the agent needs a record type nobody uploads yet, add a `Requirement` in
`requirements.py` first. The registry check fails at import otherwise — on purpose.

## Conventions that are not negotiable

These are load-bearing. Breaking one is a bug even when the tests pass.

1. **Money is integer cents.** Never a float, anywhere, for any reason. `money.py` owns
   parsing and allocation. The UI is the only place that formats.
2. **No model writes a number.** Agent prose is validated to contain no digits or
   currency symbols. Deterministic code produces every figure; the renderer inserts it.
3. **Confidence is computed, never claimed.** It comes from the weighted rubric in
   `match.py`, and every input is recorded so a person can re-derive the score.
   `AgentResult` has no confidence field, deliberately.
4. **An agent cites only what it retrieved.** `Toolbox.validate_citations` rejects a
   result pointing at a record the agent never read.
5. **Only a human decision writes memory.** `approvals.decide()` is the sole writer of
   precedent, so an agent cannot promote its own conclusion into guidance for its next run.
6. **No demo data, ever.** No seeding, no "load sample data", no fixture in the runtime
   database. The generator writes files to disk; a person uploads them through Books like
   any other records. This is what keeps "the agents found this" honest.
7. **A finding's id names what it is, not which rows are in it.** Ids derived from group
   membership move when the group gains a row, orphaning a reviewer's note and
   re-presenting the finding as new.
8. **Say what a check does not establish.** An unreconciled difference is not a loss. A
   duplicate candidate is not a duplicate payment. Amounts from different checks are
   never summed.
9. **A passing check is still a finding.** "No exact-key duplicate in the register" says
   what was tested, and belongs on screen beside what was not. A report that only ever
   shows problems teaches a reader that silence means safety.
10. **One answer resolves one question.** Several agents can pause in one run.
   `resume_investigation` is addressed to a single approval and refuses to guess when
   more than one is waiting — resuming them all together would record a decision on
   questions nobody was shown.

## Evaluating

From the evaluation harness that was retired with the school domain, one principle is
worth carrying into phase 7: **an evaluation must grade independently of the product**.
Re-read citations from the bytes the evaluation itself supplied and compare figures
against what those bytes contain — never against what the system under test was willing
to accept. A benchmark that asks the system whether it passed measures nothing.

## Running it

```bash
cd api && uv sync && uv run pytest          # 218 passing
python fixtures/generate_saas.py --out ./generated --seed 42 --defects
cd web && node --experimental-strip-types --test src/lib/*.test.ts
cd api && uv run uvicorn app.main:app --reload --port 8000
cd web && bun install && bun dev            # http://localhost:3000
cd web && npx tsc --noEmit && npx eslint src

# Generate records to upload through Books. Nothing is seeded.
python fixtures/generate_saas.py --out ./generated --seed 7
```

Put `OPENAI_API_KEY=...` in ignored `api/.env.local`. Without it, intake and every
deterministic check still work; only agent runs refuse, with a message saying why.

## Budget

Agent runs cost money and the meter is enforced in code: **$10 per run**, **$75 per day**,
both configurable through `AGENT_RUN_CAP_CENTS` and `AGENT_DAY_CAP_CENTS`. A breach stops
the work and reports it rather than returning a thinner answer. Every run response carries
what it cost.

Keep roughly $300 of the credit for demo day.
