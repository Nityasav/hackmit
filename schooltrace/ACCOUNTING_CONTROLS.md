# Accounting policy, controls, and worked cases

These are implementation requirements for a fictional internal-management prototype. They are not a universal accounting policy. External requirements must be activated through a reviewed institution/award policy pack. Reference links and limitations are in [SOURCES.md](SOURCES.md).

## 1. Basis and jurisdiction boundaries

The MVP's accrual management ledger recognizes the supplied economic events using the explicit demo policies. Each statement displays `DEMO_US_DISTRICT_MANAGEMENT_ACCRUAL_V1 — internal management use; incomplete for statutory reporting`.

US governmental fund statements generally use a current-financial-resources measurement focus and modified accrual; government-wide statements use an economic-resources focus and accrual. These cannot be combined by merely relabeling an accrual balance sheet. A later government reporting adapter needs basis-conversion entries, reconciliations, appropriate fund classifications, deferred inflow/outflow handling, and current authoritative guidance. [California Department of Education FAQ](https://www.cde.ca.gov/fg/ac/as/faqs.asp).

Public and private universities and Canadian institutions require separate accounting-policy discovery. Do not assume GASB, FASB, or Canadian public-sector requirements apply solely because an organization provides education.

A policy pack stores issuer, authority type, applicable entity/award, source locator, effective dates, version, approved interpretation, exceptions, and reviewer. Conflicting authorities are escalated; an institutional precedent cannot override a grant agreement or applicable rule.

## 2. Ledger invariants

| ID | Rule | On failure |
| --- | --- | --- |
| L01 | Each journal has total debits = total credits in minor units | Reject staging/posting |
| L02 | A line has nonnegative debit/credit and exactly one nonzero side | Reject invalid line |
| L03 | Account exists and is effective on accounting date | Request mapping |
| L04 | Institution, currency, scenario, and period are valid | Quarantine |
| L05 | Opening + activity = closing by account/dimension | Block statement publication |
| L06 | Simplified management assets = liabilities + net assets | Block publication |
| L07 | Subledger balances tie to AP/AR/payroll control accounts or identify reconciling items | Publish only with explicit unresolved exception |
| L08 | Approved adjustments use a current proposal version and distinct human approver | Reject stale or unauthorized application |
| L09 | Reversal and replacement are linked; original entry is immutable | Reject destructive edit |
| L10 | Cash flow totals reconcile to cash account movement | Mark forecast/actual reconciliation invalid |
| L11 | Allocation components total the original amount exactly | Apply documented cent-residual rule or reject |
| L12 | Applying the same approved proposal twice has no second effect | Return existing application |

For L06, the simplified chart omits deferred inflows/outflows; that is a scope constraint, not a general governmental accounting equation. If imported balances need unsupported account classes, flag the report incomplete.

Use documented largest-remainder allocation for cents, stable tie-breaking by allocation ID, and unit tests for negative/reversal cases. Accounting dates, service dates, invoice dates, settlement dates, and ingestion dates are distinct.

## 3. Import and reconstruction

Prefer an existing GL with source IDs. Import bank statements, invoices, and payroll as corroborating records linked to GL events. They must not all independently become expenses.

When reconstructing books from documents, require verified opening balances, account mapping, event identity, and reviewed journal proposals. An unmatched amount remains an unresolved reconciliation item. Do not plug differences to miscellaneous expense or an invented suspense balance just to make statements tie. A real suspense entry requires explicit policy, evidence, and approval, with aging and resolution tracking.

Baseline records may contain balanced but wrong entries. A trial balance proves arithmetic balance, not validity, completeness, or correct classification.

## 4. Accounts payable and procurement

Three-way match compares invoice lines with authorized PO lines and goods receipts/service acceptance. Support partial receipts, split invoices, freight/tax treatment, credit memos, and documented tolerances. A missing PO may reflect an authorized non-PO purchase; check policy before alleging a violation.

Duplicate signals: normalized vendor ID, invoice number, gross/net amount, currency, service period, invoice image hash, and bank payment reference. Similar invoice numbers or equal recurring amounts are candidates only. Two invoices for different delivered batches may both be valid.

AP rollforward = opening AP + supplier invoices/accruals - credit notes - payments applied +/- reclassifications. Payment applications may be one-to-many or many-to-one, with explicit residuals.

Encumbrance = a budget commitment, not automatically a liability. Do not count an open PO as both an expense and AP. When recognized activity replaces a commitment, release the corresponding encumbrance so budget usage is not counted twice. [CDE distinction](https://www.cde.ca.gov/fg/ac/as/faqs.asp).

Control checks: preparer/approver separation, delegated authority effective date, approval threshold, purchase splitting as a hypothesis, vendor changes, and approval after payment. Thresholds come from supplied policy; none are universal constants.

## 5. Receivables, revenue, and cash

AR aging uses contractual due date and outstanding amount after applications and credits. Aging alone does not establish uncollectibility. A grant award ceiling is not automatically revenue, a receivable, or cash. Recognition depends on the supplied award terms and accounting profile.

For the demo reimbursement award, recognize a receivable/revenue only for eligible incurred costs meeting the fictional agreement's conditions. Cash received in advance follows a separately defined liability policy until conditions are met. These policies are explicit fixture assumptions.

Bank reconciliation distinguishes bank errors, book errors, deposits in transit, outstanding checks, fees, and unidentified items. A timing difference does not automatically require a correcting journal. Show statement balance and book balance bridges with signs and source IDs.

Do not equate restricted-award remaining capacity with spendable cash. Cash may be pooled while allocation restrictions remain. The cash forecast must not fund general payroll with restricted resources without supporting authority.

## 6. Payroll and benefits

Reconcile gross pay minus employee deductions to net pay; reconcile employer payroll taxes/benefits separately. Payroll expense includes gross compensation plus employer costs under the demo policy. Net salary payments do not equal total payroll expense.

Check service dates, pay dates, employee master changes, authorized rate, FTE, substitute hours, overtime evidence, allocation percentages, benefit allocations, and remittance liabilities. Flag terminated-employee payments for review; final leave payouts or retroactive adjustments may explain them.

For shared staff charged to grants, budgeted percentages alone are not automatically evidence of actual work. Require the evidence specified by the award/policy pack. Federal cost-principle concepts include allowability, allocability, and compensation support; verify applicable versions before using them as criteria. [Federal Register guidance](https://www.federalregister.gov/citation/89-FR-30109).

Variance bridge decomposes prior/current payroll differences into headcount/FTE, rates, hours, employer benefits, one-time adjustments, and residual. Label a residual rather than forcing a causal story. Enrollment decline is contextual evidence, not proof that payroll should decline proportionally.

Pension contributions in payroll can be reconciled. Net pension liability and other postemployment benefit valuation require specialist schedules and are outside the MVP; do not infer those balances from current contributions.

## 7. Restricted-fund checklist

For every tested charge record the criterion, evidence, calculation, result (`supported`, `exception`, `insufficient_evidence`, `not_applicable`), reviewer, and applicable dates.

| Check | Test | Important exception |
| --- | --- | --- |
| Award identity | Charge belongs to the exact award and amendment | Same funder may have multiple awards |
| Purpose | Cost benefits the permitted activity/population | Department name alone is insufficient |
| Period | Service/incurrence date fits the applicable budget/service window | Invoice/payment date may differ; amendments may apply |
| Allowability | Cost category and conditions satisfy supplied terms | An approved budget line does not waive all other conditions |
| Allocability | Charged share follows documented benefit/allocation basis | Moving a cost to consume spare budget is not justification |
| Documentation | Required invoice, service evidence, approvals, and payroll records exist | Missing records mean unresolved support, not automatically theft |
| Duplicate funding | Same cost is not claimed more than once across funding sources | Valid split funding must total no more than supported cost |
| Budget ceiling | Charges respect approved category/award limits | Allowable rebudgeting must be evidenced |
| Credits | Rebates/refunds are attributed to related charges | Original gross spend may overstate supported cost |
| Indirect cost | Approved rate and eligible base match agreement/version | Never assume a universal rate or apply it to excluded base items |
| Match/cost share | Contributions meet specific agreement conditions | Do not reuse the same contribution without authorization |
| Reporting | Claimed expenditure ties to source ledger/scenario | Cash reimbursement is not the same as expenditure |

Program-specific rules such as maintenance of effort and supplement-not-supplant remain unsupported unless a reviewed rule pack and required comparison data are supplied. Output `not_evaluated` rather than an invented pass.

## 8. Worked adjustments — fictional amounts

### A. Payroll allocation error

A $10,000 salary was charged entirely to the student-support award. Reviewed service evidence supports 60% to that award and 40% to general operations.

Proposed management reclassification:

| Account | Dimension | Debit | Credit |
| --- | --- | ---: | ---: |
| Salary expense | General operations | 4,000.00 | 0.00 |
| Salary expense | Student-support award | 0.00 | 4,000.00 |

Total payroll expense, AP, and cash do not change. General allocation increases $4,000; award allocation decreases $4,000. If a reimbursement receivable was recognized for the unsupported portion, a separate evidenced proposal debits grant revenue and credits grant receivable for $4,000. That second entry affects revenue and AR; it is not implied by every allocation correction.

### B. Duplicate invoice recorded, only one payment

One $2,400 invoice was posted twice, with the duplicate still unpaid. Reverse the duplicate: debit AP $2,400; credit supplies expense $2,400. Cash is unchanged. This is removal of an overstated payable and expense, not $2,400 of recovered cash. If two payments actually occurred, investigate a recoverable balance separately and support recognition.

### C. Prepaid service

Under the fixture's monthly allocation policy, $12,000 paid October 1 covers October through September. The original entry expensed all $12,000. At October close, $1,000 belongs to October; propose debit prepaid expense $11,000 and credit service expense $11,000. No cash change. Do not apply this example to governmental fund reporting without a proper basis adapter.

### D. Unbilled maintenance

A signed acceptance record supports $3,000 of work completed September 28, invoiced in October. If absent from the September accrual ledger, propose debit maintenance expense and credit accrued liabilities $3,000. October invoice handling must reverse/reclassify the accrual without recognizing expense twice.

### E. Banking fee

A $9,980 deposit settles a supported $10,000 receivable with a documented $20 processing fee. Correct settlement: debit cash $9,980, debit fee expense $20, credit AR $10,000. No invented $20 customer delinquency remains.

## 9. Facilities and advanced accounting boundaries

Distinguish repair/maintenance from capitalization using approved policy and evidence of the asset's nature; amount alone does not decide. Track service/in-service dates, useful life, depreciation, and construction-in-progress only if the selected profile supports them. Retainage, debt covenants, leases, impairment, asset retirement obligations, and bond-restricted proceeds are future modules with explicit policy requirements.

## 10. Audit vocabulary and reporting discipline

- **Occurrence/existence:** did the recorded event or asset exist?
- **Completeness:** are required events or obligations missing?
- **Accuracy/valuation:** are amounts and measurement supported?
- **Cutoff:** is the event assigned to the correct period?
- **Classification/presentation:** is the account, fund, or report category appropriate?
- **Rights and obligations:** does the institution own the asset or owe the liability?
- **Control deficiency:** potential weakness requiring review; formal severity classification is reserved.
- **Questioned cost exposure:** use a clearly labeled internal estimate unless a qualified process establishes a formal questioned cost.
- **PBC schedule:** a prepared-by-client supporting workpaper, not independent audit evidence by itself.
- **Materiality:** reviewer-configured prioritization context, not a license to ignore qualitatively serious small items.
- **SEFA:** schedule of expenditures of federal awards; the MVP's award schedule is not automatically a compliant SEFA.

Report confirmed facts, unresolved support gaps, and suspected anomalies separately. Preserve dissent and counterevidence. Never conceal an unresolved issue to make the final report look clean.
