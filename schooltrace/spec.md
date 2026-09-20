# Sherlock — Product and Technical Specification

Version: 1.0 | Date: 2026-09-19 | Status: implementation-ready hackathon design

### Showcase update

The revised [DEMO.md](DEMO.md) is authoritative for presentation flow: a read-only MIT public-report explorer followed by a synthetic university investigation, with explicitly labeled hybrid/replay execution. Public documents are permitted inputs to this explorer; synthetic-only restrictions continue to govern transaction fixtures and benchmark data. The explorer does not claim access to MIT's internal ledger or implement statutory university accounting. Existing accounting, review, and evaluation requirements remain in force. Authored scripted previews may illustrate incomplete capabilities but do not satisfy agentic acceptance criteria or count as measured results.

### Redesign update (2026-09-19, evening)

The product is now presented as **an Office of the CFO for schools, run by AI agents**. The five roles keep their responsibilities but get finance-office display names (§8). The UI is rebuilt around making the agents' work visible (§11). Learning is implemented as agent-written playbooks behind a replay gate and human approval (§7.4). Every agent action emits a structured decision record (§8) that feeds the Reasoning log. The build is cut to about 16 hours for 4 people; see [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) and `/WORKPLAN.md`. The approved visual prototype is `docs/design/prototype.html`.

## 1. Purpose and problem

Educational institutions can have substantial finance and compliance teams and still lose track of how money was allocated, approved, paid, and reported. Payroll, procurement, grants, enrollment, and facilities operate in separate systems. A transaction can be valid in one system but incorrectly classified, insufficiently supported, or duplicated elsewhere.

The product hypothesis is that these disconnected records and unresolved exceptions create preventable audit-readiness problems. Consequences can include rework, repayment exposure, distorted spending decisions, and disruption to services students depend on. Funding and financing consequences are possible, not automatic. Do not claim all schools mismanage money or invent prevalence statistics. See [SOURCES.md](SOURCES.md).

Sherlock collects financial records, establishes a traceable accounting baseline, and coordinates agents to answer: **What is wrong, what evidence proves it, what remains uncertain, and what action would resolve it?**

It supports internal preparation for an external audit. Its auditor agent is an independent review role within the application, not a licensed external auditor or an audit opinion.

## 2. Users and decisions

| User | Decision enabled | Deliverable |
| --- | --- | --- |
| Controller / finance director | Which exceptions require action before close? | Prioritized findings and proposed adjusting journal entries |
| Grant administrator | Are costs supported and charged to the correct award? | Restricted-fund schedule and evidence requests |
| Payroll / procurement staff | What source record needs correction? | Specific transaction, conflicting evidence, and remediation owner |
| Internal audit | Can the conclusion be independently reproduced? | Workpapers, calculation lineage, and control exceptions |
| Board / university leadership | What does this mean for services and funding? | Plain-language report with bounded exposure and unresolved questions |

## 3. Scope and accounting profile

### 3.1 MVP institution

Fictional Maplebridge School District: three schools, central administration, approximately 1,200 students, 80 employees, and 20 vendors. Analyze September and October of a fictional fiscal year. Use aggregate enrollment counts and synthetic employee identifiers. Include general operations, student-support grant, technology grant, and facilities tracking dimensions.

Default profile: `DEMO_US_DISTRICT_MANAGEMENT_ACCRUAL_V1`, USD, two decimal places. It produces simplified internal management reports from a supplied balanced opening trial balance and fully traced monthly activity. It is **not** a complete GASB financial statement package. “Fund” in this profile is a management allocation dimension; the demo does not claim individually self-balancing governmental funds.

The basis distinction matters: US governmental fund reporting and government-wide reporting use different measurement conventions. A public university, private nonprofit university, or Canadian school board cannot inherit this profile without a separately reviewed adapter. See [ACCOUNTING_CONTROLS.md](ACCOUNTING_CONTROLS.md).

### 3.2 Feature coverage

| Domain | MVP | Extension |
| --- | --- | --- |
| School budgets | Department/program budget versus actual, encumbrance overlay | Budget construction and multi-year planning |
| Payroll and benefits | Gross-to-net tie-out, employer benefits, cost allocation, substitute variance | Actuarial pension/OPEB valuation, collective agreement interpretation |
| Funding and revenue | Grant awards, reimbursement receivables, cash receipts | Tuition revenue, donation conditions, endowments |
| School money-in | Fee charges, event collections, bank deposits and sponsor pledges; receipt-to-deposit tracing by reference, deposits no supplied receipt accounts for, uncollected fee remainders and unreceived pledge remainders | Payment-processor and point-of-collection feeds, family statements, refunds, waiver policy and receipt issuance |
| Enrollment | Aggregate counts and staffing-cost variance explanation | Formula-driven revenue scenarios using verified local funding rules |
| Purchasing and payments | Three-way match, duplicate candidates, AP aging, approval exceptions | Live ERP integration and payment execution |
| Facilities | One maintenance/prepaid or capital-classification investigation | Construction-in-progress, retainage, bond compliance |
| Reporting and audit preparation | Management ledger, trial balance, balance sheet, findings and workpapers | Statutory annual reports and formal audit methodologies |
| Restricted funds | Award period, purpose, allocation, documentation, duplicate funding checks | Program-specific supplement-not-supplant, maintenance-of-effort, and complex indirect costs |

### 3.3 Non-goals

- Autonomous real-world posting, payments, bank changes, grant submissions, or communications.
- Declaring fraud, intent, legal noncompliance, a material weakness, or an audit opinion without qualified review.
- Reconstructing an entire institution's balance sheet from incomplete bank statements alone.
- Treating a graph, an LLM confidence score, or agent agreement as proof.
- Supporting every accounting jurisdiction in the first build.

