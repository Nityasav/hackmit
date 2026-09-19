# SchoolTrace — Product and Technical Specification

Version: 1.0 | Date: 2026-09-19 | Status: implementation-ready hackathon design

### Showcase update

The revised [DEMO.md](DEMO.md) is authoritative for presentation flow: a read-only MIT public-report explorer followed by a synthetic university investigation, with explicitly labeled hybrid/replay execution. Public documents are permitted inputs to this explorer; synthetic-only restrictions continue to govern transaction fixtures and benchmark data. The explorer does not claim access to MIT's internal ledger or implement statutory university accounting. Existing accounting, review, and evaluation requirements remain in force. Authored scripted previews may illustrate incomplete capabilities but do not satisfy agentic acceptance criteria or count as measured results.

## 1. Purpose and problem

Educational institutions can have substantial finance and compliance teams and still lose track of how money was allocated, approved, paid, and reported. Payroll, procurement, grants, enrollment, and facilities operate in separate systems. A transaction can be valid in one system but incorrectly classified, insufficiently supported, or duplicated elsewhere.

The product hypothesis is that these disconnected records and unresolved exceptions create preventable audit-readiness problems. Consequences can include rework, repayment exposure, distorted spending decisions, and disruption to services students depend on. Funding and financing consequences are possible, not automatic. Do not claim all schools mismanage money or invent prevalence statistics. See [SOURCES.md](SOURCES.md).

SchoolTrace collects financial records, establishes a traceable accounting baseline, and coordinates agents to answer: **What is wrong, what evidence proves it, what remains uncertain, and what action would resolve it?**

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
5. Ask: “Enrollment fell 6%. Why did staffing costs rise, and why is the student-support grant nearly exhausted?”
6. Lead investigator creates hypotheses and specialist tasks. Each task has a question, permitted data scope, expected evidence, and stopping condition.
7. Specialists use typed tools and the context graph. They return findings, counterevidence, calculations, and requests for missing records.
8. Auditor independently re-performs critical calculations and checks original sources. Unsupported conclusions are rejected or downgraded.
9. Human reviews unresolved evidence requests and proposed adjustments. Any requested clarification stays in the local review queue.
10. An approved scenario recomputes dependent schedules and reports. The as-reported baseline remains accessible.
11. Lead investigator produces the final evidence-backed report and action register, including unresolved limitations.
12. Reviewed decisions eligible for reuse become scoped memory. Month two demonstrates changed investigation behavior.

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
                 lead investigator
                 /       |        \
          transactions  payroll   restricted funds
                 \       |        /
                    auditor review
                           |
                  human review queue
                           |
              approved scenario / recompute
                           |
           reports + workpapers + evaluation logs
```

Recommended implementation shape: TypeScript web UI, Python API and worker, PostgreSQL, SQL graph tables, local file storage, and one provider-neutral model adapter. A dedicated graph database is optional; typed edges, temporal filtering, traversals, and provenance are required regardless of storage. Confirm supported library versions during implementation rather than relying on unverified SDK names in a challenge brief.

Use server-sent events or an equivalent event stream to display agent actions. Background runs persist checkpoints in SQL. Every tool call logs agent identity, permitted scope, input hash, output references, latency, and result status. Store concise decision rationales and evidence, not private chain-of-thought.

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
3. Reviewed procedural memory: approved allocation rules, matching precedents, and recurring exceptions, with explicit applicability tests.
4. Institutional context: organizational structure and policies anchored to authoritative source versions.

Precedent schema: `id, institution, domain, entity_scope, rule_summary, applicability_predicates, exclusions, valid_from, valid_to, source_ids, reviewer_id, review_time, supersedes_id, status`.

Retrieval order: enforce tenant and access scope; filter by period and domain; traverse connected entities and policies; retrieve approved precedents; use semantic similarity only to rank remaining candidates. Similar text cannot override incompatible dates or scope.

### 7.4 Learning loop

Agent proposes memory -> reviewer checks evidence and scope -> approved memory is persisted -> later task retrieves it -> current source checks pass or invalidate it -> decision records exactly how memory affected the next action.

Do not self-edit production prompts or promote agent summaries into policy. “Learning” in the MVP means controlled retrieval and reuse, not fine-tuning.

Negative-transfer example: September permits a 60/40 transportation allocation under contract A. October contract B changes routes and allocation evidence. The prior memory must be flagged as inapplicable, not copied because the vendor name matches.

### 7.5 Invalidation and concurrency

When a source, ledger scenario, policy, or approved decision changes, mark all transitively dependent calculations and claims stale. Recompute in dependency order and publish a new report snapshot only after invariant checks pass. Old snapshots remain immutable and visibly dated.

Workers write using optimistic version checks. The graph projection carries the SQL ledger revision; a mismatched projection cannot support a final report. Outbox events allow failed graph updates to replay without losing financial changes.

## 8. Agent contracts and orchestration

Five roles: lead investigator; transaction detective; payroll/budget analyst; restricted-funds specialist; independent auditor. Reuse a model if necessary but separate role context, tools, and permissions. Model diversity is optional and does not guarantee independence.

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
  "next_action": "await_document"
}
```

Allowed task statuses: `queued`, `running`, `needs_evidence`, `submitted`, `review_rejected`, `review_accepted`, `failed`, `cancelled`. Findings use a separate lifecycle: `candidate -> investigating -> needs_evidence / substantiated / cleared -> action_proposed -> approved -> resolved`, with reopening on new evidence. Resolution requires verified remediation, not just report publication.

