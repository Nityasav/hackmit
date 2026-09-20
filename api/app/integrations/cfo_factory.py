"""Server-side CFO adapter wiring. Trusted configuration, not user input.

Enable with:
    CFO_ADAPTER_FACTORY=app.integrations.cfo_factory:create_adapters
"""

from ..cfo.api import Adapters
from .cfo_intake import IntakeDataSource


def create_adapters() -> Adapters:
    """Records and sources are live; the investigating agents are not yet.

    Specialist and auditor agents belong to the Agent design track
    (`app/agents/`). Register them here when they land:

        specialists={"ap": ..., "py": ..., "gr": ...}, auditor=...

    Until then a live run stops with a 503 naming the missing agents rather
    than silently falling back to the scripted harness.
    """
    return Adapters(data=IntakeDataSource())