## 4. Core user journey

1. Select the institution, accounting profile, period, and scenario.
2. Import the opening trial balance, existing ledger and subledgers, bank activity, payroll, budgets, contracts, invoices, award documents, and approval records.
3. Show a completeness panel: source coverage, row counts, control totals, unmapped accounts, missing periods, extraction warnings, and unresolved opening balances.
4. Establish the as-reported baseline. Source documents corroborate imported entries; they must not create duplicate transactions. If no ledger exists, separately stage reconstructed entries for review.
5. Ask the command bar (“Ask your finance team”): “Enrollment fell 6%. Why did staffing costs rise, and why is the student-support grant nearly exhausted?”
6. The CFO Agent creates hypotheses and specialist tasks, which appear on the Agent board. Each task has a question, permitted data scope, expected evidence, and stopping condition.
7. Specialists use typed tools and the context graph. They return findings, counterevidence, calculations, and requests for missing records.
8. Auditor independently re-performs critical calculations and checks original sources. Unsupported conclusions are rejected or downgraded.
9. Human reviews unresolved evidence requests and proposed adjustments. Any requested clarification stays in the local review queue.
10. An approved scenario recomputes dependent schedules and reports. The as-reported baseline remains accessible.
11. The CFO Agent produces the final evidence-backed report and action register, including unresolved limitations.
12. Agents propose playbooks from repeated patterns. Playbooks that pass the replay gate and human approval become scoped memory. Month two demonstrates changed investigation behavior, and the Reasoning log shows each use or rejection.

## 5. Architecture

```text
CSV + text PDFs + synthetic emails/contracts
                 |
        ingest / validate / hash
                 |
    immutable sources + normalized SQL records
           |                         |
 deterministic accounting      graph projection
 and calculation services      facts / hypotheses / precedents
           |                         |
           +---- typed tool gateway --+
                           |
                     CFO Agent
                 /       |        \
       AP & Payments  Payroll &   Grants &
                      Budget      Compliance
                 \       |        /
                 Internal Auditor review
                           |
                  human review queue
                           |
              approved scenario / recompute
                           |
           reports + workpapers + evaluation logs
```

Recommended implementation shape: TypeScript web UI, Python API and worker, PostgreSQL, SQL graph tables, local file storage, and one provider-neutral model adapter. A dedicated graph database is optional; typed edges, temporal filtering, traversals, and provenance are required regardless of storage. Confirm supported library versions during implementation rather than relying on unverified SDK names in a challenge brief.

Hackathon build (justified equivalent): `web/` uses Next.js 16 App Router, TypeScript, Tailwind v4, and bun. `api/` uses FastAPI (Python, uv) with `app/ingestion.py` (record intake), `app/accounting` (exact-cents checks), `app/agents` and `app/cfo` (the agent runtime), and `app/reviews.py` (snapshot review and human follow-up). There is no `app/workflows` module; the workflow stages described elsewhere in this document are design, not code. The hackathon uses SQLite instead of PostgreSQL for zero-setup local runs; the schema stays portable to Postgres. `contracts/` holds the shared fixtures.

The model layer is provider-neutral at its boundary and deliberately hybrid. The first live adapter uses the OpenAI Responses API with a server-side `OPENAI_API_KEY`; `OPENAI_MODEL` selects the model without changing agent contracts. Strong hosted models perform planning, investigation and independent challenge. A future fine-tuned local extraction model performs private document perception: schema-guided extraction of requirements, dates, entities, relations and exact source spans. The local model is not permitted to calculate financial results, approve changes or convert an extraction into an audit conclusion. A clearly labeled replay adapter remains available for deterministic demos and evaluation.

The product's internal “brain” is the combination of the orchestrator, immutable run state, deterministic accounting tools, evidence graph, reviewed playbooks and versioned model adapters. No individual model is the system of record. Model output is always a proposal tied to a snapshot and evidence; SQL records, source bytes, deterministic calculations and human decisions remain authoritative within their stated scope.

Use server-sent events or an equivalent event stream to display agent actions. For the hackathon, the web app may poll `GET /api/workspaces/{ws}/bundle` instead. Background runs persist checkpoints in SQL. Every tool call logs agent identity, permitted scope, input hash, output references, latency, and result status. Store concise decision rationales and evidence, not private chain-of-thought.

LangGraph is the selected target for the future multi-agent state machine: CFO plans → specialists investigate → Auditor challenges → evidence/human gates → briefing. Use persistent SQLite checkpoints during the hackathon. The first single-agent slice below uses a compact synchronous loop with persisted tool history; it does not yet implement LangGraph scheduling or automatic crash/evidence resumption. The future local extraction stack is NuExtract3 4B as the initial benchmark candidate, schema-constrained output, Pydantic validation, and offline TRL/PEFT LoRA training, subject to hardware and license verification. No model download or training is part of the first OpenAI-agent slice.

## 6. Financial data model

All monetary records carry `institution_id`, `currency`, `period_id`, `source_id`, `source_locator`, and `ingestion_batch_id`. Financial calculations use integer minor units or exact decimal arithmetic, never binary floating point.

