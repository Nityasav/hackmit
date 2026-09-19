# Copy-paste implementation prompt

Give the following prompt to a coding agent with all files in this specification directory available. The requested deliverable is an implemented application; this package itself is the design input.

---

Build **SchoolTrace**, a working hackathon application for the Maximor Office of the CFO track. It is a multi-agent financial detective for educational institutions, starting with a fictional school district and two monthly accounting periods.

Read the entire provided specification package before implementing:

1. `spec.md`
2. `ACCOUNTING_CONTROLS.md`
3. `DATA_AND_EVALUATION.md`
4. `AGENT_PROMPTS.md`
5. `IMPLEMENTATION_PLAN.md`
6. `DEMO.md`
7. `SOURCES.md`

Treat `spec.md` as the product/architecture authority, `ACCOUNTING_CONTROLS.md` as the accounting contract, and `DATA_AND_EVALUATION.md` as the evaluation contract. If there is a conflict, document it and choose the narrower behavior that preserves evidence, accounting correctness, and honest reporting. Do not silently broaden the jurisdiction or accounting basis.

Follow the revised DEMO.md for presentation: MIT public-report exploration followed by a synthetic university sandbox. Public reports are allowed for the read-only explorer; do not fabricate MIT transactions or mix them into the synthetic benchmark. Preparsed evidence and cached completed agent runs are encouraged for speed. Clearly labeled authored scripted previews are allowed for unfinished UI flows, but cannot be represented as actual agent runs or used for benchmark scores. Keep arithmetic, scenario review, and dependency invalidation functional. This narrow presentation exception supersedes earlier synthetic-only wording for public-report inputs.

## Outcome

Deliver a runnable application that imports synthetic financial records and supporting documents, establishes an as-reported accounting baseline, coordinates specialist investigations, independently reviews findings, requests missing evidence, applies approved corrections to a separate simulation, and exports a source-linked report and action plan.

The distinctive features must actually work:

- Five reasoning roles: lead investigator, transaction detective, payroll/budget analyst, restricted-funds specialist, and independent auditor.
- A typed temporal context graph used for source tracing, retrieval, reviewed precedent applicability, and downstream invalidation.
- Month-two behavior changes through reviewed memory, with an honest with/without-memory evaluation.
- Exact arithmetic and deterministic accounting controls outside the LLM.
- Human review with server-side enforcement before adjustment application or procedural memory activation.

## Execution instructions

Inspect the repository, existing instructions, and available runtimes. Create the application in a dedicated project directory; preserve unrelated files. Maintain a short implementation checklist and proceed milestone by milestone. Start with the smallest end-to-end financial investigation before expanding the UI or dataset.

Use the proposed stack if appropriate, or document a justified equivalent. Verify official documentation for chosen framework/model APIs and pin working dependencies. Do not invent an SDK or rely on a product name in the hackathon brief. Keep the model provider behind a small adapter.

Implement a real backend, financial data store, calculation engine, graph projection, orchestration loop, review queue, and frontend. Do not substitute staged agent messages, random risk scores, or hard-coded issue outputs for real investigations. Deterministic financial validation is encouraged; hard-coded planted-case conclusions are prohibited.

Represent money with exact decimals or integer minor units. Maintain stable IDs and source page/row/cell locators. Preserve original documents and ledger baseline. Use immutable journal proposals, versioned human approval, idempotent scenario application, and report snapshots.

Build reviewed-memory retrieval with scope/date/source checks and an explicit stale-precedent case. Agent agreement and graph connectivity are not proof. Every final factual claim needs valid evidence; every authoritative amount needs a deterministic calculation reference. Preserve counterevidence and unresolved questions.

Implement the synthetic generator and evaluator. Keep private truth outside runtime agent access. Clearly distinguish development fixtures from a genuinely held-out evaluation. The paired memory experiment must use identical month-two documents, opening books, model settings, prompts except memory access, tool limits, and human response policy.

No real payments, payroll changes, ERP postings, bank modifications, grant submissions, or external messages. Use synthetic institution/person data only. The internal auditor agent does not issue an audit opinion. Label simplified statements as management reports under the demo accounting profile.

## Build order

1. Data contracts, opening balances, minimal fixture, exact calculations, import idempotency.
2. Baseline trial balance and management statements; approved correction scenario.
3. Evidence graph, source viewer, one lead/specialist/auditor investigation.
4. Full specialist coverage, review queue, downstream schedules and report generation.
5. Reviewed memory, month-two run, changed-policy invalidation.
6. Hidden-issue evaluation, paired ablation, exports, demo polish, and documentation.

Use the milestone gates in IMPLEMENTATION_PLAN.md. If time is limited, cut optional OCR, complex statutory reporting, advanced facilities accounting, and visual effects before compromising provenance, math, review, or evaluation.

## Required interface

Show an overview with source coverage and period; an investigation timeline driven by real events; findings with evidence and counterevidence; a focused context graph; original source viewer; human review drawer with exact before/after effects; and report/evaluation views. Show incomplete, failed, waiting, and stale states honestly.

## Required final deliverables

- Application source and pinned dependencies.
- `.env.example` with placeholders and clear model configuration.
- Reproducible install, seed, run, test, reset, and export commands.
- Synthetic runtime-safe fixtures plus separately isolated evaluator assets.
- Tests for the accounting, graph, approval, privacy boundary, and memory invariants.
- One saved successful run and exported management report/evidence bundle.
- Measured evaluation results with counts, sample sizes, configurations, and limitations.
- README documenting implemented features, remaining gaps, replay mode, and demo steps.

If model credentials are missing, implement and test the deterministic system and a clearly labeled fixture/replay adapter, then identify the exact configuration needed for a real agent run. Do not claim replay is live or fabricate successful model results.

Do not stop at an architecture summary or static mockup. Implement, run the appropriate checks, resolve failures, and report what actually works. Ask only for genuinely blocking credentials or decisions; choose documented defaults for reversible engineering choices.

---

## Optional continuation prompt

Continue from the existing implementation. Read the checklist and current tests, identify the first unmet acceptance criterion in `spec.md`, and finish the next runnable milestone. Preserve working behavior, use actual saved evaluation results, and do not replace unresolved features with mocked success.
