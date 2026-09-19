# Copy-paste implementation prompt

Give the following prompt to a coding agent with all files in this specification directory available. The requested deliverable is an implemented application; this package itself is the design input.

---

Build **SchoolTrace**, a working hackathon application for the Maximor Office of the CFO track. It is an Office of the CFO for schools, run by AI agents: a multi-agent financial detective and workflow runner for educational institutions, starting with a fictional institution and two monthly accounting periods.

Hackathon reality: about 16 hours and 4 people split into UI, Agent design, Workflows, and Functionality. If you are helping one teammate, work only inside that owner's area in `/WORKPLAN.md` and the directories it owns, and do not change `contracts/` without flagging it. The repo layout is `web/` (Next.js 16, TS, Tailwind v4, bun), `api/` (FastAPI, uv; `app/accounting`, `app/agents`, `app/workflows`), `contracts/` (bundle schema + fixtures), and `docs/design/prototype.html` (the approved UI). Use SQLite for the hackathon, and Claude Sonnet 5 (`claude-sonnet-5`) behind the provider adapter plus a labeled replay adapter.

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

- Five reasoning roles, shown as an Office of the CFO: the CFO Agent (lead investigator), AP & Payments (transaction detective), Payroll & Budget (payroll/budget analyst), Grants & Compliance (restricted-funds specialist), and the Internal Auditor (independent auditor).
- A typed temporal context graph used for source tracing, retrieval, reviewed precedent applicability, and downstream invalidation.
- Month-two behavior changes through reviewed memory: agent-written playbooks that pass a replay gate (0 new false positives on prior months) and a human approval, with an honest with/without-memory evaluation.
- A structured decision record for every agent action (when, how, why, alternatives, memory checks, outcome), which feeds the Reasoning log.
- Exact arithmetic and deterministic accounting controls outside the LLM.
- Human review with server-side enforcement before adjustment application, simulated payment-batch release, or playbook/procedural memory activation.

## Execution instructions

Inspect the repository, existing instructions, and available runtimes. Create the application in a dedicated project directory; preserve unrelated files. Maintain a short implementation checklist and proceed milestone by milestone. Start with the smallest end-to-end financial investigation before expanding the UI or dataset.

Use the proposed stack if appropriate, or document a justified equivalent. Verify official documentation for chosen framework/model APIs and pin working dependencies. Do not invent an SDK or rely on a product name in the hackathon brief. Keep the model provider behind a small adapter.

Implement a real backend, financial data store, calculation engine, graph projection, orchestration loop, review queue, and frontend. Do not substitute staged agent messages, random risk scores, or hard-coded issue outputs for real investigations. Deterministic financial validation is encouraged; hard-coded planted-case conclusions are prohibited.

Represent money with exact decimals or integer minor units. Maintain stable IDs and source page/row/cell locators. Preserve original documents and ledger baseline. Use immutable journal proposals, versioned human approval, idempotent scenario application, and report snapshots.

Build reviewed-memory retrieval with scope/date/source checks and an explicit stale-precedent case. Agent agreement and graph connectivity are not proof. Every final factual claim needs valid evidence; every authoritative amount needs a deterministic calculation reference. Preserve counterevidence and unresolved questions.

Implement the synthetic generator and evaluator. Keep private truth outside runtime agent access. Clearly distinguish development fixtures from a genuinely held-out evaluation. The paired memory experiment must use identical month-two documents, opening books, model settings, prompts except memory access, tool limits, and human response policy.

No real payments, payroll changes, ERP postings, bank modifications, grant submissions, or external messages. Payment batches and payroll reallocations are prepared by agents, released by a human, and simulated. Use synthetic institution/person data only. The internal auditor agent does not issue an audit opinion. Label simplified statements as management reports under the demo accounting profile.

## Build order

1. Data contracts (`contracts/` bundle schema), opening balances, minimal fixture, exact calculations, import idempotency.
2. Baseline trial balance and management statements; approved correction scenario.
3. Evidence path, source viewer, one CFO Agent/specialist/Internal Auditor investigation emitting decision records.
4. Full specialist coverage, Approvals queue (journals, simulated payment batch, playbooks), workflows, and report generation.
5. Playbooks with replay gate, month-two run, stale-playbook retirement.
6. Hidden-issue evaluation, one paired ablation, exports, demo polish, and documentation.

Use the 16-hour checkpoints and cut list in IMPLEMENTATION_PLAN.md §3. If time is limited, cut optional OCR, complex statutory reporting, advanced facilities accounting, and visual effects before compromising provenance, math, review, or evaluation.

## Required interface

Match spec §11 and `docs/design/prototype.html` (clean fintech style, teal accent). Include a workspace switcher (MIT FY2025 · Public ⇄ Sandbox University · Synthetic) and 8 tabs:
- Command center: CFO Agent briefing, live agent strip, workflow progress.
- Agent board: Kanban with a task drawer showing steps, progress, ETA, and to-dos.
- Workflows: close, payroll, AP & payments, grants, audit prep, with human gates.
- Findings, with the evidence trail.
- Approvals.
- Reports: before/after.
- Reasoning log: expandable when/how/why/alternatives.
- Learning: playbooks, replay gate, memory on/off.

The AI's work must be visibly live, and every visible agent status must come from real task state or a labeled recorded run. Show incomplete, failed, waiting, and stale states honestly.

## Required final deliverables

- Application source and pinned dependencies.
- `.env.example` with placeholders and clear model configuration.
- Reproducible install, seed, run, test, reset, and export commands.
- Synthetic runtime-safe fixtures plus separately isolated evaluator assets.
- Tests for the accounting, graph, approval, privacy boundary, memory/playbook replay gate, payment-batch hold, and decision-record invariants.
- One saved successful run and exported management report/evidence bundle.
- Measured evaluation results with counts, sample sizes, configurations, and limitations.
- README documenting implemented features, remaining gaps, replay mode, and demo steps.

If model credentials are missing, implement and test the deterministic system and a clearly labeled fixture/replay adapter, then identify the exact configuration needed for a real agent run. Do not claim replay is live or fabricate successful model results.

Do not stop at an architecture summary or static mockup. Implement, run the appropriate checks, resolve failures, and report what actually works. Ask only for genuinely blocking credentials or decisions; choose documented defaults for reversible engineering choices.

---

## Optional continuation prompt

Continue from the existing implementation. Read the checklist and current tests, identify the first unmet acceptance criterion in `spec.md`, and finish the next runnable milestone. Preserve working behavior, use actual saved evaluation results, and do not replace unresolved features with mocked success.
