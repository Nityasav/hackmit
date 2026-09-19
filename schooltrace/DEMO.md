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

## 1. Interface: a capability tour

Keep three tabs visible:

- **MIT public reports:** read-only audit results, financial disclosures, and source comparison.
- **University sandbox:** fictional transactions, grant terms, corrections, and reviewed memory.
- **Run evidence:** tool events, execution mode, manifests, and measured evaluation.

Use persistent badges: `Public report`, `Synthetic scenario`, `Live run`, `Recorded run`, or `Scripted preview`, as applicable. Expandable run details explain what was cached. The main view has capability buttons, current findings/calculations, and a side pane for sources, graph paths, or review.

Show concrete actions such as “opened award clause” and “recomputed allocation,” not generic thinking animations.

## 2. Capability: inspect MIT's actual audit results

Click **Load MIT FY2025**. Documents and page indexes are already prepared.

Prompt chip: “What did the external auditors report?”

The lead delegates opinion extraction; the restricted-funds specialist locates the major-program result; the auditor agent checks the original pages. Display the source card above, with each result opening its source region. Click **Compare FY2024 / FY2025** to show year-specific results and citations. Keep report date separate from audited period.

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

The transaction detective retrieves the table; the analyst calls the deterministic calculation; the auditor checks signs, units, and ending balance; the lead explains the bridge. Do not invent donor-level causes that the report does not disclose.

Click any bridge component to open its source row and calculation lineage. Click **What evidence is missing?** to list underlying pledge agreements, receipt applications, and valuation workpapers needed for transaction-level investigation. This schedule is not MIT's general ledger.

Optional interaction: **Omit a component in a sandbox copy**. Recompute the residual and restore the component. The discrepancy belongs to the deliberately modified copy, not the published report.

## 4. Capability: inject an issue and investigate

Switch visibly to **University sandbox — all transactions fictional**. Invented records must not use MIT employee, donor, vendor, or award identifiers.

Click **Inject grant-allocation issue**. Load one fictional $10,000 payroll cost entirely charged to a fictional award, its contract, incomplete service evidence, a legitimate duplicate-looking invoice pair, and a small balanced management ledger.

1. Lead assigns the allocation and invoice questions.
2. Payroll analyst reconciles payroll and identifies the unsupported allocation assumption.
3. Restricted-funds specialist reads the fictional award and requests current service evidence.
4. Transaction detective clears the invoices using separate delivery records.
5. Auditor refuses to confirm the allocation amount before the missing record arrives.

Click **Add service evidence**. The prepared synthetic document supports 60% award / 40% general operations. The engine computes a $4,000 reclassification. Offer an alternative 80/20 evidence fixture: the same calculation path must yield $2,000.

A new or contradictory document starts a genuine bounded task or shows an unsupported-input state. It must not trigger a canned successful answer.

## 5. Capability: approve once, update every affected output

Click **Review correction** to open source evidence, proposed journal, and before/after effects. Human approval applies only to the synthetic scenario.

- General program expense increases by the reclassified amount.
- Award program expense decreases by the same amount.
- Institution-wide payroll expense and cash stay unchanged.
- Budget comparison, award schedule, finding amount, and report update together.
- Graph dependencies mark old claims stale and produce a new consistent snapshot.

Include a remediation action register. Do not automatically invent a receivable reversal or claim cash recovered. Additional entries require separate supporting evidence and approval.

## 6. Capability: remember, then recognize when memory is wrong

Click **Save reviewed precedent**. Show source, contract scope, dates, exclusions, and reviewer. Then click **Next synthetic month**.

Compare two cases:

- Same contract and validated current conditions: retrieve the precedent and avoid repeated clarification.
- Amended contract: reject the old precedent and inspect current service evidence.

Expose `current charge -> contract -> reviewed precedent -> source -> validity check` in the graph, and highlight the action memory changed.

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
- Event player with pause, step, source-open, and mode display.
- Working scenario approval/application, dependency invalidation, and report export.
- Optional “run this task live” control when a provider is configured.

Public-report mode retains published classifications and is read-only. Synthetic mode uses the existing simplified management engine. No MIT affiliation claim or automated alteration of MIT's published statements is involved.

## 9. Presenter route and evaluation

**Load MIT -> inspect actual results -> reconcile published movement -> switch to sandbox -> inject issue -> add evidence -> approve correction -> demonstrate memory -> export findings.**

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
- No MIT finding, live-run claim, or benchmark score is fabricated.