| Entity | Required fields beyond common metadata |
| --- | --- |
| InstitutionProfile | jurisdiction, entity type, basis, fiscal calendar, currency, policy pack version |
| SourceDocument | immutable hash, filename, MIME type, source system, received timestamp, access classification |
| ExtractedField | field name, value, page/row/cell, extraction method, validation status, source version |
| Account | code, label, type, normal balance, statement mapping, effective dates |
| JournalEntry | entry ID, accounting date, status, originating system ID, reversal link, scenario ID |
| JournalLine | entry ID, debit, credit, account, school, department, program, management fund, award, counterparty |
| Invoice / InvoiceLine | vendor, invoice number, dates, amount, PO line, receipt line, service period, credits |
| FeeCharge | student reference, fee type, charge date, amount, optional waiver reference (stored; no check reads it yet, so a waived charge still reports as uncollected) |
| CashCollection | collector, collection date, method, amount, optional fee charge reference, optional pledge reference, optional deposit reference |
| BankDeposit | deposit date, bank reference, amount, optional deposit reference |
| SponsorPledge | sponsor, program, pledge date, due date, amount |
| Payment / PaymentApplication | bank item, payment amount, invoice/receivable allocation, residual amount |
| PurchaseOrder / Receipt | ordered, received, invoiced quantities and values; approval references |
| PayrollLine | employee ID, pay period, service period, gross pay, deductions, employer costs, allocation |
| Award | award ID, funder, approved amount, dates, reimbursement method, policy source, amendment version |
| BudgetLine | version, account/dimensions, period, adopted/revised amount, approval reference |
| Calculation | function/version, input IDs and versions, parameters, outputs, rounding policy, run ID |
| Finding | condition, criterion, evidence, counterevidence, amount basis, status, severity, action owner |
| AdjustmentProposal | balanced lines, justification, affected records, author, reviewer, version, approval |
| ReviewDecision | reviewer identity, decision, reason, source references, timestamp, supersession link |
| ReportSnapshot | scenario, source/ledger/graph versions, covered period, stale status, claim references |

Inbound school money is traced by reference, not by amount matching. A collection names the fee charge or the sponsor pledge it settles and the deposit reference it was banked under; a deposit answers for exactly one reference — its own deposit reference where the slip carries one, its bank reference otherwise — so no deposit can close two groups and report the same money as banked twice. References are compared with case and repeated spacing ignored, because staff write them by hand. A charge or a pledge is measured by its remainder, charged or pledged less collected, and only a positive remainder is reported, so an over-collection never nets off something else. An unmatched reference is an unreconciled difference to investigate, never a conclusion about the person who held the cash; a deposit no supplied receipt claims is reported on the deposit side and is not evidence of unrecorded revenue. Fee charges, collections, deposits and sponsor pledges are separate populations: a total from one is never added to a total from another.

Enforce idempotency on `(institution, source_system, source_record_id, source_version)`. A changed import version creates a superseding record with a reviewable diff; it does not silently overwrite facts. Preserve raw source values alongside normalized values.

## 7. Context graph and memory

### 7.1 Nodes and edges

Nodes: institution, school, department, program, award, account, vendor, employee, contract, invoice, payment, journal line, document, source span, policy clause, finding, hypothesis, calculation, review decision, precedent, report claim.

Edges include `ISSUED_BY`, `AUTHORIZED_BY`, `CHARGED_TO`, `FUNDED_BY`, `PAID_BY`, `MATCHED_TO`, `GOVERNED_BY`, `SUPPORTED_BY`, `CONTRADICTED_BY`, `DERIVED_FROM`, `REVIEWED_BY`, `SUPERSEDES`, and `DEPENDS_ON`.

Every edge has an ID, type, entity endpoints, institution, provenance, assertion class, valid-from/to dates, recorded-at timestamp, source version, verification status, and creating actor. Store graph revision numbers.

Assertion classes:

- **Observed:** a source contains a stated value; this does not itself establish truth.
- **Derived:** a deterministic calculation from identified inputs.
- **Hypothesized:** an agent inference awaiting testing.
- **Reviewed:** an authorized reviewer accepted a specific assertion within a scope.
- **Rejected/superseded:** retained for history and excluded from active truth queries.

Time has two meanings: when a fact applies and when the system learned it. Queries must support both so a later contract amendment does not rewrite what was knowable at the earlier close.

### 7.2 Example investigation path

`PAY-104 -> CHARGED_TO -> GRANT-STUDENT-SUPPORT`

`PAY-104 -> SUPPORTED_BY -> ALLOCATION-SHEET-SEP`

`ALLOCATION-SHEET-SEP -> CONTRADICTED_BY -> REVIEWED-SERVICE-RECORD`

`FINDING-07 -> DERIVED_FROM -> CALC-ALLOCATION-DELTA`

`REPORT-CLAIM-12 -> DEPENDS_ON -> CALC-ALLOCATION-DELTA`

Clicking any path opens the relevant row, page, or calculation. A graph visualization without actionable evidence traversal is insufficient.

### 7.3 Memory types

1. Working memory: run-local hypotheses and open questions, discarded or archived after the run.
2. Episodic memory: prior findings, investigations, and review outcomes; useful context but not automatically authoritative.
3. Reviewed procedural memory: approved allocation rules, matching precedents, and recurring exceptions, with explicit applicability tests. In the UI these are called **playbooks** (for example, PB-05, “same vendor and amount with different receipts → clear”).
4. Institutional context: organizational structure and policies anchored to authoritative source versions.

Precedent/playbook schema: `id, institution, domain, entity_scope, rule_summary, applicability_predicates, exclusions, valid_from, valid_to, source_ids, source_finding_ids, proposed_by, replay {months, new_false_positives, passed}, reviewer_id, review_time, supersedes_id, uses, status` where status ∈ `proposed | needs_approval | active | retired | blocked`.

Retrieval order: enforce tenant and access scope; filter by period and domain; traverse connected entities and policies; retrieve approved precedents; use semantic similarity only to rank remaining candidates. Similar text cannot override incompatible dates or scope.

### 7.4 Fast learning loop (RSI via playbooks)

