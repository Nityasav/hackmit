# Contracts

The seam between the four workstreams. **Change these three together:**

| File | Owner of the change |
| --- | --- |
| `contracts/fixtures/*.json` | whoever adds the data |
| `web/src/lib/types.ts` | UI |
| `api/app/models.py` | Functionality |

If you change a field, say so in the team channel before you push. Everything else can move independently.

## The bundle

The dashboard renders **one JSON payload per workspace**: `GET /api/workspaces/{sandbox|mit}/bundle`.
With no API running, the web app reads `contracts/fixtures/{ws}.json` directly, so the UI works offline.

```
Bundle
├─ workspace      id, name, kind (synthetic|public), period, mode (live|recorded|scripted),
│                 snapshot_id, disabled_tabs[], model, run_budget
├─ agents[]       cfo | ap | py | gr | au — name, role, status, "doing" (drives the live strip)
├─ briefing       CFO Agent text (**bold** marks highlights) + action buttons
├─ kpis[]         label, value, note, tone
├─ workflows[]    id, name, owner, progress, stages[] (done|running|human|todo)
├─ tasks[]        Agent board cards: column (queued|working|needs_you|auditor_review|done),
│                 progress, eta_s, tool_calls, steps[], todos[], rationale, approval_id
├─ findings[]     status, amount_cents, verified_by, evidence[] (the graph path)
├─ approvals[]    kind (journal|payment|playbook|evidence), journal[], effects[], status
├─ decisions[]    Reasoning log: when / how (tool calls) / why / alternatives / memory_checks / outcome
├─ playbooks[]    RSI: replay gate result, uses, status (active|needs_approval|retired|blocked)
├─ ablation       memory on vs off. `example: true` until the evaluator produces real numbers
└─ report         sections, before/after comparisons, applies_approval
```

## Rules

1. **Money is integer cents.** `amount_cents: 400000` is $4,000.00. The UI formats it; nothing else does.
2. **Task columns map to spec statuses**: `queued → queued`, `running → working`, `needs_evidence → needs_you`,
   `submitted → auditor_review`, `review_accepted → done`.
3. **Every finding carries evidence**, and every amount traces to a calculation ID. No bare numbers.
4. **`decisions[]` holds concise decision records**, never raw chain-of-thought (spec.md §8).
5. **`example: true` on ablation** means the numbers are placeholders. Remove it only when the evaluator
   wrote them (DATA_AND_EVALUATION.md §9).
6. **Only a human decides an approval.** Agents propose; `POST /api/approvals/{id}/decision` is the human path.

## Endpoints (hackathon minimum)

| Endpoint | Behavior |
| --- | --- |
| `GET /api/health` | liveness |
| `GET /api/workspaces/{ws}/bundle` | everything the dashboard renders. The web app polls every 2s |
| `POST /api/approvals/{id}/decision` | `{workspace, decision}` → updated bundle |
| `POST /api/demo/{action}` | `reset`, `inject_issue`, `add_evidence`, `next_month` |
