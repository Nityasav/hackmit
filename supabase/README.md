# Supabase schema

Postgres holds accounts and what people do. It does not hold review content:
workspaces, records, findings, tasks and agent runs live in the intake service,
which computes them from committed records and agent runs.

## Tables

| Purpose | Tables |
| --- | --- |
| Accounts | `profiles` |
| Usage | `user_sessions`, `activity_events` |

`profiles` is created by the `handle_new_user` trigger on `auth.users` and
carries `last_seen_at` / `last_workspace` for presence.

`activity_events` records what someone did (`page_view`, `sign_in`,
`workspace_switch`, …) against a `workspace_id` owned by the intake service.
There is no foreign key to a workspaces table, because there is no such table
here.

## Functions

| Function | Granted to | What it does |
| --- | --- | --- |
| `handle_new_user()` | trigger only | Creates a profile row for a new account. |
| `touch_presence(ws, p_path)` | authenticated | Updates `last_seen_at` and `last_workspace`. The workspace id is shape-checked only and grants no access by itself. |

## Row-level security

Every table has RLS on. A person reads and writes only their own `profiles`,
`user_sessions` and `activity_events` rows.

## Outstanding

- The `on_auth_user_auto_confirm` trigger confirms new accounts without email
  verification. Remove it before real production, once SMTP is configured.
- Leaked-password protection is off; it is a Supabase dashboard toggle.
