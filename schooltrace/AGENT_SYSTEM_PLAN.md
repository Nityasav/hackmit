# Agentic CFO — implementation plan

Companion to the canonical agent spec (one orchestrator, four worker agents, seventeen
subagents). That document says *what the agents are*. This one says *how they are built,
what data they run on, what they cost, and in what order the work lands*.

Status: plan agreed 2026-09-20. Phase 1 in progress on `feat/agentic-cfo-rework`.

## 1. Decisions taken

| Question | Decision |
| --- | --- |
| Orchestration | **LangGraph.** Workers are compiled subgraphs; subagents are nodes; dynamic fan-out via `Send` |
| Models | **OpenAI.** Sol for the orchestrator and reviewers, Terra for workers, Luna for mechanical subagents |
| Domain | **SaaS company.** Vendors, purchase orders, goods receipts, customers, processor payouts, payroll, budgets |
| Processor payouts | **In scope.** Stripe/Adyen style, net of fees, refunds and chargebacks |
| Legacy school data | **Removed.** Roles, accounting modules and fixtures are replaced, not extended |
| Demo data | **Never seeded, never shipped.** A generator writes CSVs to disk; a person uploads them through Books like any other records |
| One-shot run | **Kept.** "Start the investigation" becomes the first message of a conversation rather than a separate mode |
| Standalone triage | **Reworked** into the orchestrator. A cheap model keeps an unpriced path available |
| Budget | $10 per run hard cap, $75 per day, $300 reserved for demo day |

### No demo content, anywhere

There is no demo mode, no seeded workspace, no "load sample data" control and no fixture
committed into the runtime database. `fixtures/` is a generator that writes files to a
directory of your choosing. Those files reach the product the same way real records do:
someone selects them in Books, maps the columns, reviews the validation and commits a
snapshot. If a demo exists, it is because a person built it and saved it themselves.

This is a hard rule, not a preference. It is what keeps "the agents found this" honest.

## 2. Models and budget

Pricing observed September 2026. The 5.6 family uses Sol/Terra/Luna capability tiers.

| Model | $/MTok in | $/MTok out | Used by |
| --- | --- | --- | --- |
| GPT-5.6 Sol | 4.00 | 20.00 | Orchestrator, B4 Close Review, D1 Audit, D2 Controls |
| GPT-5.6 Terra | 2.00 | 12.00 | Workers A–D, judgment subagents |
| GPT-5.6 Luna | 0.20 | 1.20 | Extraction, classification, mechanical subagents, unpriced triage |

Sol is on promotional pricing at least through 2026-11-21. Every model id is an
environment variable so a price change is a config edit.

Estimated cost of one full period close:

| Tier | Calls | Tokens in / out | Cost |
| --- | --- | --- | --- |
| Orchestrator | ~20 | 240k / 40k | $1.76 |
| Workers x4 | ~24 | 360k / 60k | $1.44 |
| Subagents | ~50 | 500k / 75k | ~$1.20 |
| Reviewers | ~8 | 160k / 16k | $0.96 |
| | | **total** | **~$5.40** |

With prompt caching on static system prompts, $3–4 is the realistic figure. Against
$1,000 of credit that is roughly 200–300 full runs.

Spend is metered in integer cents on the run row and enforced in code, not in prompts.
A run that would exceed its cap stops and says so; it does not silently degrade.

### Auditor independence without a second provider

Running every agent on one provider costs the independence that comes from uncorrelated
model families. Four compensations, strongest first:

1. **Deterministic re-performance.** The auditor recomputes the number in Python and
   compares exactly. A disagreement is an error, not a negotiation.
2. **Context starvation.** The reviewer never sees the preparer's reasoning. It receives
   the claim and fetches originals itself.
3. **Tier separation.** Preparers on Terra, reviewers on Sol. Different-sized models fail
   differently.
4. `build_client()` already abstracts the provider, so pointing D at another vendor later
   is an environment change rather than a refactor.

## 3. Economic event identity

Invariant 1 — one transaction, one identity — is implemented as a first-class
`event_id` carried by every artifact, not as a join discovered afterwards.

```
economic_event evt-...
  |- vendor_invoice   INV-99121
  |- purchase_order   PO-1821
  |- goods_receipt    GR-1828
  |- payment          PAY-18392
  |- bank_transaction ACH-828192
  |- gl_lines         JE-4471 L1..L2
  |- accrual          JE-4502
  |- close_period     2026-09
  |- variance_line    cloud-expense
  |- evidence_pack    EV-18392
```

