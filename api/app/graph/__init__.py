"""The agent organization as a LangGraph graph.

`build()` is the entry point; `state.py` holds the shape that flows through it.
"""

from .build import build_graph, run_investigation
from .state import RunState

__all__ = ["build_graph", "run_investigation", "RunState"]
