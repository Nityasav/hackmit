"""Server-side CFO adapter wiring. Trusted configuration, not user input.

Enable with:
    CFO_ADAPTER_FACTORY=app.integrations.cfo_factory:create_adapters
"""

from ..agents.payroll import PayrollBudgetSpecialist
from ..cfo.api import Adapters
from .cfo_intake import IntakeDataSource


def payroll_specialist() -> PayrollBudgetSpecialist | None:
    """The `py` agent, when this server is configured to call a model.

    Returned as None rather than raised when credentials or a model ID are
    absent: the factory runs once at process start, and a server that has not
    configured a specialist model should still serve intake and scripted runs.
    A live run then stops with the 503 that names the agents it is missing.
    """
    try:
        return PayrollBudgetSpecialist.from_env()
    except (ImportError, ValueError):
        return None


def create_adapters() -> Adapters:
    """Records, payroll amounts and the Payroll & Budget agent are live.

    AP (`ap`), Grants (`gr`) and the independent Internal Auditor belong to the
    same Agent design track (`app/agents/`). Register them here when they land:

        specialists={"ap": ..., "py": ..., "gr": ...}, auditor=...

    Until every one of them exists a live run stops with a 503 naming the
    missing agents rather than silently falling back to the scripted harness,
    because no claim may be accepted without independent review.
    """
    specialists = {}
    payroll = payroll_specialist()
    if payroll is not None:
        specialists["py"] = payroll
    return Adapters(data=IntakeDataSource(), specialists=specialists)
