# Sources, assumptions, and verification boundaries

Research date: 2026-09-19. These references ground selected concepts; they are not a complete or current codification of all applicable accounting and grant requirements. The application must use versioned institution/award policies and qualified review for deployment.

## Challenge source

The user supplied the Maximor HackMIT 2026 track brief. It emphasizes coordinated finance workflows, agent handoffs, persistent memory/context, multi-step document reasoning, consistent transaction treatment, human escalation, and measurable improvement. This package maps to that supplied brief; prize and recruiting claims were not independently verified and are not needed for implementation.

## Primary reference material

| Reference | How it informs this design | Boundary |
| --- | --- | --- |
| [California Department of Education — GASB 34 FAQ](https://www.cde.ca.gov/fg/ac/as/faqs.asp) | Basis separation, encumbrance/AP distinction, and potential financing/grant consequences of adverse reporting | Historical implementation FAQ; some sections are outdated. Do not use its historical pension/OPEB discussion as current guidance. |
| [GASB Statement 34](https://storage.gasb.org/GASBS%2034.pdf) | Foundational governmental fund versus government-wide reporting concepts | Original statement, subsequently amended; not a current complete implementation manual. |
| [GASB Statement 54](https://storage.gasb.org/GASBS%2054.pdf) | Governmental fund-balance classification concepts | Management grant tags are not a substitute for formal fund-balance reporting. |
| [GAO — Green Book](https://www.gao.gov/greenbook) | Internal-control documentation, review, reliable information, and remediation | Framework reference; does not establish automatic applicability to every institution. |
| [GAO — Yellow Book](https://www.gao.gov/yellowbook) | Distinguishes real government audit standards from internal product review | SchoolTrace does not perform or certify a Yellow Book audit. |
| [Federal Register — 2024 Guidance for Federal Financial Assistance](https://www.federalregister.gov/citation/89-FR-30109) | Official published revision context for federal award cost principles | Verify effective dates, later changes, agency implementation, and award terms before activation. |
| [Ohio Department of Education — Perkins allowable use guidance](https://education.ohio.gov/getattachment/Topics/Finance-and-Funding/School-Payment-Reports/State-Funding-For-Schools/Career-Tech-Planning-and-Funding/FY24-Perkins-Regulations-and-Allowable-Use-of-Funds-Guidance.pdf.aspx?lang=en-US) | Education-agency illustration of reasonable/allocable costs and compensation concepts | Program-specific and dated guidance; not a universal rule pack. |
| [US Department of Education — FERPA](https://studentprivacy.ed.gov/ferpa) | Education-record privacy considerations and deployment boundaries | Synthetic MVP avoids real education records; this is not a compliance certification. |

## Current regulation verification required before deployment

Canonical links for further review:

- [2 CFR 200.403 — Factors affecting allowability](https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-E/section-200.403)
- [2 CFR 200.405 — Allocable costs](https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-E/section-200.405)
- [2 CFR 200.430 — Compensation, personal services](https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-E/section-200.430)

Direct eCFR pages were inaccessible through the research tool during preparation. Consequently, this package does not claim to have verified the full current text of those sections. It uses broad design concepts and explicit fictional award terms rather than encoding unverified statutory thresholds, universal rates, or legal conclusions.

## Design assumptions, not sourced claims

- The institution, staffing/enrollment counts, financial amounts, award rules, and issue catalog are synthetic.
- The claimed product opportunity is a hypothesis, not a measured prevalence of financial mismanagement across schools.
- Five agents, SQL graph tables, a two-month demo, and the proposed resource budget are engineering choices.
- Precision/recall and intervention-reduction thresholds are proposed targets until an implemented evaluator measures them.
- Graph-based context and reviewed memory may improve retrieval and consistency; the ablation must establish whether they help this prototype.
- The simplified accrual management profile deliberately excludes complete statutory reporting and complex pension, debt, and deferred-resource accounting.

## Deployment research still needed

Confirm the institution's legal entity and jurisdiction; applicable reporting framework and current amendments; grant agreements and agency rules; collective agreements and benefit policies; delegated approval matrix; records retention and student/employee privacy requirements; model-provider data handling; and reviewer/accountant sign-off on each enabled accounting policy.

For Canadian school boards or universities, replace the US demonstration policy references with the institution's applicable Canadian/provincial reporting and funding rules before using the output operationally.