1. **Notice:** an agent, usually the CFO Agent, sees the same pattern across findings or months.
2. **Propose:** it drafts a scoped playbook with scope, validity dates, exclusions, and source findings (`propose_playbook`). Status: `proposed`.
3. **Replay gate:** a deterministic runner re-runs the prior month or months with the playbook enabled. It must add **0 new false positives** against that month's reviewed outcomes. If it fails, the status is `blocked`: for example, PB-06 “auto-clear 100% allocation for dedicated staff” is blocked after 1 false clear. If it passes, the status is `needs_approval`.
4. **Human approval:** the playbook appears in Approvals. Only the human review service can activate it. Status: `active`.
5. **Use and re-check:** a later task retrieves the playbook and re-runs its applicability checks against current sources on every use. The decision record logs exactly how the playbook changed the next action, or why it was rejected.
6. **Retire:** a playbook whose governing source is superseded becomes `retired`, and the old version stays for history.

Do not self-edit production prompts or promote agent summaries into policy. In the online runtime, “learning” means controlled retrieval and reuse of reviewed playbooks, not silent prompt modification or weight updates. The replay gate is a guard against learning the wrong lesson, not proof of general improvement.

Negative-transfer example: September permits a 60/40 transportation allocation under contract A (PB-03). October contract B changes routes and allocation evidence. PB-03 must be flagged as inapplicable and retired, not copied because the vendor name matches.

### 7.5 Slow learning loop (offline local-model improvement)

The local extraction model may improve from reviewer corrections only through an offline, versioned promotion pipeline:

1. **Capture:** save the immutable source snapshot, schema version, base model, adapter version, model extraction and reviewer correction. Never store private chain-of-thought as training data.
2. **Qualify:** admit an example only when exact quotations resolve to the original source and a reviewer approves the corrected labels. Teacher-model or self-generated labels are proposals, not ground truth.
3. **Train a candidate:** start with supervised fine-tuning through a separate LoRA adapter. Preference optimization may be evaluated later when accepted/rejected pairs are numerous and representative. Never mutate the production adapter in place.
4. **Replay a frozen evaluation:** compare the base and candidate on held-out institutions and document templates. Required metrics include schema validity, field precision/recall/F1, exact dates/amounts/IDs, citation-span accuracy, unsupported extraction rate and abstention quality.
5. **Promote explicitly:** only an authorized human may activate an adapter that passes all regression thresholds. Record dataset hash, code version, hyperparameters, base-model hash, adapter hash, evaluation result and approval. Keep the prior version available for rollback.
6. **Monitor and retire:** route low-confidence or out-of-distribution documents to review, collect corrections for the next candidate, and retire adapters whose governing schemas or source formats change.

Research patterns such as reflection or self-training may propose retries and candidate examples, but production outputs must never recursively become training truth merely because the model generated them. This prevents feedback-loop amplification, model collapse and prompt-injection content from entering model weights. Raw institutional documents require an authorized retention and training policy before they can enter any training corpus.

The initial local extraction candidate should use JSON-schema-guided document extraction with a small open-weight model specialized for structured extraction. NuExtract-class models, Pydantic schemas and constrained decoding are implementation candidates, not fixed requirements; select the final model through hardware, license, citation-accuracy and held-out evaluations. The API-agent and local-extractor contracts remain separate so either can be replaced independently.

### 7.6 Invalidation and concurrency

When a source, ledger scenario, policy, or approved decision changes, mark all transitively dependent calculations and claims stale. Recompute in dependency order and publish a new report snapshot only after invariant checks pass. Old snapshots remain immutable and visibly dated.

Workers write using optimistic version checks. The graph projection carries the SQL ledger revision; a mismatched projection cannot support a final report. Outbox events allow failed graph updates to replay without losing financial changes.

## 8. Agent contracts and orchestration

### Connected five-agent implementation checkpoint (2026-09-19)

Route names in this dated checkpoint are the ones that existed on 2026-09-19. The app's routes have since
collapsed to `/` (Books), `/investigation` and `/briefing`, plus `/access` and `/login`; the pages named
below no longer exist and the one-click fictional scan has been removed.

The `max` branch exposed a **Five-agent workflow · uploaded records** option on
`/cfo`, linked from the Command center. A committed immutable intake snapshot flows
through CFO planning → AP & Payments, Payroll & Budget, Grants & Compliance →
independent Internal Auditor review → CFO report. All three specialist domains are
assigned; absent records produce explicit gaps, not invented clean results.
The coordinator enforces scoped evidence, deterministic calculation provenance,
fresh Auditor reads/reperformance, bounded retries and stale-snapshot rejection.
No payment or posting tools are exposed. Clients/budgets are invocation-local.

This is a bounded investigation workflow, not the full benchmark implementation.
AP/Grants observations are supported. The laptop director workflow now additionally
publishes exact-key invoice duplicate candidate amounts and expense budget variance
through the deterministic evidence gateway. These are bounded checks, not complete
AP/payment or grant eligibility assurance.

That home page offered a one-click fictional scan. `/scan`, Findings, Follow-up,
Reports and the uploaded-workspace overview shared a snapshot-aware review feed:
rules checks, latest standalone candidates and final Auditor-accepted central claims
are labelled separately. A human may assign an owner, request evidence and decide
a proposed correction; version checks and history preserve the distinction between
proposal acceptance and financial execution. Source commits invalidate applicability
of older decisions. Reports export current evidence and explicit gaps.

Laptop safeguards include loopback/origin restrictions, optional account sessions,
role/workspace permissions, protected local file permissions and admin-confirmed
logical deletion. This does not establish enterprise privacy compliance, encrypted
storage or an Ontario accounting profile. Model training, complete PO/receipt matching,
statutory statements, a global dollar-cost ceiling and held-out model accuracy remain
future work. `DEMO_IMPLEMENTATION.md` documents the demo, tests and deployment gates.

Five roles, shown in the UI as an Office of the CFO:

