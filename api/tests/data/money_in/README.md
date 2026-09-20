# Fictional money-in pack (fees, collections, deposits, sponsorships)

September at a fictional school: charges raised against anonymised student refs, cash and cheques taken at
the office and at events, the bank deposits that should follow, and three local-business pledges. Every
identifier here is invented — `STU-00x`, `SPONSOR-0x`, `COL-0xx`, `DEP-REF-000x`. No real school, student,
family, staff member or business is represented, and nothing in this directory is a real payment.

Upload the four files into a workspace whose period is `2026-09-01` to `2026-09-30`, on the synthetic USD
management profile. The dates are chosen for that window: intake requires every `collection_date` to fall
inside the period, and every `deposit_date` to fall inside the period or within the 7-day banking window it
allows after the period end (`DEPOSIT_GRACE_DAYS` in `api/app/ingestion.py`). `charge_date`, `pledge_date`
and `due_date` are not bounded by the period — `SPN-003` falls due in October on purpose. Every amount must
be positive, so a refund or a reversal cannot be expressed in this pack at all; no check in
`api/app/accounting/collections.py` models one either.

## Intended wiring

Nothing imports these files. That is deliberate. They are meant to be uploaded by a person through the real
intake path — `POST /api/workspaces/{ws}/imports` with roles `fees`, `collections`, `deposits`,
`sponsorships`, then commit, then `POST /api/workspaces/{ws}/review/scans` — so that every number a judge
reads was parsed from bytes a human handed the server. They are not seeded into a database behind the user's
back, and a row inserted by a fixture would still be mock data however it arrived.

## Planted cases

Amounts are what the checks in `api/app/accounting/collections.py` compute from these records. They come in
the two kinds that module keeps apart: a difference between two supplied populations (the deposit shortfall
against a reference, the excess deposited over it, the uncollected remainder of a charge, the unreceived
remainder of a pledge) and a gross total of one population (receipts carrying a reference no deposit
answers). None of them establishes theft, loss or misappropriation, and they must never be added together or
described as recovered money.

| Planted case | Records | Expected `amount_cents` | Check id | Status |
| --- | --- | --- | --- | --- |
| Athletics fundraiser receipted with no matching deposit: `DEP-REF-0009` appears on two receipts and on no supplied deposit. The amount is the gross total of those receipts | COL-008, COL-009 | `240000` (USD 2,400.00) | `rc-undeposited-2b95aeb57ec7` | attention |
| Deposit short of the cash collected against `DEP-REF-0004`: 1,000.00 recorded as received, 850.00 banked. The amount is that shortfall | COL-006, COL-007, DEP-004 | `15000` (USD 150.00) | `rc-deposit-shortfall-d432ab8cb466` | attention |
| Sponsor pledge due 2026-09-11 covered by no receipt. The amount is the unreceived remainder | SPN-002 | `175000` (USD 1,750.00) | `rc-pledge-overdue` | attention |
| Two fee charges referenced by no receipt — expected in September, not an exception. The amount is the uncollected remainder across both | FEE-007, FEE-008 | `17000` (USD 170.00) | `rc-fees-outstanding` | gap |

The hashed suffix is the first 12 hex characters of the `sha256` of the **normalised** deposit reference —
whitespace collapsed, NFKC applied, lowercased — so `sha256("dep-ref-0009")` gives `2b95aeb57ec7` and
`sha256("dep-ref-0004")` gives `d432ab8cb466`. An id is therefore stable while its reference is, and changes
if the reference does, not if the receipts under it change.

The shortfall id moved this round. That case used to be emitted as `rc-undeposited-<digest>`, the same id as
the no-deposit-at-all case, so two different checks over one reference could not be told apart; it now has
its own `rc-deposit-shortfall-<digest>` prefix over the same digest. A follow-up saved against the old id
refers to nothing.

## What should stay quiet

Everything else ties, so the pack also shows the checks not firing. Reference groups `DEP-REF-0001`, `-0002`,
`-0003`, `-0005` and `-0006` each match supplied deposits for exactly the amount collected against them — not
less, so `rc-deposit-shortfall-*` stays silent on them, and not more, so `rc-deposit-surplus-*` stays silent
too. `DEP-002` resolves on its own `deposit_reference` rather than its `bank_reference`, which exercises the
other half of the linking rule. Every receipt carries a deposit reference, so `rc-undeposited-unreferenced`
stays silent; every `fee_record_id` names a supplied charge, so `rc-collection-without-charge` stays silent;
every deposit resolves to a reference some receipt carries and none is missing both references, so
`rc-deposit-unmatched-*` and `rc-deposit-unreferenced` stay silent; no receipt is dated more than five days
before the earliest supplied deposit under its reference dated on or after it, so `rc-deposit-timing-*` stays
silent. `COL-005` names `SPN-001` in `collection_reference` and names no fee charge, so it answers that
pledge and covers it in full; `SPN-003` falls due after the period end. Neither joins the overdue pledge
finding, and the workspace period is supplied, so `rc-pledge-ageing-not-run` stays silent.

No receipt here names both a fee charge and a pledge, so the rule that a collection answers one obligation
only — the charge where it names one, the pledge otherwise — is not exercised by this pack.

`rc-deposit-reconciliation`, the money-in pass finding, does not appear while this pack is loaded: it is
emitted only when no group is unreconciled, and this pack plants two that are.

## How the table was produced

Every id, amount and evidence line above was read back out of the running application, not computed by hand.
The four files were uploaded through the real intake path into a temporary data directory — a workspace
created over `2026-09-01` to `2026-09-30`, `POST /api/workspaces/{ws}/imports` with the four roles, the batch
committed, then `POST /api/workspaces/{ws}/review/scans` — driven in process with FastAPI's `TestClient`
against `api/app/main.py`. The scan reported 29 parsed records and returned exactly the four `rc` findings
listed, citing collections.csv lines 7-10, deposits.csv line 5, fees.csv lines 8-9 and sponsorships.csv
line 3. That is a scripted run of the same endpoints a person uses, not a record of a human upload, and it is
engine reproduction rather than an accuracy measurement.

`api/tests/test_collections.py` exercises the same rules on its own inline fixtures rather than on these
files, so a change to the checks shows up there first and this table must be recomputed when it does. The
check ids move whenever the reference normalisation or a check's own prefix moves, as the shortfall id did
this round.
