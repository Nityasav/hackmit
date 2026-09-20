"""Persist observable execution events, never private reasoning or raw prompts."""
from .. import db


def emit(ws, thread_id, agent, status, detail=""):
    with db.connect() as connection:
        db.event(connection, ws, "agent.activity",
                 {"thread_id": thread_id, "agent": agent, "status": status, "detail": detail})