| Display name | Role | Owns |
| --- | --- | --- |
| CFO Agent | Lead investigator / orchestrator | Plan, task assignment, briefing, final report, playbook proposals |
| AP & Payments agent | Transaction detective | AP/AR, 3-way match, duplicates, bank, payment batches |
| Payroll & Budget agent | Payroll/budget analyst | Payroll tie-out, allocations, variance bridge, budget |
| Grants & Compliance agent | Restricted-funds specialist | Award terms, windows, allowability, award schedule |
| Internal Auditor agent | Independent auditor | Re-performs calculations from originals; accept/reject/needs_evidence |

### 8.1 First live slice: CFO snapshot triage

Integration status: `app/agents/cfo.py` powers live snapshot triage from the records panel on `/` (Books).
The separately merged `app/cfo/` coordinator exposes `/api/cfo/runs`, with scripted specialists
and independent-review gates; its `/cfo` page has been removed, and the client calling those endpoints
(`web/src/components/investigation/`) is not yet composed into `/investigation`. Its intake bridge exists, but live specialist/auditor adapters remain
unregistered. The two execution paths are not yet unified; suggested triage tasks are not auto-dispatched.
The coordinator's optional local CFO adapter is experimental and is not the planned local document extractor.

The first implemented live role is a bounded CFO triage agent. It runs synchronously for the local hackathon build against exactly one current immutable snapshot. The API key exists only in the FastAPI process environment and is never returned to or entered in the browser. The request uses provider storage disabled where supported.

The CFO receives no database connection, arbitrary file path, shell, web search or mutation tool. Its initial tool allowlist is: read workspace/snapshot context, list sources, literal-search source lines, read a bounded source span, list paginated normalized records by role and run deterministic ledger import-control totals across the entire pinned ledger. Cross-workspace IDs and sources outside the pinned snapshot are rejected. The limits are 12 actual tool calls, one active CFO run per workspace, four minutes per run, 60 seconds per provider request, 2,500 output tokens per response, 60,000 conversation bytes and a conservative 100,000 cumulative token ceiling. The model is configurable. Request IDs prevent duplicate runs; expected snapshot IDs reject stale starts. Completed steps survive failures, and abandoned runs expire after the deadline plus 30 seconds.

The required final call is a structured submission containing a concise executive briefing, scope assessed, limitations, candidate findings, evidence requests and proposed specialist tasks. Citations must identify an authorized source and exact line with a verbatim substring; the application re-validates them before accepting the run. A non-`needs_evidence` candidate requires at least one valid citation. The runtime persists the model ID, snapshot, status, timestamps, token usage, hashed tool inputs, output references, latency and concise decision record. It never stores private chain-of-thought.

The agent must inspect the source inventory before submission. Bounded original-source previews help distinguish missing evidence from present-but-unreviewed evidence. Normalized amounts are integer cents; ledger tools also return formatted display amounts. A supplemental validator rejects currency-prefixed amounts absent from inspected records or tool results. This is a narrow unit-error guard, not a proof of all monetary prose or of the financial interpretation; independent review remains required.

This first role may label an item only `hypothesized`, `needs_evidence` or `cleared`. It cannot substantiate a final finding, approve an adjustment, verify population completeness or issue an audit opinion. Those transitions require specialist work, independent Auditor review and human gates. A model call failure or exhausted tool budget produces a visible failed run; it does not fall back to invented fixture findings.

`cleared` in the raw triage output means proposed clearance pending independent review. The Findings dashboard presents it as an unreviewed hypothesis, and the source panel labels it explicitly. Citation validation checks location and verbatim text, not semantic correctness of the inference. Evidence requests and proposed specialist tasks are suggestions; a user can add a suggested request to the intake evidence queue. New snapshots require an explicit rerun; old results remain accessible and visibly stale.

The human user is the real CFO or controller and approves every adjustment, payment release, and playbook activation. Reuse a model if necessary but separate role context, tools, and permissions. Model diversity is optional and does not guarantee independence.

Specialists may investigate concurrently against an immutable snapshot. They cannot approve their own proposals. The auditor receives the submitted claim and evidence references, then retrieves originals and re-performs calculations rather than merely reviewing persuasive prose.

Required response contract:

```json
{
  "task_id": "TASK-104",
  "status": "needs_evidence",
  "snapshot_id": "SNAP-SEP-01",
  "claims": [{
    "claim_id": "CL-7",
    "text": "The allocation requires review.",
    "assertion_class": "hypothesized",
    "evidence_ids": ["SPAN-42"],
    "counterevidence_ids": [],
    "calculation_ids": [],
    "limitations": ["Current service allocation record missing"]
  }],
  "proposed_adjustment_ids": [],
  "evidence_requests": [{"record_type": "service_allocation", "period": "2026-09", "reason": "Test allocation basis"}],
  "memory_used": [],
  "decision": {
    "id": "DEC-0412",
    "run": "RUN-SEP-03",
    "time": "2026-10-02T14:02:52Z",
    "agent": "internal_auditor",
    "action": "Rejected claim CL-7",
    "summary": "No current service record; a budget % is not proof of work.",
    "when": {"run": "RUN-SEP-03", "step": "22 of 38", "started": "14:02:43", "finished": "14:02:52", "trigger": "CL-7 submitted with budget sheet only"},
    "how": [{"tool": "read_source_span", "input": "GRANT-SS §4.2", "output": "shared staff need service records"}],
    "why": "Award terms require actual service records; none exist yet.",
    "alternatives": [
      {"option": "Mark needs_evidence", "reason": "Plausible but unsupported", "chosen": true},
      {"option": "Accept CL-7", "reason": "No evidence of actual work", "chosen": false}
    ],
    "memory_checks": [],
    "outcome": "CL-7 -> needs_evidence; evidence requested",
    "evidence": ["CL-7", "GRANT-SS §4.2"]
  },
  "next_action": "await_document"
}
```