Two supporting tables make the graph queryable and auditable:

- `links` — typed edges carrying **how** each was established (`exact`, `fuzzy`,
  `inferred`, `human`), a confidence, a rationale and the agent that drew it.
- `agent_decisions` — what an agent did, why, on what evidence, who reviewed it.

### Confidence is computed, never self-reported

A model asserting "99.3% confident" is uncalibrated and indefensible under questioning.
Confidence is a deterministic rubric over match features — amount equality, vendor-name
distance, date proximity, reference overlap, supporting-document presence — with the
weights in code and the inputs recorded on the link. A model may *explain* a score. It
may not produce one.

## 4. Data

### Intake roles

Structured (CSV): `chart`, `opening`, `ledger`, `vendors`, `purchase_orders`,
`goods_receipts`, `vendor_invoices`, `payments`, `customers`, `customer_invoices`,
`remittances`, `bank_transactions`, `processor_payouts`, `payroll`, `expenses`,
`budgets`, `forecasts`, `headcount`, `approvals`, `period_locks`, `tax_registrations`.

Document (text/PDF): `contract`, `policy`, `document`.

### Data requirements drive the Books screen

Every agent declares the inputs it needs. Those declarations are the single source for
what Books asks for, so an agent cannot silently depend on data nobody was asked to
supply. A requirement is satisfied by a committed CSV, a committed document, or a
workspace setting answered in a form.

`GET /api/workspaces/{ws}/requirements` returns, for each requirement: whether it is
satisfied, which agents are waiting on it, and what it unlocks. Books renders exactly
that list. Adding an agent that needs sales-tax registrations adds a box to Books.

### Generation

`fixtures/generate_saas.py` builds clean economic events first, derives books, bank
activity, subledgers and documents from them, then injects controlled defects. The truth
file is written outside the API data directory and is unreachable from the tool gateway.

Target scale for one company across three periods (two closed, one open): ~40 vendors,
25 customers, 60 employees, 800–1,200 journal lines per period, 120 vendor invoices,
80 purchase orders, 90 receipts, 200 bank lines, 3 processor payouts.

Every defect ships with a benign lookalike, so precision is measurable and not just recall:

| Defect | Lookalike that must not fire |
| --- | --- |
| Duplicate invoice under an altered number | Same amount, separate deliveries |
| One payment covering several invoices | One invoice paid in two instalments |
| Wire received net of a bank fee | Genuine short payment or dispute |
| Duplicated refund | Two legitimate refunds to one customer |
| Late invoice requiring an accrual | Work not yet performed |
| Processor payout net of fees and chargebacks | Clean payout with no adjustments |
| Duplicate vendor record | Two real entities with similar names |
| Round-number payment | A legitimately round contract |
| Self-approved request | Valid delegated authority |
| Journal entry posted after close | Authorized, documented reopening |
| Unexpected spend causing variance | Timing shift, not overspend |

## 5. Orchestration

```
main graph                        thread = workspace x period, SqliteSaver
  chat -> orchestrator (Sol)      routes; retains control; workers are tools
    |
    +-- subgraph A Treasurer   A1 A2 A3 A4
    +-- subgraph B Controller  B1 B2 B3 B4
    +-- subgraph C FP&A        C1 C2 C3 C4 C5
    +-- subgraph D Audit       D1 D2 D3 D4
    |
    +-- guardrail nodes        budget, scope, balance, citation
    +-- interrupt()            human escalation
    +-- Store                  cross-thread precedent
```

Workers are **tools the orchestrator calls**, never handoffs. The orchestrator must retain
the thread to combine four domains and keep every delegation inside one budget.

**Attenuation.** On sub-delegation an agent passes only the slice of its rights the
subtask needs. A's scope is a superset of A1's, enforced in the tool wrapper rather than
requested in a prompt.

### Not every subagent needs a model

Roughly half the subagents are deterministic work an LLM supervises. This is what makes
twenty-two agents affordable and correct.

| | Model in the hot path | Deterministic, model narrates or judges exceptions |
| --- | --- | --- |
| A | A1 exception judgment | A1 three-way-match arithmetic, A2 aging, A3 exact matching, A4 projection |
| B | B1 close orchestration, B2 accrual estimation, B4 review | B2 journal construction, **B3 statements entirely** |
| C | C3 explanation, C4 scenarios, C5 narrative | C1 rollup, C2 baseline series, C3 decomposition |
| D | D1 sample selection, D2 judgment calls | D2 rule tests, **D3 evidence assembly entirely** |

