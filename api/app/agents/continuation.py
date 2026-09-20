"""One human-decision path for graph pauses and completed standalone tasks."""
from fastapi import HTTPException
from .. import approvals, db


async def resolve(ws, approval_id, decision):
    with db.connect() as connection:
        row = connection.execute("SELECT * FROM approvals WHERE ws=? AND id=?", (ws, approval_id)).fetchone()
        if not row:
            raise HTTPException(404, "Approval not found in this workspace.")
        graph = connection.execute(
            "SELECT * FROM approvals WHERE ws=? AND finding_id=? AND id LIKE 'ESC-%'",
            (ws, row["finding_id"])).fetchone()
    if graph:
        from ..graph import resume_investigation
        from .budget import BudgetExceeded
        try:
            outcome = await resume_investigation(ws, graph["run_id"], decision, approval_id=graph["id"])
        except BudgetExceeded as exc:
            raise HTTPException(402, {"code": "budget_exceeded", "message": str(exc)})
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc))
        # Runtime ACK and graph ESC describe one conclusion, not two decisions.
        if row["id"] != graph["id"] and row["status"] == "pending":
            approvals.decide(ws, row["id"], decision)
        from .chat import _finish, reply_for
        with db.connect() as connection:
            ack = connection.execute("SELECT id FROM approvals WHERE ws=? AND finding_id=? AND id LIKE 'ACK-%' AND status='pending'",
                                     (ws, row["finding_id"])).fetchone()
        if ack:
            approvals.decide(ws, ack["id"], decision)
        with db.connect() as connection:
            turn = connection.execute("SELECT id,body FROM conversations WHERE ws=? AND (run_id=? OR (run_id='' AND thread_id=?)) AND role='orchestrator' ORDER BY rowid DESC LIMIT 1",
                                      (ws, graph["run_id"], graph["run_id"])).fetchone()
            if turn:
                import json
                previous = json.loads(turn["body"])
                _finish(connection, ws, turn["id"], {**previous, **reply_for(outcome)},
                        "waiting_on_you" if outcome.get("waiting_on_you") else "done")
        from .activity import emit
        emit(ws, graph["run_id"], row["agent"], "completed", "Human decision recorded: " + decision)
        return outcome
    approvals.decide(ws, approval_id, decision)
    return {"status": "completed", "note": "Standalone task resolved. Use revised instructions to request further work."}