Lead investigator chooses follow-ups based on evidence gaps and reviewer challenges. Deterministic workflow logic enforces permissions, bounds, and transitions; it must not hard-code the planted issue conclusions.

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

Only the authenticated human review service can approve an adjustment or activate procedural memory. Runtime agents cannot access evaluator labels, unrestricted filesystem paths, arbitrary SQL, a shell, or payment tools.

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

Reports share snapshot IDs and calculation results. A narrative claim must reference a source span or calculation; amounts are injected from validated data, not regenerated by the LLM. Budget remaining, award capacity, fund allocation, net assets, and spendable cash are not interchangeable.

## 10. Finding and report quality

Every finding includes: condition, applicable criterion and version, affected population, evidence, counterevidence, quantified effect, unknowns, hypothesized cause, proposed remediation, owner, due date, and review status. Cause remains tentative unless evidenced.

Separate actual cash loss, potential recovery, accounting reclassification, unsupported charge exposure, and forecast risk. Do not add overlapping amounts into one “money saved” number. Track overlap groups and unique affected transactions.

Product severity (`high/medium/low`) is separate from formal audit classifications. A missing receipt is an evidence gap; it is not automatically misuse. A payroll increase despite enrollment decline may be legitimate because of wage rates, staffing commitments, or service needs.

Report sections: executive summary; scope and coverage; reviewed findings; pending evidence; proposed adjustments; financial effects; action register; methodology and limitations; evidence appendix. Include an explicit statement when an investigation could not finish.

## 11. Interface

- Overview: period, profile, snapshot, reviewed exposure, open questions, coverage, stale-data banner.
- Investigation workspace: task timeline, current hypothesis, evidence requests, actual tool events, review outcomes.
- Evidence pane: document page/CSV row and source highlight beside the claim.
- Context graph: focused neighborhood with assertion class, date, source, and supersession filters.
- Findings list: amount category, status, severity, owner, evidence strength; no unreviewed accusation headlines.
- Review drawer: before/after entries, exact financial effects, approver, reason, and version conflict handling.
- Reports: baseline/scenario comparison and downloadable Markdown/CSV/JSON; PDF is optional.
- Evaluation page: hidden-run metrics only after scoring, memory comparison, costs and failures.

## 12. Security and failure handling

Use synthetic data for the hackathon. For future real deployments, minimize personal data, use aggregate enrollment, restrict payroll access, and establish institution-specific retention and model-provider policies. FERPA relevance depends on the data and institution; do not claim a compliant deployment from this design alone. See [SOURCES.md](SOURCES.md).

All imported document content is untrusted data. Embedded instructions cannot grant tools, approve changes, redefine policy, or request secrets. Hash sources; preserve locators; enforce tenant scope server-side. Redact sensitive values from logs and exports according to role.

Recovery behaviors: quarantine malformed imports; show OCR uncertainty; keep conflicting documents; stop on unknown currencies/basis; block unbalanced entries; retry transient model failures within limits; make job restarts idempotent; invalidate stale reports; expose incomplete runs. Append-only application logs are auditable history, not a claim of tamper-proof infrastructure.

## 13. Acceptance criteria

- AC-01: Reimporting a source does not double-count a financial event.
- AC-02: All accepted journals balance exactly; invalid or unknown mappings block final statements.
- AC-03: Ledger, statements, schedules, and report claims tie to the same snapshot.
- AC-04: At least three specialists perform distinct evidence-driven investigations and an auditor rejects or revises an unsupported claim.
- AC-05: A finding can be traced through the graph to original evidence and a reproducible calculation.
- AC-06: Human-approved correction changes the proper downstream outputs; a pure allocation correction leaves total cash unchanged.
- AC-07: Month-two memory retrieval changes a logged action; expired or conflicting memory is rejected.
- AC-08: With-memory and without-memory evaluations use identical month-two evidence, accounting state, model settings, and budgets.
- AC-09: Unresolved cases remain unresolved; reports do not fabricate missing facts or declare a clean audit.
- AC-10: Runtime tools cannot retrieve private grader labels or perform real financial actions.
- AC-11: A changed source invalidates dependent reports; stale reports cannot be presented as current.
- AC-12: All metric claims come from saved evaluator output, with sample size and limitations.

## 14. Maximor alignment

| Track criterion | Demonstration |
| --- | --- |
| Multi-step reasoning over documents | Trace a payroll allocation through service evidence, grant terms, ledger, and report |
| Multi-agent coordination | Specialist handoffs, reviewer challenge, targeted evidence request |
| Memory/context changes behavior | Reviewed September precedent affects October retrieval and checks |
| Long horizon | Two closes with carry-forward balances, recurring issues, and amended contracts |
| Consistency across workflows | One approved correction recomputes several dependent outputs |
| Human uncertainty handling | Evidence request and explicit approval before scenario application |
| Own measure of better | Hidden issue detection plus false positives, consistency, interventions, and memory ablation |

Supporting documents: [accounting](ACCOUNTING_CONTROLS.md), [evaluation](DATA_AND_EVALUATION.md), [implementation](IMPLEMENTATION_PLAN.md), [role prompts](AGENT_PROMPTS.md), [handoff](BUILD_PROMPT.md), [demo](DEMO.md), [sources](SOURCES.md).