B3 must never author a balance sheet. It reads the general ledger in integer cents and
flags inconsistencies. D3 assembles an evidence pack from the event graph; it generates
nothing.

### One runtime, twenty-two specs

Subagents differ by prompt, tools, schema and budget — not by code. A declarative
registry builds the graph at import time so topology and documentation cannot drift.

```python
AgentSpec(
    id="A1", name="Accounts Payable", parent="A", tier="subagent",
    model=MODEL_TERRA,
    tools=["read_source", "find_po", "find_receipt",
           "three_way_match", "check_duplicate", "check_policy"],
    output_schema=APResult,
    reviewer="D2",
    requires=("vendor_invoices", "purchase_orders", "goods_receipts", "vendors"),
    escalate_when=EscalationRule(
        confidence_below=85,
        amount_above_cents=500_000,
        on=("duplicate_suspected", "vendor_changed", "no_po"),
    ),
    budget=Budget(model_calls=4, tool_calls=20, usd_cents=40),
)
```

`requires` is what Books renders. Adding an agent adds its data ask automatically.

## 6. Preparer, reviewer, approver

Three outcomes wired as graph edges, with thresholds in `EscalationRule` rather than prose:

- high confidence — auto-approve, logged, never silent
- medium — second-agent review (B4 for close work, D2 for controls)
- low or material — `interrupt()`, durable pause, human decision

Only a human decision writes memory. A later period is offered the precedent, must
re-check it against its own evidence, and must record `applied: true/false` with a reason.
A declined precedent is a correct outcome and is displayed as prominently as an applied one.

## 7. Integration

| Path | Fate |
| --- | --- |
| `accounting/money.py` | keep |
| `accounting/{payroll,grants,collections,review}.py` | delete; replaced by `{match,reconcile,close,statements,variance,controls}.py` |
| `ingestion.py` | keep the staging lifecycle, replace roles and validators |
| `db.py` | keep patterns, schema v6 adds events, links and decisions |
| `requirements.py` | new; the registry Books renders |
| `cfo/engine.py` | delete; replaced by `graph/` |
| `cfo/{schemas,tools,ports}.py` | port budget enforcement, `Claim`, `MemoryCheck` |
| `agents/*` | delete; replaced by `agents/registry.py` and one runtime |
| `approvals.py` | keep; `finding_id` generalizes to `event_id` |
| `projection.py` | rewrite as an event-graph reader |
| `security.py` | unchanged |
| `models.py` `AgentId` | new literal set, changed with `web/src/lib/types.ts` and `contracts/` together |
| Books / Briefing | same shape, new record types, requirements-driven asks |
| Investigation | chat, escalation queue, event timeline |

## 8. Phases

| # | Deliverable | Gate |
| --- | --- | --- |
| 1 | Schema v6, event identity, links, roles, requirements registry, generator | Generated books tie; truth file unreachable; requirements drive Books |
| 2 | Agent registry, one subagent runtime, budget and spend enforcement | A1 processes one invoice, cites evidence, respects its cap |
| 3 | LangGraph skeleton: orchestrator plus subgraph A | Invoice to match to payment to bank to cash, one `event_id` throughout |
| 4 | Defect injection, D2 controls, preparer/reviewer, `interrupt()` | Planted duplicate caught, lookalike not flagged, escalation resolves |
| 5 | Subgraph B, deterministic statements | Period closes; statements tie to the ledger in exact cents |
| 6 | Subgraph C | Variance decomposes to named transactions |
| 7 | D1, D3, D4, cross-period memory | A correction changes the next period's behaviour, with a recorded check |
| 8 | Chat UX, event timeline, escalation queue | Full flow end to end |

Phases 1–3 are the spine. If time runs short, cut from 6 and 7 upward.

## 9. Risks

1. **Scope.** Twenty-two agents, a new data model and a new framework at once. Phases 1–3
   must land; the rest is negotiable.
2. **C4 Strategic Planning has no ground truth.** Multi-year scenarios cannot be scored
   against a fixture. Its output is labelled unvalidated rather than placed beside
   verifiable numbers.
3. **B3 must stay deterministic.** If asked whether a model wrote the balance sheet, the
   answer has to be no.
4. **Latency.** Three hops before real work starts. Intermediate events stream to the UI
   or the product feels dead during a run.
5. **Removing the unpriced path.** Every question costing money discourages exploration.
   A Luna-tier triage keeps an unpriced option available.