The `decision` block is a concise, structured rationale that the agent emits with each action. It feeds the Reasoning log. It is not raw chain-of-thought. Tool calls in `how` must match the logged tool events, and amounts must reference calculation IDs.

Allowed task statuses: `queued`, `running`, `needs_evidence`, `submitted`, `review_rejected`, `review_accepted`, `failed`, `cancelled`. Agent board columns map to them as follows: `queued`→Queued, `running`→Working, `needs_evidence`→Needs you, `submitted`→Auditor review, `review_accepted`→Done. `review_rejected` returns the task to Working with the reviewer's challenge, and `failed`/`cancelled` show as badges. Each task also exposes `progress` (steps done / total), `eta`, the ordered `steps` (done/running/pending), agent `todos`, and tool budget used. Findings use a separate lifecycle: `candidate -> investigating -> needs_evidence / substantiated / cleared -> action_proposed -> approved -> resolved`, with reopening on new evidence. Resolution requires verified remediation, not just report publication.

The CFO Agent chooses follow-ups based on evidence gaps and reviewer challenges. Deterministic workflow logic enforces permissions, bounds, and transitions; it must not hard-code the planted issue conclusions.

Default run limits: five agents, two concurrent specialist calls, 12 tool calls per task, two review cycles per finding, configurable total token/cost ceiling, and a visible stop reason on exhaustion. A bounded run may end partially complete with unresolved questions rather than manufacturing an answer.

### Tool surface

- `search_sources(filters, query)` and `read_source_span(id)` return authorized evidence with locators.
- `query_financial_records(template_id, parameters, snapshot_id)` executes allowlisted parameterized queries.
- `traverse_context(start_ids, edge_types, depth, as_of, snapshot_id)` returns bounded paths.
- `calculate(function_id, input_ids, parameters)` returns exact outputs and lineage.
- `retrieve_precedents(scope, period)` returns candidates and applicability results.
- `submit_finding(payload)` and `propose_adjustment(payload)` validate schemas and append proposals.
- `request_evidence(payload)` adds an in-app request; it sends nothing externally.
- `submit_review(finding_id, decision, evidence)` records the auditor's review, not human financial approval.
- `propose_playbook(payload)` drafts a scoped playbook and queues the replay gate; it cannot activate anything.
- `prepare_payment_batch(invoice_ids)` assembles a simulated batch and holds flagged items; it cannot release funds.

Only the authenticated human review service can approve an adjustment, release a (simulated) payment batch, or activate a playbook or procedural memory. Runtime agents cannot access evaluator labels, unrestricted filesystem paths, arbitrary SQL, a shell, or payment tools.

### 8.2 Grants & Compliance direct-run specialist

`api/app/agents/grants.py` implements the second live role using the same bounded, read-only snapshot
runtime as CFO triage. Select it in the records panel on `/` (Books); API requests use `agent: "grants_compliance"`.
It reviews uploaded award terms and supporting evidence, with no web research or inferred legal rules.
The local document extraction model is still a separate future component.

The additional `check_grant(award_id)` tool computes exact supplied-payroll allocation totals across
all pinned records and compares service periods inclusively with a uniquely identified award window.
It reports ceiling comparison, per-record source locators, input hash, result truncation and scope limits.
Missing/ambiguous award definitions produce unknown checks. Payroll and ledger totals are not combined.
These totals are not lifetime grant expenditure, remaining funds, allowable cost or a proposed adjustment.
Original terms, extensions and service evidence still require interpretation and independent review.

The agent must inspect source context and run a deterministic grant check when normalized award/payroll
records exist. It returns cited hypotheses, evidence requests and proposed follow-ups; raw proposed
clearances stay unreviewed in the UI. Citation validation does not establish semantic correctness.
In synthetic workspaces it assesses consistency within the fictional scenario rather than treating the
synthetic label itself as a financial exception. `GRANTS_MODEL` may override the shared `OPENAI_MODEL`.

The current-snapshot results for both CFO and Grants coexist in the review feed on `/investigation`. Role-specific
history survives reruns; new snapshots visibly stale prior runs. One snapshot-agent run at a time is
allowed per workspace, and idempotency includes the selected role. Coordinator automatic dispatch,
and complete grant expenditure schedules remain future integrations. Direct Auditor review is now implemented in §8.3.

### 8.3 Internal Auditor direct-run review

`api/app/agents/auditor.py` implements an independent reviewer context, selected as `internal_auditor`
in the same endpoint and the same records panel. At least one current-snapshot CFO/Grants finding is required.
It pins exact preparer run/finding IDs at startup, treats their text as untrusted claims, and returns
up to four explicit accept/reject/needs_evidence verdicts. Remaining candidate IDs/counts are recorded.

Acceptance/rejection requires explicit fresh `read_source_span` calls for the claim's cited lines;
preparer quotations and automatic context previews do not satisfy that gate. Acceptance additionally
requires reperformance of supporting calculations, including checks inferred from cited financial
record types if the preparer omitted a calculation. The Auditor reparses original immutable CSV bytes
with the shared exact parser, reconciles them to pinned normalized records, and recomputes results.
Integrity mismatches block acceptance. Shared parser/math bugs remain a limitation: this is a separate
execution and review context, not an independently implemented accounting engine or guaranteed semantic truth.

