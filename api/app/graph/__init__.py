"""The agent organization as a LangGraph graph.

`build_graph()` compiles it; `run_investigation()` starts one; `resume_investigation()`
continues one that stopped for a person. `state.py` holds the shape that flows through.
"""

from .build import build_graph, checkpointer_path, resume_investigation, run_investigation
from .escalation import pending
from .state import RunState

__all__ = ["build_graph", "checkpointer_path", "pending", "resume_investigation",
           "run_investigation", "RunState"]
