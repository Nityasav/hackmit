"""Server-side CFO adapter wiring. Trusted configuration, not user input.

Enable with:
    CFO_ADAPTER_FACTORY=app.integrations.cfo_factory:create_adapters
"""

import os
from ..agents.team import SnapshotAuditor, SnapshotSpecialist
from ..cfo.api import Adapters
from .cfo_intake import IntakeDataSource


def create_adapters() -> Adapters:
    """Stateless ports: each invocation owns and closes its model client."""
    configured = bool(os.getenv("OPENAI_API_KEY")) or os.getenv("SPECIALIST_PROVIDER", os.getenv("CFO_PROVIDER")) == "local"
    return Adapters(data=IntakeDataSource(),
                    specialists={role: SnapshotSpecialist(role) for role in ("ap", "py", "gr")} if configured else {},
                    auditor=SnapshotAuditor() if configured else None)