Each verdict includes original citations, rationale and required action for rejected/unresolved claims.
Accepted evidence-gap observations do not clear the underlying transaction. Findings retain candidate
status; no accounting approvals, compliance certifications or audit opinions are issued. UI annotations
match exact target IDs, so even a same-snapshot preparer rerun cannot inherit an old verdict. Historical
reviews remain available with stale-target warnings. `AUDITOR_MODEL` can select a different API model;
successive runs prioritize previously unreviewed targets. Latest per-finding verdicts from the last
20 completed audits remain attached to matching current findings, even when a later audit reviews a different subset.
model diversity alone is not independence. Automatic coordinator dispatch/review remains a future adapter
integration, and no local model training is included.

## 9. Deterministic accounting and outputs

The accounting engine imports existing entries and computes opening balance + period activity = closing balance. It checks journal balance, statement mapping, subledger control totals, and source coverage before agents interpret results.

Required outputs:

1. As-reported and approved-scenario general ledger and trial balance.
2. Simplified management balance sheet and revenue/expense statement, clearly labeled by basis and period.
3. AP/AR aging with outstanding balances and unapplied cash.
4. Bank reconciliation with matched, timing, and unresolved differences.
5. Department/program budget versus actual with separate commitments.
6. Restricted-award schedule showing award ceiling, approved changes, supported charges, disputed charges, reimbursements, and remaining capacity; these are distinct measures.
7. Payroll reconciliation and variance bridge.
8. Thirteen-week cash forecast with dated receipt/payment assumptions and restricted cash availability constraints.
9. Findings report, proposed adjustment register, and action plan.
10. Evidence index / prepared-by-client workpaper bundle.

Hackathon cut: outputs 3, 4, and 8 (AP/AR aging, bank reconciliation, 13-week cash forecast) are deferred unless there is time left. Build outputs 1, 2, 5, 6, 7, 9, and 10 first. See the cut list in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

Reports share snapshot IDs and calculation results. A narrative claim must reference a source span or calculation; amounts are injected from validated data, not regenerated by the LLM. Budget remaining, award capacity, fund allocation, net assets, and spendable cash are not interchangeable.

## 10. Finding and report quality

Every finding includes: condition, applicable criterion and version, affected population, evidence, counterevidence, quantified effect, unknowns, hypothesized cause, proposed remediation, owner, due date, and review status. Cause remains tentative unless evidenced.

Separate actual cash loss, potential recovery, accounting reclassification, unsupported charge exposure, and forecast risk. Do not add overlapping amounts into one “money saved” number. Track overlap groups and unique affected transactions.

Product severity (`high/medium/low`) is separate from formal audit classifications. A missing receipt is an evidence gap; it is not automatically misuse. A payroll increase despite enrollment decline may be legitimate because of wage rates, staffing commitments, or service needs.

Report sections: executive summary; scope and coverage; reviewed findings; pending evidence; proposed adjustments; financial effects; action register; methodology and limitations; evidence appendix. Include an explicit statement when an investigation could not finish.

## 11. Interface

Visual style: clean fintech. White surfaces, Inter, a teal `#0F766E` accent, rounded cards, and status pills. The approved prototype is `docs/design/prototype.html`.

**The AI must be visibly present.** A viewer should see agents working, not a static dashboard. This means the CFO Agent's AI briefing, an animated “doing X…” status per agent, an “N agents working” indicator in the top bar, ✦ tags on AI-generated content, agent badges on every row, and an “Ask your finance team” command bar.

**Workspace switcher** (top of the sidebar): `MIT FY2025 · Public` (read-only public-report explorer) ⇄ `Sandbox University · Synthetic`. Persistent badges show `Public report` / `Synthetic scenario` and `Live run` / `Recorded run` / `Scripted preview`.

**Shipped navigation (2026-09-20):** the app serves three destinations — `/` (Books, where records go in),
`/investigation` and `/briefing` — plus `/access` and `/login`. The workspace switcher lists uploaded
schools only; the fixed MIT and Sandbox workspaces are not currently reachable. The eight-tab layout below
is the original design, not the routes the app serves: `/command`, `/board`, `/workflows`, `/findings`,
`/approvals`, `/reports`, `/reasoning` and `/learning` do not exist. Where the design is still wanted, it
has to fit inside the three destinations.

**8 tabs in 3 groups (original design):**

| Group | Tab | Contents |
| --- | --- | --- |
| Office of the CFO | Command center | CFO Agent AI briefing (what the team did, what needs you), live agent team strip, workflow progress, KPIs (flagged amount with cash impact, tasks done, playbooks used/rejected, questions to you), stale-data banner |
| | Agent board | Kanban: Queued / Working / Needs you / Auditor review / Done (status mapping in §8). Working cards show the current step, % progress, and ETA. Clicking a card opens a drawer with steps (done/running/pending, with tool call and result), progress, ETA, tool budget, agent to-dos, and the decision rationale |
| | Workflows | Month-end close, payroll, AP & payments, grant compliance, and audit prep as stage pipelines, each with an owner agent. ✋ marks human gates (approve adjustments, release payments, upload evidence) |
| Work product | Findings | Findings list (amount category, status, finding agent, verifying agent), plus the evidence trail: the context-graph path from source to calculation to finding, with each node opening the source page/row or calculation. There are no unreviewed accusation headlines |
| | Approvals | Human queue: journal corrections (before/after entries, exact effects, cash impact), simulated payment batch release (with held items), playbook activation, and evidence requests. It handles version conflicts |
| | Reports | AI-written close pack generated only from verified findings and calculations, with a baseline vs approved-scenario comparison. Export to Markdown/CSV/JSON; PDF is optional |
| Agent brain | Reasoning log | Every agent decision across runs and months, filterable by agent, month, and memory use, with an “ask why” search. Each entry expands to WHEN (run, step, started/finished, trigger), HOW (tool calls with inputs → outputs), WHY (rationale), WHY THIS OVER ALTERNATIVES (options considered, chosen vs rejected with a reason), MEMORY CHECKS, and OUTCOME, all from the §8 `decision` record |
| | Learning | RSI loop (§7.4), playbooks table (source finding, proposing agent, replay result, uses, status), and memory on vs off comparison. Measured numbers come only from saved evaluator output; otherwise they are labeled as example values |

