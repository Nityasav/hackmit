// Mirror of contracts/README.md. api/app/models.py mirrors the same shapes.
// Change all three together.

export type AgentId = "cfo" | "ap" | "py" | "gr" | "au";
export type WorkspaceId = "sandbox" | "mit";
export type TabId =
  | "command"
  | "board"
  | "workflows"
  | "findings"
  | "approvals"
  | "reports"
  | "reasoning"
  | "learning";

export interface Workspace {
  id: WorkspaceId;
  name: string;
  kind: "synthetic" | "public";
  period: string;
  mode: "live" | "recorded" | "scripted";
  snapshot_id: string;
  disabled_tabs: TabId[];
  model: string;
  run_budget: { used: number; total: number };
  source_url?: string;
}

export interface Agent {
  id: AgentId;
  name: string;
  short: string;
  role: string;
  status: "working" | "waiting" | "idle";
  doing: string;
}

export interface Briefing {
  generated_at: string;
  /** Plain text; **double asterisks** mark highlights. */
  text: string;
  actions: { label: string; href: TabId; primary?: boolean }[];
}

export interface Kpi {
  label: string;
  value: string;
  note: string;
  tone?: "good" | "warn" | "neutral";
}

export type StageState = "done" | "running" | "human" | "todo";

export interface Workflow {
  id: string;
  name: string;
  owner: AgentId;
  progress: number;
  stages: { name: string; state: StageState }[];
}

export type Column = "queued" | "working" | "needs_you" | "auditor_review" | "done";

export interface TaskStep {
  title: string;
  detail?: string;
  state: "done" | "running" | "todo";
  memory?: boolean;
}

export interface Task {
  id: string;
  agent: AgentId;
  title: string;
  workflow: string;
  column: Column;
  progress: number;
  eta_s: number | null;
  started_at: string | null;
  tool_calls: { used: number; budget: number };
  steps: TaskStep[];
  todos: string[];
  rationale: string | null;
  note?: string;
  note_tone?: "warn" | "info";
  /** Set on "needs_you" tasks that wait on an Approval. */
  approval_id?: string;
}

export interface EvidenceNode {
  label: string;
  kind: "record" | "award" | "doc" | "calc" | "page";
  tone: "neutral" | "bad" | "good";
  /** Graph edge from this node to the next one. */
  edge?: string;
}

export type FindingStatus =
  | "substantiated"
  | "cleared"
  | "explained"
  | "needs_evidence"
  | "none_reported"
  | "ties";

export interface Finding {
  id: string;
  agent: AgentId;
  title: string;
  summary: string;
  status: FindingStatus;
  amount_cents: number | null;
  amount_note?: string;
  verified_by?: AgentId;
  evidence: EvidenceNode[];
}

export interface JournalLine {
  account: string;
  fund: string;
  debit_cents: number;
  credit_cents: number;
}

export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface Approval {
  id: string;
  agent: AgentId;
  kind: "journal" | "payment" | "playbook" | "evidence";
  title: string;
  summary: string;
  verified: boolean;
  status: ApprovalStatus;
  journal?: JournalLine[];
  effects?: { label: string; value: string; tone?: "good" | "neutral" }[];
}

export interface Decision {
  id: string;
  run: string;
  time: string;
  agent: AgentId;
  action: string;
  summary: string;
  tags: { label: string; kind?: "mem" | "memx" }[];
  when: { run: string; step: string; started: string; finished: string; trigger: string };
  how: { tool: string; input: string; output: string }[];
  why: string;
  alternatives: { option: string; reason: string; chosen: boolean }[];
  memory_checks: { text: string; ok: boolean }[];
  outcome: string;
}

export type PlaybookStatus = "active" | "needs_approval" | "retired" | "blocked";

export interface Playbook {
  id: string;
  title: string;
  source: string;
  proposed_by: AgentId;
  replay: { passed: boolean; new_false_positives: number; months: string[] };
  uses: string;
  status: PlaybookStatus;
  status_note?: string;
}

export interface Ablation {
  /** true until the numbers come from the real evaluator (DATA_AND_EVALUATION.md). */
  example: boolean;
  rows: { metric: string; without: number; with: number }[];
  note: string;
}

export interface Report {
  title: string;
  sections: string[];
  comparisons: { label: string; before: string; after: string }[];
  applies_approval?: string;
  before_label?: string;
  after_label?: string;
}

export interface Bundle {
  workspace: Workspace;
  agents: Agent[];
  briefing: Briefing;
  kpis: Kpi[];
  workflows: Workflow[];
  tasks: Task[];
  findings: Finding[];
  approvals: Approval[];
  decisions: Decision[];
  playbooks: Playbook[];
  ablation: Ablation | null;
  report: Report;
}
