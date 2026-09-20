# Director workflow / judge demo implementation

Scope: laptop-first, fictional records, existing `max` branch. No deployment or
claim of readiness for real institutional records. Preserve existing agent APIs.

## Delivery checklist

- [x] Home: plain-language navigation and one-click fictional scan.
- [x] One workspace review feed: deterministic checks plus latest five-agent run,
      snapshot freshness, original evidence, Findings/Reports/Command center.
- [x] Bounded financial checks: invoice duplicate candidates, missing matching support,
      approved expense budget variance, grant windows/ceilings and payroll tie-out.
      Integer cents; gaps are not wrongdoing; no additive overlapping exposure KPI.
- [x] Human follow-up: owner, evidence request, proposed decision, version checks,
      append-only event history. No payment/posting or automatic clean opinion.
- [x] Interactive demo: supplied records → actual checks → source drill-down →
      add withheld support → new snapshot → rerun → compare → export briefing.
- [x] Evaluation: labelled deterministic cases, false-positive controls, evidence
      and freshness regressions; provider smoke separately labelled, not an accuracy score.
- [x] Laptop safeguards: loopback/origin protection, optional authenticated roles
      and workspace access, bounded paid runs, retention/deletion UI, data-use warning.
- [x] Verify backend, build/lint, browser journey; document exact remaining gaps.

## Non-negotiable boundaries

- Offline checks are explicitly rules-based, never represented as live AI agents.
- Live five-agent calls require explicit user action and disclose provider transfer.
- Review acceptance, human approval and financial execution are different states.
- New evidence invalidates prior review/decision applicability, not historical records.
- Ontario/TDSB accounting, privacy/legal compliance, managed encryption/backups,
  enterprise identity and held-out model accuracy require separate validation.

## Implementation map

Keep changes compact: `api/app/reviews.py` owns review/check/follow-up API;
`api/app/security.py` owns laptop access safeguards; a shared review UI powers
Findings, Reports, and the guided scan. Existing intake owns sources/snapshots;
the existing coordinator remains the only live five-agent runtime.

## How to present (roughly three minutes)

1. Home → **Try the guided financial scan**. All inputs are fictional. The imported
   snapshot starts with 14 records and 10 bounded checks, not an invented activity log.
2. Open **Possible duplicate invoice** and its source. The register contains two
   matching records for the same vendor/invoice/amount: a USD 1,200 candidate, not
   proof that a duplicate payment occurred. A different vendor with the same invoice
   number is intentionally present as a negative control and must not join that group.
3. Inspect **Expense budget variance**: USD 10,000 net payroll expense versus a
   supplied USD 9,000 period budget, giving USD 1,000 variance—not recovered cash.
4. Assign Finance operations an evidence request or record a proposal, then let a
   reviewer approve/reject that proposal. No books or payments are changed.
5. **Add withheld evidence & rescan**. A new snapshot has 15 records. The prior
   missing-service exposure becomes **not established** once a memo is present;
   allocation correctness remains an explicit gap. Prior follow-up stays historical.
6. Reports → download Markdown or print the visible briefing. Show sources, method,
   outstanding questions and human follow-up, not a fabricated clean opinion.
7. Optional: `/cfo` → five-agent review. Explain that this sends synthetic records to
   the provider, is billable, may take longer and can return partial/needs-evidence.

## Evaluation checkpoint

- Offline suite: 315 passed, 10 opt-in/artifact tests skipped at this checkpoint.
- Eight labelled invoice cases: three duplicate positives detected; five negative
  controls not flagged. Precision 3/3 and recall 3/3 **on these hand-authored exact-key
  cases only**. This is not a held-out fraud/duplicate-payment accuracy result.
- Four labelled budget cases: exact integer-cent variance and expected disposition
  matched in all four. Additional tests reject ambiguous budget versions and treat
  empty inputs as gaps, not clean results.
- Integration tests exercise original evidence, source/snapshot freshness, proposal
  state/version gates, history, standalone/live projection, exports and deletion.
- Security tests exercise role restrictions, workspace/run ACLs, wrong/expired
  sessions, logout, untrusted origins/hosts, malformed configuration and body limits.
- One fresh paid fictional director-demo run completed: 3 tasks, 20 evidence calls,
  3 CFO calls, 4 accepted claims, final `needs_evidence`. End-to-end execution passed;
  semantic reliability, held-out accuracy, total specialist token cost and memory
  ablation were not measured by that smoke test.
- Browser verified: home → fresh fictional scan → original invoice lines → saved
  follow-up → withheld evidence/new snapshot → rescan → report → actual server-backed
  Markdown download event. Mobile-width layout was visually inspected. No real
  institutional files were used in this test.

## Optional sign-in on this laptop

Default mode trusts the person using this unlocked laptop and refuses external
connections. It is labelled **local demo**, not authenticated enterprise access.
To enable accounts, set `SCHOOLTRACE_USERS` in ignored `api/.env` to a single-line
JSON object keyed by username. Each value has `password_hash`, `role` and
`workspaces` (an array of exact workspace IDs). Roles: viewer (read), analyst
(scan/propose/request evidence), reviewer (also decide proposals), admin (all
workspaces, creation and deletion). Unauthorized access defaults to denial.

Generate a salted hash locally without putting a plaintext password in shell history:

```bash
cd api
uv run python -c 'from getpass import getpass; from app.security import password_hash; print(password_hash(getpass("New local password: ")))'
```

Place the resulting hash into the following configuration shape (replace the
placeholder, never commit real credentials):

```text
SCHOOLTRACE_USERS='{"director":{"password_hash":"REPLACE_WITH_GENERATED_HASH","role":"admin","workspaces":[]}}'
```

Restart the API, then open `/access` to sign in. Sessions use HttpOnly/SameSite cookies,
expire after eight hours and are invalidated on process restart. The same local
hostname should be used for UI and API (`localhost` for both). Password entry is
rate-limited. Account changes are trusted server configuration, not an in-app IAM UI.

## Retention, data transfer and deployment gates

- Original files, snapshots and follow-up remain on disk until an admin deletes the
  workspace on `/access`. Deletion removes logical records and CFO runs, refuses
  active investigations, and requires typing the exact workspace ID. It does not
  erase OS backups, exports or recoverable filesystem remnants.
- Data directory/database permissions are restricted. This is not encrypted database
  storage. Enable appropriate device encryption and validate storage/backup controls
  before handling sensitive records; none is claimed configured by this change.
- Live provider transmission is explicit; rules-based scans do not call a provider.
  There are per-run model/tool limits and at most two simultaneous coordinator runs,
  not a global dollar-cost ceiling. One API worker is required.
- Full purchase-order/receipt quantity-price matching, complete grant eligibility,
  institutional completeness and statutory financial statements are not implemented.
- Real TDSB/Ontario use requires an independently reviewed profile: Ontario states
  boards must use Public Sector Accounting Standards and its uniform code of accounts.
  [Ontario financial accountability](https://www.ontario.ca/page/financial-accountability-education-system).
- Internet deployment remains blocked: enterprise identity/SSO, TLS/Secure cookies,
  encryption/key management, retention policies, privacy/legal review, penetration
  testing and independently held-out evaluations are not replaced by this demo.
  The local ACL approach follows request-by-request authorization and default denial;
  see [OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

This delivery is a working laptop-demo slice across all six areas, **not completion
of the production-readiness roadmap**. No auto-posting or payment execution was added.