In the MIT workspace, Workflows, Approvals, and Learning are disabled. Command center, Findings, Reports, and Reasoning log show public-report content only: the published opinions, “no findings reported,” the pledge rollforward tie, and the FY2024/FY2025 comparison.

## 12. Security and failure handling

Use synthetic data for the hackathon. For future real deployments, minimize personal data, use aggregate enrollment, restrict payroll access, and establish institution-specific retention and model-provider policies. FERPA relevance depends on the data and institution; do not claim a compliant deployment from this design alone. See [SOURCES.md](SOURCES.md).

All imported document content is untrusted data. Embedded instructions cannot grant tools, approve changes, redefine policy, or request secrets. Hash sources; preserve locators; enforce tenant scope server-side. Redact sensitive values from logs and exports according to role.

Recovery behaviors: quarantine malformed imports; show OCR uncertainty; keep conflicting documents; stop on unknown currencies/basis; block unbalanced entries; retry transient model failures within limits; make job restarts idempotent; invalidate stale reports; expose incomplete runs. Append-only application logs are auditable history, not a claim of tamper-proof infrastructure.

## 13. Acceptance criteria

**[demo]** marks the criteria that must be met for the hackathon demo. The others are met if time allows, or honestly marked incomplete in the README.

- AC-01: Reimporting a source does not double-count a financial event.
- AC-02 **[demo]**: All accepted journals balance exactly; invalid or unknown mappings block final statements.
- AC-03: Ledger, statements, schedules, and report claims tie to the same snapshot.
- AC-04 **[demo]**: At least three specialists perform distinct evidence-driven investigations and an auditor rejects or revises an unsupported claim.
- AC-05 **[demo]**: A finding can be traced through the graph to original evidence and a reproducible calculation.
- AC-06 **[demo]**: Human-approved correction changes the proper downstream outputs; a pure allocation correction leaves total cash unchanged.
- AC-07 **[demo]**: Month-two memory retrieval changes a logged action; expired or conflicting memory is rejected.
- AC-08: With-memory and without-memory evaluations use identical month-two evidence, accounting state, model settings, and budgets. (Required before any memory metric is shown.)
- AC-09 **[demo]**: Unresolved cases remain unresolved; reports do not fabricate missing facts or declare a clean audit.
- AC-10 **[demo]**: Runtime tools cannot retrieve private grader labels or perform real financial actions.
- AC-11: A changed source invalidates dependent reports; stale reports cannot be presented as current.
- AC-12 **[demo]**: All metric claims come from saved evaluator output, with sample size and limitations. Otherwise they are labeled as example values.
- AC-13 **[demo]**: Every agent action shown in the Reasoning log comes from a saved decision record whose tool calls match logged tool events.
- AC-14 **[demo]**: No playbook becomes active without passing the replay gate (0 new false positives) and a human approval. A failed replay leaves it `blocked`.
- AC-15 **[demo]**: Payment batches and payroll reallocations are prepared by agents, released only by a human, and simulated. Items with vendor bank-detail changes are held.

## 14. Maximor alignment

| Track criterion | Demonstration |
| --- | --- |
| Office of the CFO | CFO Agent plus AP & Payments, Payroll & Budget, Grants & Compliance, and Internal Auditor running close, payroll, AP & payments, grant compliance, and audit-prep workflows |
| Multi-step reasoning over documents | Trace a payroll allocation through service evidence, grant terms, ledger, and report |
| Multi-agent coordination | Specialist handoffs, reviewer challenge, targeted evidence request, all visible live on the Agent board |
| Memory/context changes behavior | Reviewed September playbook changes October retrieval and checks; a stale playbook is retired (Learning tab, Reasoning log) |
| Explainability | Each action's when/how/why/alternatives, taken from the saved decision records |
| Long horizon | Two closes with carry-forward balances, recurring issues, and amended contracts |
| Consistency across workflows | One approved correction recomputes several dependent outputs |
| Human uncertainty handling | Evidence request and explicit approval before scenario application |
| Own measure of better | Hidden issue detection plus false positives, consistency, interventions, and memory ablation |

Supporting documents: [accounting](ACCOUNTING_CONTROLS.md), [evaluation](DATA_AND_EVALUATION.md), [implementation](IMPLEMENTATION_PLAN.md), [role prompts](AGENT_PROMPTS.md), [handoff](BUILD_PROMPT.md), [demo](DEMO.md), [sources](SOURCES.md).
# Implementation checkpoint: document lifecycle and incremental updates

The `max` implementation now includes a laptop-local document/extraction review
pipeline and a benchmark-gated release workflow; see `EXTRACTION_IMPLEMENTATION.md`
for the precise interface, thresholds, limitations and partner training handoff.
PDF/image originals are retained; local preprocessing produces page text, and
reviewed extracted fields link back to original pages. OCR and field corrections
are versioned. Only human-approved fields enter staged intake; normal validation
and explicit commit still apply. Uploaded files can be appended or versioned in
an existing institution. The dashboard shows snapshot changes and offers explicit
rules-only or live five-agent rescans. No unseen file silently triggers paid calls.

The improvement workflow supports permissioned correction datasets, frozen train
and held-out splits, immutable model manifests, paired benchmark jobs, promotion,
rollback and retirement. It does not train weights: partner models implement the
versioned local page-text extraction contract. Thresholds are engineering gates,
not measured accuracy. Promotion requires benchmark results and admin approval;
model output never becomes training truth automatically. No recursive weight
updates, automatic drift detector or hosted multi-tenant security is claimed.
