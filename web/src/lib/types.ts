// Mirror of the bundle contract in /README.md. api/app/models.py mirrors the same shapes.
// Change all three together.

export type AgentId = "cfo" | "ap" | "py" | "gr" | "au";
export type WorkspaceId = string;
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
  mode: "live" | "recorded" | "scripted" | "not_started";
  snapshot_id: string;
  disabled_tabs: TabId[];
  model: string;
  run_budget: { used: number; total: number };
  source_url?: string;
  intake?: boolean;
  currency?: string;
  profile?: string;
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
  /** Where this came from: file + row, or document + page. */
  locator?: string;
  /** Short excerpt of the source, shown when the node is opened. */
  source_preview?: string;
}

export type FindingStatus =
  | "hypothesized"
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
  kind: "journal" | "payment" | "playbook" | "evidence" | "decision";
  title: string;
  summary: string;
  verified: boolean;
  status: ApprovalStatus;
  journal?: JournalLine[];
  effects?: { label: string; value: string; tone?: "good" | "neutral" }[];
  /** The finding this proposal would resolve, when it came from one. */
  finding_id?: string | null;
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
  /** true until the numbers come from the real evaluator. */
  example: boolean;
  rows: { metric: string; without: number; with: number }[];
  note: string;
}

export interface Report {
  title: string;
  sections: string[];
  comparisons: { label: string; before: string; after: string }[];
  /** The run's own published Markdown, when a run produced one. */
  markdown?: string | null;
  applies_approval?: string;
  before_label?: string;
  after_label?: string;
}

export interface Bundle {
  contract_version?: number;
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

export type SourceRole = "chart" | "opening" | "ledger" | "payroll" | "grants" | "budget" | "invoice" | "service" | "policy" | "document";
export interface IntakeWorkspace {
  id: string; name: string; kind: "synthetic" | "public";
  entity_type: "school" | "district" | "board" | "university";
  jurisdiction: string; currency: "USD" | "CAD" | "EUR" | "GBP";
  start: string; end: string; scope: string; profile: string; revision: number;
}
export interface SourceOptions {
  role: SourceRole; source_system: string; source_version: number;
  external_id: string; applies_to: string; mapping: Record<string, string>;
  amount_unit: "major" | "minor"; expected_rows?: number | null;
  expected_debit?: string | null; expected_credit?: string | null;
  excluded: boolean; exclusion_reason: string;
}
export interface ImportFile {
  id: string; name: string; sha256: string; options: SourceOptions;
  headers: string[]; required_fields: string[]; row_count: number;
  preview: { key: string; locator: number; payload: Record<string, string | number> }[];
  totals: Record<string, number>; duplicate_of: string | null;
}
export interface ImportBatch {
  id: string; workspace_id: string; status: string; version: number; base_revision: number;
  created_at: string; snapshot_id: string | null; files: ImportFile[];
  counts: { parsed: number; valid_records: number; new_records: number; duplicate_records: number; issues: number };
  totals: { debit_cents: number; credit_cents: number };
  issues: { code: string; message: string; source_id: string; locator?: number; field?: string }[];
  issues_truncated: boolean;
  changes: { record_key: string; role: string; previous: unknown; next: unknown }[];
  coverage_note: string;
}
export interface EvidenceRequest {
  id: string; title: string; role: SourceRole; task_id: string | null;
  status: string; source_id: string | null; snapshot_id: string | null; version: number;
}
export interface Coverage {
  workspace: IntakeWorkspace; snapshot: { id: string; revision: number; created_at: string } | null;
  counts: Record<string, number>;
  capabilities: { id: string; label: string; status: string; missing: string[]; note: string }[];
  sources: { id: string; name: string; sha256: string; role: SourceRole; active: boolean }[];
  requests: EvidenceRequest[]; coverage_verified: boolean; note: string;
}
export interface SourceDetail {
  id: string; name: string; sha256: string; committed: boolean; options: SourceOptions;
  line_count: number; lines: { number: number; text: string }[];
}
export interface AgentCitation { source_id: string; line: number; quote: string }
export interface AgentRun {
  id: string; workspace_id: string; agent: "cfo" | "grants_compliance" | "internal_auditor"; snapshot_id: string;
  current_snapshot: boolean;
  review_targets_current?: boolean | null;
  status: "running" | "completed" | "failed"; model: string; focus: string;
  created_at: string; completed_at: string | null; error: string | null;
  result: {
    analysis?: {
      executive_briefing: string; scope_assessed: string; limitations: string[];
      findings: { title: string; status: "hypothesized" | "needs_evidence" | "cleared";
        summary: string; citations: AgentCitation[]; limitations: string[] }[];
      evidence_requests: { title: string; role: SourceRole; reason: string }[];
      next_tasks: { specialist: string; title: string; objective: string }[];
      reviews?: { finding_id: string; verdict: "accept" | "reject" | "needs_evidence";
        rationale: string; citations: AgentCitation[]; required_action: string }[];
    };
    review_scope?: { candidate_count: number; reviewed_count: number; unreviewed_finding_ids: string[] };
    tool_calls?: { tool: string; input_hash: string; output_ref: string; latency_ms: number; status: string }[];
    usage?: { input_tokens: number; output_tokens: number; total_tokens: number };
  };
}
