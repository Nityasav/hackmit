# Database

Postgres on Supabase is the source of truth for everything the dashboard
renders. The JSON under `seed/` is only the material the tables were first
loaded from — the app does not read it at runtime.

## What is stored

| Area | Tables |
| --- | --- |
| Workspace | `workspaces` |
| Agents | `agents`, `agent_state_events` |
| Briefing | `briefings`, `briefing_actions` |
| Headline numbers | `kpis` |
| Workflows | `workflows`, `workflow_stages` |
| Agent board | `tasks`, `task_steps`, `task_todos`, `task_transitions` |
| Findings | `findings`, `evidence_nodes` |
| Approvals | `approvals`, `approval_journal_lines`, `approval_effects`, `approval_decisions` |
| Reasoning log | `decisions`, `decision_tags`, `decision_tool_calls`, `decision_alternatives`, `decision_memory_checks` |
| Learning | `playbooks`, `ablations`, `ablation_rows` |
| Report | `reports`, `report_sections`, `report_comparisons` |
| Sample records | `starter_packs`, `starter_pack_files` |
| People | `profiles` |
| What people do | `user_sessions`, `activity_events` |

History is kept rather than overwritten: `agent_state_events` records every
change to what an agent is doing, `task_transitions` records every board move,
and `approval_decisions` records every decision including reversals.

## Functions

| Function | Who may call it | What it does |
| --- | --- | --- |
| `get_bundle(ws)` | authenticated | Assembles the whole dashboard payload in one round trip. Runs as the caller, so row-level policies decide what comes back. |
| `list_workspaces()` | authenticated | The workspaces the caller may open. |
| `decide_approval(ws, approval, decision)` | authenticated | The human approval path. Updates the approval, logs the decision, closes the waiting task and records the activity, atomically. |
| `touch_presence(ws, path)` | authenticated | Keeps `profiles.last_seen_at` current. |
| `seed_workspace(bundle)` | nobody by default | Loads a bundle from JSON. Granted only for the length of a seed run. |
| `seed_starter_pack(pack)` | nobody by default | Same, for the sample records. |

## Row-level security

RLS is on for every table. A table with RLS on and no policy denies
everything, so each policy below opens one thing deliberately.

- Workspaces with no owner are shared demos every signed-in user can read.
  Workspaces with an owner are readable only by that owner.
- Child tables reach the workspace through `can_read_workspace()`, and
  grandchildren reach it through their parent.
- The only write the dashboard makes against shared data is deciding an
  approval, and it goes through `decide_approval`.
- `user_sessions` and `activity_events` are readable and writable only by the
  person they describe.

## Re-seeding

```bash
cd web
set -a; . ./.env.local; set +a
SEED_EMAIL=you@example.com SEED_PASSWORD=... node scripts/seed-db.mjs
```

`seed_workspace` must be granted to `authenticated` for the run and revoked
after:

```sql
grant execute on function public.seed_workspace(jsonb) to authenticated;
-- run the seeder
revoke execute on function public.seed_workspace(jsonb) from authenticated;
```
