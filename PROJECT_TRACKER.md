# Sherlock — current implementation and handoff

Updated: 2026-09-20. Canonical product context: [schooltrace/spec.md](schooltrace/spec.md).
This tracker replaces accumulated historical checkpoints that contradicted the current code.

## Current state

| Area | Status | Where to work |
| --- | --- | --- |
| Three-screen UI | Implemented: Books, Investigation, Briefing | `web/src/lib/tabs.ts`, `web/src/app/` |
| Empty institutions | Implemented; preset content and loading paths removed | `SourcesPanel.tsx`, `store.ts`, `ingestion.py` |
| Financial intake | Implemented: upload, map, validate, commit, provenance, revisions | `ingestion.py`, `SourcesPanel.tsx` |
| Continuous updates | Implemented: snapshot differences and explicit rescans | `updates.py`, `FileUpdates.tsx` |
| Five-agent workflow | Connected coordinator and specialist/reviewer adapters | `cfo/`, `agents/team.py`, `integrations/` |
| Standalone reviews | CFO, Grants, Auditor; separate loop from coordinator | `agents/cfo.py`, `grants.py`, `auditor.py` |
| Evidence and reports | Saved runs, calculations, citations, review feed and exports | `projection.py`, `reviews.py`, `accounting/` |
| Human precedent | Implemented; automatic agent-created playbooks remain future | `approvals.py`, `Precedent.tsx` |
| Extraction lifecycle | Corrections, datasets, evaluation, promotion and rollback implemented | `extraction.py`, `document_processing.py` |
| Fine-tuned model | Artifact/training and measured benchmark performance still required | Partner training + `extractor_server.py` |
| Public deployment | Frontend auth exists; backend hosting and integrated tenant authorization remain incomplete | `proxy.ts`, `security.py`, `api.ts` |

## Latest changes

- Removed three persisted local preset workspaces and their records; deletion cannot be undone through the app. No default institutions remain locally.
- Removed bundled workspace JSON, fixture loader/seeding script, starter-pack UI and obsolete demonstration prototype.
- Fixed incompatible disabled-tab values and recovery when a selected workspace disappears.
- Added shared label/control spacing to prevent form borders intersecting text.
- Standardized enum display labels while preserving submitted lowercase identifiers.
- Shortened copy across Books, Investigation, Briefing, forms, help and login; retained existing layout and typography.
- Replaced the stale specification with a code-grounded current-state map; root `SPEC.md` links to it.

## Verification

- Backend before capitalization/doc-only work: 339 passed, 9 skipped; one dependency deprecation warning.
- Frontend lint and production build passed after the preset cleanup and form spacing changes.
- Browser showed no preset workspace or schema banner; institution form spacing was visually checked.
- These checks establish software behavior, not held-out agent or extraction accuracy.
- The cleanup is committed and integrated with main's agent board, deterministic record checks, money-in accounting and opt-in hosting support. Verify branch references and deployment status directly before further work.

## Next work to scope

1. Connect hosted API storage and authorization to the signed-in institution context for public use.
2. Integrate the partner's extraction artifact and run paired held-out benchmarks using existing gates.
3. Test the complete upload → committed snapshot → five-agent review → decision → briefing flow with representative authorized records.
4. Resolve duplicate standalone controls on Books and coordinator controls on Investigation if simplifying navigation further.
5. Address client timeout versus synchronous standalone review duration before relying on long reviews remotely.

## Handoff template

For each subsequent change, record:

- Objective and authorized scope.
- Branch and starting commit; overlapping pending edits.
- Files changed and contract/behavior changes.
- Verification command, observed result and any skipped coverage.
- Remaining blockers and one concrete next step.
- Commit/push/deployment status, stated separately from local completion.

Preserve uploaded originals, exact money calculations, workspace scope and snapshot freshness. Do not seed default institutions or recreate old demonstration content. Keep primary navigation at three destinations unless the user requests otherwise.
