# Interactive showcase: MIT audit explorer + financial detective sandbox

## Concept

Open the product, explore its capabilities, and let the audience change a scenario. Start with MIT's actual public audit results, then demonstrate transaction-level investigation in a clearly labeled synthetic university sandbox. Prefer a hybrid demo: preloaded documents and cached completed agent runs, with working calculations, evidence navigation, review actions, and scenario changes.

Opening line: **“Let's explore MIT's published audit results, then watch SchoolTrace investigate a financial issue we deliberately introduce into a university sandbox.”**

This replaces the Maplebridge-only presentation sequence. It adds a read-only report explorer; it does not convert the district management ledger into a statutory university accounting system. The synthetic two-month evaluation remains the quantitative benchmark.

## Verified MIT source card

Primary source: [MIT FY2025 Uniform Guidance Audit Report](https://vpf.mit.edu/sites/default/files/downloads/AuditReport/2025_mit_uniform_guidance_report.pdf), year ended June 30, 2025. MIT's [VPF publications page](https://vpf.mit.edu/about-vpf/publications) identifies PwC as the independent auditor.

Printed page 234 (PDF page 236) reports unmodified financial-statement and major-program compliance opinions; no identified material weaknesses or reported significant deficiencies; and no reportable financial-statement or federal-award findings. The major program is the Research & Development Cluster. Printed page 235 reports no prior findings requiring an update.

Comparison: [FY2024 report](https://vpf.mit.edu/sites/default/files/downloads/AuditReport/2024-MIT-Uniform-Guidance-Report.pdf), printed pages 244–245 (PDF pages 246–247), likewise reports no matters in the financial-statement/federal-award findings sections and no prior findings requiring an update.

These are published outcomes, not proof that every internal transaction was error-free. Do not invent an MIT scandal or suggest SchoolTrace found issues PwC missed. Verification date: September 19, 2026.

## 1. Interface: an Office of the CFO run by AI agents

The full layout is in spec §11, and the prototype is `docs/design/prototype.html` (clean fintech style, teal accent). A **workspace switcher** toggles `MIT FY2025 · Public` (read-only) and `Sandbox University · Synthetic`. The sidebar has 8 tabs:

- **Office of the CFO:** Command center (CFO Agent briefing, live agent strip, workflow progress), Agent board (Kanban; click a Working card for steps, progress, ETA, and to-dos), Workflows (close, payroll, AP & payments, grant compliance, audit prep, with ✋ human gates).
- **Work product:** Findings (with the evidence trail), Approvals, Reports.
- **Agent brain:** Reasoning log (click an entry to see when/how/why/alternatives), Learning (playbooks, replay gate, memory on vs off).

In the MIT workspace, Workflows, Approvals, and Learning are disabled.

Use persistent badges: `Public report`, `Synthetic scenario`, `Live run`, `Recorded run`, or `Scripted preview`, as applicable. Expandable run details explain what was cached. The agents must be visibly at work, through agent badges, “N agents working,” and per-agent “doing X…” status. Show concrete actions such as “opened award clause” and “recomputed allocation,” not generic thinking animations.

## 2. Capability: inspect MIT's actual audit results

Select **MIT FY2025 · Public** in the workspace switcher. Documents and page indexes are already prepared, and the Command center shows the CFO Agent's briefing on the published results.

Prompt chip in the command bar: “What did the external auditors report?”

The CFO Agent delegates opinion extraction, the Grants & Compliance agent locates the major-program result, and the Internal Auditor agent checks the original pages. Display the source card above, with each result opening its source region. Click **Compare FY2024 / FY2025** to show year-specific results and citations. Keep report date separate from audited period.

“Show me the findings” must return the published outcome rather than manufacture an anomaly. Accurate restraint is part of the capability showcase.

## 3. Capability: reconcile a real financial movement

Click **Trace a financial movement**. Use FY2025 Note D, Table 11, printed page 23 (PDF page 25). Its pledge-receivable rollforward is in USD thousands:

| Component | Signed value |
| --- | ---: |
| Beginning balance | 626,904 |
| New pledges | 76,081 |
| Payments received | -204,993 |
| Discount change | 53,257 |
| Allowance change | 80,480 |
| Ending balance | 631,729 |

Exact calculation: `626904 + 76081 - 204993 + 53257 + 80480 = 631729`; residual zero; change 4,825 in the same units. [Source: FY2025 Note D](https://vpf.mit.edu/sites/default/files/downloads/AuditReport/2025_mit_uniform_guidance_report.pdf#page=25).

The AP & Payments agent retrieves the table, the Payroll & Budget agent calls the deterministic calculation, the Internal Auditor checks signs, units, and ending balance, and the CFO Agent explains the bridge. This appears in the MIT Findings tab. Do not invent donor-level causes that the report does not disclose.

Click any bridge component to open its source row and calculation lineage. Click **What evidence is missing?** to list underlying pledge agreements, receipt applications, and valuation workpapers needed for transaction-level investigation. This schedule is not MIT's general ledger.

Optional interaction: **Omit a component in a sandbox copy**. Recompute the residual and restore the component. The discrepancy belongs to the deliberately modified copy, not the published report.

## 4. Capability: inject an issue and investigate

Switch visibly to **Sandbox University · Synthetic**, where all transactions are fictional. Invented records must not use MIT employee, donor, vendor, or award identifiers.

Click **Inject grant-allocation issue**. Load one fictional $10,000 payroll cost entirely charged to a fictional award, its contract, incomplete service evidence, a legitimate duplicate-looking invoice pair, and a small balanced management ledger. Open the **Agent board** and watch the cards move:

1. The CFO Agent assigns the allocation and invoice questions (cards appear in Queued, then Working).
2. The Payroll & Budget agent reconciles payroll and identifies the unsupported allocation assumption. Open its Working card to show steps, progress, ETA, and to-dos.
3. The Grants & Compliance agent reads the fictional award and requests current service evidence (card moves to **Needs you**).
4. The AP & Payments agent clears the invoices using separate delivery records.
5. The Internal Auditor refuses to confirm the allocation amount before the missing record arrives.

From the Needs you card, click **Add service evidence**. The prepared synthetic document supports 60% award / 40% general operations. The engine computes a $4,000 reclassification. Offer an alternative 80/20 evidence fixture: the same calculation path must yield $2,000.

A new or contradictory document starts a genuine bounded task or shows an unsupported-input state. It must not trigger a canned successful answer.

## 5. Capability: approve once, update every affected output

Open **Approvals** to see source evidence, the proposed journal, and before/after effects. Human approval applies only to the synthetic scenario. The same queue shows the simulated payment batch the AP & Payments agent prepared, with one invoice held because the vendor changed bank details. Releasing it is simulated.

- General program expense increases by the reclassified amount.
- Award program expense decreases by the same amount.
- Institution-wide payroll expense and cash stay unchanged.
- Budget comparison, award schedule, finding amount, and report update together.
- Graph dependencies mark old claims stale and produce a new consistent snapshot.

Include a remediation action register. Do not automatically invent a receivable reversal or claim cash recovered. Additional entries require separate supporting evidence and approval. Show **Reports** before/after: award spend and remaining award capacity change, and cash does not.

Then open the **Reasoning log** and expand the 60/40 decision. It shows WHEN (run, step, trigger: “you attached SVC-REC-SEP”), HOW (`read_source_span` → `calculate(alloc_split)` → invariant checks), WHY, and WHY THIS OVER ALTERNATIVES (budget sheet's 100% rejected; 50/50 rejected as having no basis). Every field comes from the saved decision record.

## 6. Capability: remember, then recognize when memory is wrong

The CFO Agent proposes playbook PB-07 from the repeated pattern. The **Learning** tab shows it passing the replay gate (0 new false positives on prior months), and the human activates it in Approvals. Show source, contract scope, dates, exclusions, and reviewer. Then click **Next synthetic month**.

Compare two cases:

- Same contract and validated current conditions: PB-05 is retrieved and applied, and the agent skips a repeated clarification.
- Amended contract: PB-03 (60/40 under contract A) is rejected as stale and retired, and the agent inspects current service evidence.

Expose `current charge -> contract -> reviewed precedent -> source -> validity check` in the evidence trail. Highlight the action the playbook changed in the Reasoning log (memory checks ✓/✗). A blocked playbook (PB-06, which failed replay) shows that the gate works.

These months belong to the synthetic institution. Comparing MIT's public annual reports demonstrates document context, not learning from MIT's private monthly books.

## 7. Hybrid execution and permitted shortcuts

| Mode | What runs | Display |
| --- | --- | --- |
| Hybrid — recommended | Preparsed sources and recorded agent results; current calculation, graph navigation, approval, and invalidation code | Recorded-run badge for saved results; live-calculation badge for current computation |
| Live | Fresh model calls using the same tools and sources | Actual progress, bounded costs, honest failures |
| Scripted preview | Authored fixture events before real agents exist | Scripted-preview badge; intended behavior, not measured agent performance |

Precompute extraction, embeddings, source locations, graph layout, and completed model runs. Hard-code navigation, prompt chips, fixture inputs, and presentation transitions. These speed the showcase without requiring repeated model calls.

Do not hard-code authoritative arithmetic, benchmark results, or acceptance of arbitrary evidence. A recorded run must originate from an actual saved run. Authored events remain scripted previews. A scripted-only prototype does not establish the track's agentic requirements.

Replay manifest: execution mode, input hashes, model/prompt/tool versions, snapshot, original start/end time, ordered events, evidence IDs, and calculated outputs. Changed evidence invalidates its cached result. Select a supported recorded branch using the complete input hash or rerun the affected task. Apply human decisions against the current scenario version.

Target immediate navigation and subsecond small calculations locally, with a four-to-six-minute tour. Measure these targets; sped-up replay time is not original model latency.

## 8. Build checklist

- Official source manifest with report years, URLs, hashes, page locators, and verified facts.
- Public-report records isolated from synthetic transactions and private benchmark labels.
- Pledge-rollforward calculation with exact units and signs.
- Two allocation-evidence fixtures plus a changed-contract memory fixture.
- Event player with pause, step, source-open, and mode display, which drives the Agent board columns and Working-card progress.
- Saved decision records for every Reasoning log entry shown, including the 60/40 and stale-PB-03 decisions.
- Playbook fixtures: PB-05 active, PB-03 retired (contract B), PB-06 blocked (replay failed), PB-07 needs approval.
- Simulated payment batch with one vendor-bank-change hold.
- Working scenario approval/application, dependency invalidation, and report export.
- Optional “run this task live” control when a provider is configured.

Public-report mode retains published classifications and is read-only. Synthetic mode uses the existing simplified management engine. No MIT affiliation claim or automated alteration of MIT's published statements is involved.

## 9. Presenter route and evaluation

**Command center (MIT) -> Findings (MIT: no findings + pledge rollforward ties) -> switch to Sandbox -> Agent board (watch agents; open a Working card) -> Needs you: add service evidence -> Approvals: approve $4,000 reclass (cash unchanged) -> Reports before/after -> Reasoning log (expand the 60/40 decision) -> next month -> Learning (PB-05 applied, PB-03 retired as stale, PB-07 via replay gate, memory on vs off) -> export.**

Spend most of the time clicking through the product; adapt the route to audience interest. Unsupported live inputs should show their limitation or start a genuine bounded investigation.

Close with the existing synthetic month-two ablation: identical evidence/books/model/budgets, different reviewed-memory access. Show measured counts and sample sizes only. MIT source fidelity is a separate check, not blind issue discovery or an independent MIT audit.

## 10. Acceptance checks

- MIT facts open the correct original source pages.
- Public, synthetic, live, recorded, and scripted states are distinguishable.
- Pledge rollforward ties exactly and preserves thousands-of-dollars units.
- Alternative evidence changes the proposed allocation amount.
- Legitimate invoices are cleared; missing evidence remains unresolved until supplied.
- Approved reclassification updates dependencies without changing cash.
- Amended contracts invalidate memory and affected cached results.
- Each Reasoning log entry expands to when/how/why/alternatives drawn from a saved decision record.
- Agent board state reflects actual task state (or a labeled recorded run), not a looping animation.
- No playbook appears active without a passed replay gate and a human approval.
- No MIT finding, live-run claim, or benchmark score is fabricated. Learning-tab numbers are measured or labeled as examples.
