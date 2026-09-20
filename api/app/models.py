"""Pydantic mirror of the bundle contract in /README.md and web/src/lib/types.ts.

Change all three together. Money is always integer cents.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

AgentId = Literal["cfo", "ap", "py", "gr", "au"]
WorkspaceId = str
TabId = Literal[
    "command", "board", "workflows", "findings", "approvals", "reports", "reasoning", "learning"
]
Column = Literal["queued", "working", "needs_you", "auditor_review", "done"]
StageState = Literal["done", "running", "human", "todo"]
ApprovalStatus = Literal["pending", "approved", "rejected"]


class RunBudget(BaseModel):
    used: int
    total: int


class Workspace(BaseModel):
    id: WorkspaceId
    name: str
    kind: Literal["synthetic", "public"]
    period: str
    mode: Literal["live", "not_started"]
    snapshot_id: str
    disabled_tabs: list[TabId]
    model: str
    run_budget: RunBudget
    source_url: str | None = None
    intake: bool = False
    currency: str = "USD"
    profile: str | None = None


class Agent(BaseModel):
    id: AgentId
    name: str
    short: str
    role: str
    status: Literal["working", "waiting", "idle"]
    doing: str


class BriefingAction(BaseModel):
    label: str
    href: TabId
    primary: bool = False


class Briefing(BaseModel):
    generated_at: str
    text: str
    actions: list[BriefingAction]


class Kpi(BaseModel):
    label: str
    value: str
    note: str
    tone: Literal["good", "warn", "neutral"] | None = None


class Stage(BaseModel):
    name: str
    state: StageState


class Workflow(BaseModel):
    id: str
    name: str
    owner: AgentId
    progress: int
    stages: list[Stage]


class TaskStep(BaseModel):
    title: str
    detail: str | None = None
    state: Literal["done", "running", "todo"]
    memory: bool = False


class ToolCalls(BaseModel):
    used: int
    budget: int


class Task(BaseModel):
    id: str
    agent: AgentId
    title: str
    workflow: str
    column: Column
    progress: int
    eta_s: int | None = None
    started_at: str | None = None
    tool_calls: ToolCalls
    steps: list[TaskStep]
    todos: list[str]
    rationale: str | None = None
    note: str | None = None
    note_tone: Literal["warn", "info"] | None = None
    approval_id: str | None = None


class EvidenceNode(BaseModel):
    label: str
    kind: Literal["record", "award", "doc", "calc", "page"]
    tone: Literal["neutral", "bad", "good"]
    edge: str | None = None
    #: file + row, or document + page
    locator: str | None = None
    #: short excerpt shown when the node is opened in the UI
    source_preview: str | None = None


class Finding(BaseModel):
    id: str
    agent: AgentId
    title: str
    summary: str
    status: Literal[
        "hypothesized", "substantiated", "cleared", "explained", "needs_evidence", "none_reported", "ties"
    ]
    amount_cents: int | None = None
    amount_note: str | None = None
    verified_by: AgentId | None = None
    evidence: list[EvidenceNode]


class JournalLine(BaseModel):
    account: str
    fund: str
    debit_cents: int
    credit_cents: int


class Effect(BaseModel):
    label: str
    value: str
    tone: Literal["good", "neutral"] | None = None


class Approval(BaseModel):
    id: str
    agent: AgentId
    kind: Literal["journal", "payment", "playbook", "evidence", "decision"]
    title: str
    summary: str
    verified: bool
    status: ApprovalStatus
    journal: list[JournalLine] | None = None
    effects: list[Effect] | None = None
    #: The finding this proposal would resolve, when it came from one.
    finding_id: str | None = None


class DecisionWhen(BaseModel):
    run: str
    step: str
    started: str
    finished: str
    trigger: str


class ToolCall(BaseModel):
    tool: str
    input: str
    output: str


class Alternative(BaseModel):
    option: str
    reason: str
    chosen: bool


class MemoryCheck(BaseModel):
    text: str
    ok: bool


class Tag(BaseModel):
    label: str
    kind: Literal["mem", "memx"] | None = None


class Decision(BaseModel):
    """One structured decision record per agent action. Feeds the Reasoning log.

    Concise rationale only, never raw chain-of-thought.
    """

    id: str
    run: str
    time: str
    agent: AgentId
    #: Set when a person took this decision rather than an agent. `agent` has no
    #: value that means "a human", and a human approval is the decision the log
    #: most needs to carry, so the reviewer is named here instead of faked there.
    actor: str | None = None
    action: str
    summary: str
    tags: list[Tag]
    when: DecisionWhen
    how: list[ToolCall]
    why: str
    alternatives: list[Alternative]
    memory_checks: list[MemoryCheck]
    outcome: str


class Replay(BaseModel):
    passed: bool
    new_false_positives: int
    months: list[str]


class Playbook(BaseModel):
    id: str
    title: str
    source: str
    proposed_by: AgentId
    replay: Replay
    uses: str
    status: Literal["active", "needs_approval", "retired", "blocked"]
    status_note: str | None = None


class AblationRow(BaseModel):
    metric: str
    without: float
    with_: float

    model_config = {"populate_by_name": True}


class Ablation(BaseModel):
    example: bool
    rows: list[dict]
    note: str


class Comparison(BaseModel):
    label: str
    before: str
    after: str


class Report(BaseModel):
    title: str
    sections: list[str]
    comparisons: list[Comparison]
    #: The run's own published Markdown, when a run produced one. Rendered by
    #: app/cfo/reporting.py so the export is the report, not a second rendering.
    markdown: str | None = None
    applies_approval: str | None = None
    before_label: str | None = None
    after_label: str | None = None


class Bundle(BaseModel):
    contract_version: int = 2
    workspace: Workspace
    agents: list[Agent]
    briefing: Briefing
    kpis: list[Kpi]
    workflows: list[Workflow]
    tasks: list[Task]
    findings: list[Finding]
    approvals: list[Approval]
    decisions: list[Decision]
    playbooks: list[Playbook]
    ablation: Ablation | None = None
    report: Report


class ApprovalDecision(BaseModel):
    workspace: WorkspaceId
    decision: Literal["approved", "rejected"]
