"""Versioned CFO handoff contracts; independent of the existing dashboard bundle."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")


Role = Literal["ap", "py", "gr"]


class Source(Contract):
    id: str
    title: str
    locator: str
    domain: Literal["ap", "py", "gr", "shared"]


class CalculationSpec(Contract):
    id: str
    description: str
    source_ids: list[str] = Field(min_length=1)


class Scope(Contract):
    workspace: str
    snapshot_id: str
    institution: str
    period: str
    accounting_profile: str
    sources: list[Source]
    calculations: list[CalculationSpec] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class SourceSpan(Contract):
    id: str
    snapshot_id: str
    text: str
    locator: str


class Calculation(Contract):
    id: str
    snapshot_id: str
    source_ids: list[str] = Field(min_length=1)
    amount_cents: StrictInt
    cash_delta_cents: StrictInt
    category: Literal["reclassification", "exposure", "potential_recovery", "none"]
    description: str


class TaskSpec(Contract):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    role: Role
    objective: str = Field(min_length=1, max_length=2000)
    source_ids: list[str]
    depends_on: list[str] = Field(default_factory=list)
    priority: int = Field(default=2, ge=1, le=3)
    success_criteria: str = Field(min_length=1, max_length=1000)


class Plan(Contract):
    rationale: str = Field(max_length=2000)
    tasks: list[TaskSpec] = Field(min_length=1, max_length=8)


class Claim(Contract):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    event_key: str = Field(min_length=1, max_length=200)
    title: str = Field(max_length=200)
    conclusion: str = Field(min_length=1, max_length=2000)
    disposition: Literal["substantiated", "cleared", "explained"]
    evidence_ids: list[str] = Field(min_length=1)
    calculation_id: str | None = None
    proposed_action: str = Field(default="No financial change proposed.", max_length=1000)


class WorkerResult(Contract):
    summary: str = Field(max_length=2000)
    claims: list[Claim] = Field(default_factory=list, max_length=8)
    evidence_requests: list[str] = Field(default_factory=list, max_length=8)


class Review(Contract):
    verdict: Literal["accept", "reject", "needs_evidence"]
    rationale: str = Field(min_length=1, max_length=2000)
    required_action: str = Field(default="", max_length=2000)


class FollowUp(Contract):
    action: Literal["retry", "request_evidence", "stop"]
    instruction: str = Field(min_length=1, max_length=2000)


class NarrativeItem(Contract):
    claim_id: str
    explanation: str = Field(min_length=1, max_length=1500)
    proposed_next_step: str = Field(min_length=1, max_length=1000)


class Narrative(Contract):
    """Only accepted claim IDs may occur here; numeric values are rendered separately."""

    items: list[NarrativeItem] = Field(default_factory=list, max_length=64)


class Limits(Contract):
    max_tasks: int = Field(default=8, ge=1, le=8)
    concurrency: int = Field(default=2, ge=1, le=2)
    #: Charged per actor per task, so a preparer and the auditor reviewing it
    #: each get this many. 12 was set for the preparer's own work and is too
    #: small for the reviewer: reperforming one claim costs a fresh read of
    #: every cited source plus a recalculation, so five claims exhausts it and
    #: the task fails with BudgetExceeded mid-review — taking any task that
    #: depends on it down as blocked. The reviewer is the expensive actor
    #: because it is not allowed to trust what it is reviewing.
    tool_calls_per_agent_task: int = Field(default=24, ge=1, le=24)
    #: Raised with it, so the run-level cap does not simply become the next
    #: thing to fail on: six actor-task pairs at 24 each can ask for 144.
    #: These are local source reads and recalculations, not model calls —
    #: `max_model_calls` is what bounds spend, and it is unchanged.
    max_tool_calls: int = Field(default=150, ge=1, le=300)
    review_cycles: int = Field(default=2, ge=1, le=2)
    call_timeout_s: float = Field(default=60, gt=0, le=180)
    max_model_calls: int = Field(default=12, ge=2, le=30)


class RunRequest(Contract):
    workflow: Literal["focused", "five_agent"] = "focused"
    # A workspace ID only a registered live data adapter can resolve.
    workspace: str = Field(default="test-workspace", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    objective: str = Field(default="Review the current close and prepare a CFO briefing.", min_length=1, max_length=2000)
    mode: Literal["live"] = "live"
    limits: Limits = Field(default_factory=Limits)


class Event(Contract):
    at: str = Field(default_factory=now)
    actor: str
    action: str
    task_id: str | None = None
    detail: str
    references: list[str] = Field(default_factory=list)


class TaskState(Contract):
    spec: TaskSpec
    status: Literal["queued", "working", "auditor_review", "done", "needs_evidence", "failed", "blocked"] = "queued"
    attempts: int = 0
    tool_calls: int = 0
    actor_tool_calls: dict[str, int] = Field(default_factory=dict)
    result: WorkerResult | None = None


class AcceptedClaim(Contract):
    task_id: str
    role: Role
    claim: Claim
    review: Review
    calculation: Calculation | None = None


class Run(Contract):
    id: str
    request: RunRequest
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    status: Literal["queued", "planning", "running", "completed", "needs_evidence", "partial", "failed", "stale", "interrupted"] = "queued"
    scope: Scope | None = None
    plan: Plan | None = None
    tasks: list[TaskState] = Field(default_factory=list)
    accepted: list[AcceptedClaim] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    tool_calls: int = 0
    model_calls: int = 0
    cfo_input_tokens: int = 0
    cfo_output_tokens: int = 0
    briefing: str = "Investigation queued. No conclusions yet."
    report_markdown: str = ""
    model_label: str = "not recorded"
