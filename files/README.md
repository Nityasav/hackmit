# Test data for the agents

Fictional records that satisfy every requirement the agent registry declares, so
all 22 agents unblock and can be run. Nothing here describes a real school,
company, person or transaction.

## How to use it

1. Books → **New institution**. `entity_type` must be `company`, `subsidiary` or
   `group`. Period **2026-09-01 to 2026-09-30**, currency **USD** — the dates in
   these files sit inside that window and will be rejected outside it.
2. Upload all 15 CSVs plus `approval-policy.md`, tagging each with the role that
   matches its filename (`vendor_invoices.csv` → Vendor invoices, and so on).
3. **Preview import**, then **Commit**.
4. Set the four settings, which are requirements but not files:

   | Setting | Value used here |
   | --- | --- |
   | Home tax jurisdiction | `US-MA` |
   | Fiscal year end | `06-30` |
   | Materiality threshold | `500.00` |
   | Payment approval limit | `5000.00` |

   Without these, four requirements stay unmet and agents stay blocked.

## What the agents should find

The data is internally consistent — the ledger balances, and entries reconcile to
payments and bank lines — so everything below is a genuine inconsistency rather
than noise.

| Planted | Where |
| --- | --- |
| Same invoice billed twice, $1,200 each | `vendor_invoices.csv` VI-1, VI-2 (both INV-2291) |
| Invoice with no purchase order and no goods receipt | INV-2310, $8,900 |
| Payment above the $5,000 approval limit, unapproved | `payments.csv` PAY-9004 |
| Customer paid $50 short | `remittances.csv` REM-2 against REC-1002 |
| Bank withdrawal matching no payment | `bank_transactions.csv` BNK-006, $325 |
| Invoice overdue at period end | `customer_invoices.csv` CI-3, $2,400 |
| Spend far above budget | account 5200: $8,900 against a $2,000 budget |

Verified: Accounts Payable (A1) run against this data returns `exception` with
five citations covering the duplicate, the missing PO, the missing receipt, the
missing approval and the over-limit payment.

## Why these are CSVs and not PDFs

Eleven of the requirements are `kind: csv` and are validated column by column on
import. A PDF goes through document extraction and cannot satisfy them. Only
`policy`, `contract`, `invoice`, `service` and `budget` accept a document, which
is why the policy is the one non-CSV here.
