# SchoolTrace API

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000   # http://localhost:8000/docs
uv run pytest                                       # accounting invariants
```

## Layout

| Path | Owner | What goes here |
| --- | --- | --- |
| `app/main.py` | Functionality | HTTP endpoints (see `contracts/README.md`) |
| `app/models.py` | Functionality | Pydantic mirror of the bundle contract |
| `app/store.py` | Functionality | Bundle state. Fixture-seeded today, SQLite-backed next |
| `app/accounting/` | Functionality | Exact integer-cent math and ledger invariants L01–L13 |

## Rules

- **Money is integer cents.** Never float. `app/accounting/money.py` is the only place that does arithmetic on amounts.
- **Agents cannot approve.** Only `POST /api/approvals/{id}/decision` applies a change, and it is the human path.
- **The answer key stays out of reach.** Evaluator truth files must live outside anything the tool gateway can read.
- Every agent action emits a `Decision` (see `app/models.py`) so it appears in the Reasoning log.
