// Mirror of the bundle contract in /README.md. api/app/models.py mirrors the same shapes.
// Change all three together.

/** Mirrors `AgentId` in api/app/models.py, which mirrors the registry in
 *  api/app/agents/registry.py. Change this, models.py and contracts/README.md in
 *  one commit: a bundle that fails to parse renders an error, not a workspace. */
export type AgentId =
  | "orchestrator"
  | "A" | "B" | "C" | "D"
  | "A1" | "A2" | "A3" | "A4"
  | "B1" | "B2" | "B3" | "B4"
  | "C1" | "C2" | "C3" | "C4" | "C5"
  | "D1" | "D2" | "D3" | "D4";
export type WorkspaceId = string;

/**
 * The tab ids the API emits, mirroring `TabId` in api/app/models.py.
 *
 * This is not the navigation — that is `NavId` in lib/tabs.ts, which is four
 * destinations. This list has to stay as wide as the producer's, because the
 * bundle is parsed against it: when the screens were cut back, this enum was
 * narrowed but `_disabled_tabs` still returned "learning" and briefings still
 * linked to "approvals", so every bundle carrying either failed to parse and
 * the dashboard rendered an error instead of a workspace.
 */
export type TabId =
  | "command" | "board" | "workflows" | "findings"
  | "approvals" | "reports" | "reasoning" | "learning";

export interface Workspace {
  id: WorkspaceId;
  name: string;
  kind: "synthetic" | "public";
  period: string;
  /** Narrower than api/app/models.py: the web app only ever receives a
   *  bundle built by ingestion.bundle(), which emits these two. */
  mode: "live" | "not_started";
  snapshot_id: string;
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

export type Column = "queued" | "working" | "needs_you" | "auditor_review" | "done";

export interface TaskStep {
  title: string;
  detail?: string | null;
  state: "done" | "running" | "todo";
  memory?: boolean;
  /** When the step landed, as the run recorded it. */
  at?: string | null;
}

/** What an agent returned, exactly as it returned it. */
export interface AgentOutput {
  summary?: string;
  disposition?: "clear" | "exception" | "insufficient_evidence";
  rationale?: string;
  proposed_action?: string;
  open_questions?: string[];
  citations?: { role: string; record_key?: string; source_id?: string; line?: number | null; note?: string }[];
  exceptions?: { code: string; detail: string }[];
  memory_checks?: { precedent_id: string; applied: boolean; reason: string }[];
  may_pay?: boolean;
  matched_po?: string;
  matched_receipt?: string;
}

export interface AgentReview {
  reviewer: string;
  reviewer_name?: string;
  verdict: "accepted" | "rejected" | "needs_evidence" | "not_reviewed";
  summary?: string;
  rationale?: string;
  decision_id?: string;
}

/** Everything else the run recorded about one task, shown in the drawer. */
export interface TaskDetail {
  agent_name: string;
  charter: string;
  tier: string;
  parent: string | null;
  reviewer: string | null;
  model: string;
  objective: string;
  summary: string;
  state: string;
  confidence: number | null;
  cost_cents: number;
  model_calls: number;
  model_budget: number;
  cost_budget_cents: number;
  escalation_reasons: string[];
  error: string | null;
  thread_id: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  result?: AgentOutput | null;
  review?: AgentReview | null;
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
  /** The proposal this task is waiting on, when it stopped for a person. */
  approval_id?: string | null;
  /** The decision record this task wrote, for the evidence behind the card. */
  decision_id?: string | null;
  detail?: TaskDetail | null;
}

/** `/api/workspaces/{ws}/agents/activity`: the board, as the runtime recorded it. */
export interface AgentActivity {
  tasks: Task[];
  /** Tasks still queued, working or in review. Zero means nothing is running. */
  active: number;
  waiting: number;
  note: string;
  spend?: { today_cents: number; day_cap_cents: number; run_cap_cents: number };
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

export interface Decision {
  id: string;
  run: string;
  time: string;
  agent: AgentId;
  /** Set when a person took this decision rather than an agent; `agent` only
   *  groups it with its run and must not be shown as the author. */
  actor?: string | null;
  action: string;
  summary: string;
  when: { run: string; step: string; started: string; finished: string; trigger: string };
  how: { tool: string; input: string; output: string }[];
  why: string;
  outcome: string;
  /** Precedent this run weighed before deciding. `ok: false` is a precedent
   *  the agent looked at and declined — the evidence that memory is re-checked
   *  rather than replayed, so it is shown, not filtered out. */
  memory_checks: { text: string; ok: boolean }[];
}

/**
 * One piece of reviewed precedent: a decision a person made, written down so
 * the next run has to reckon with it.
 *
 * Only `approvals.decide()` creates these. An agent can read precedent and
 * cannot write it, which is what stops a run promoting its own conclusion
 * into guidance for the next one.
 */
export interface Playbook {
  id: string;
  title: string;
  source: string;
  proposed_by: AgentId;
  uses: string;
  status: "active" | "retired";
  status_note: string;
}

/**
 * Something an agent decided needs a person, waiting for one.
 *
 * Mirrors `Approval` in api/app/models.py. `decide()` is the only way out of
 * `pending`, and the only thing that writes precedent — so this is the row a
 * human acts on to teach the next run.
 */
export interface Approval {
  id: string;
  agent: AgentId;
  kind: "journal" | "payment" | "playbook" | "evidence" | "decision";
  title: string;
  summary: string;
  verified: boolean;
  status: "pending" | "approved" | "rejected";
  /** A journal moves money, so only an independently reviewed claim proposes one. */
  journal: { account: string; fund: string; debit_cents: number; credit_cents: number }[] | null;
  effects: { label: string; value: string; tone?: "good" | "neutral" | null }[] | null;
  /** The conclusion this would resolve, when it came from one. */
  finding_id?: string | null;
}

export interface Bundle {
  contract_version?: number;
  workspace: Workspace;
  agents: Agent[];
  briefing: Briefing;
  tasks: Task[];
  findings: Finding[];
  decisions: Decision[];
  playbooks: Playbook[];
  approvals: Approval[];
}

/** Mirrors `api/app/roles.py`. Change both together, and `contracts/` with them. */
export type SourceRole =
  | "chart" | "opening" | "ledger"
  | "vendors" | "purchase_orders" | "goods_receipts" | "vendor_invoices" | "payments"
  | "customers" | "customer_invoices" | "remittances"
  | "bank_transactions" | "processor_payouts"
  | "payroll" | "expenses"
  | "budgets" | "forecasts" | "headcount"
  | "approvals" | "period_locks" | "tax_registrations"
  | "contract" | "policy" | "document" | "invoice" | "service" | "budget";
export interface IntakeWorkspace {
  id: string; name: string; kind: "synthetic" | "public";
  entity_type: "company" | "subsidiary" | "group";
  /** Answers to the setting-kind requirements Books collects. */
  settings?: Record<string, string | number>;
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
export interface DataRequirement {
  id: string; label: string;
  /** A csv or document is uploaded; a setting is answered in a form. */
  kind: "csv" | "document" | "setting";
  role: SourceRole | null; setting: string | null;
  control: "text" | "money" | "integer" | "date" | "month_day" | null;
  optional: boolean; satisfied: boolean;
  /** One line: what supplying this makes possible. */
  unlocks: string;
  /** Registry ids of the agents waiting on it. */
  needed_by: string[];
  /** Requirement ids worth supplying first. Ordering only, never enforcement. */
  after: string[];
  value: string | number | null;
}

/**
 * One committed file, as the coverage listing reports it.
 *
 * `source_system` and `external_id` are the provenance the server writes when a
 * file is staged from a reviewed document: system `reviewed-extraction` and the
 * document's lineage id. Files joins a file to its document with those two
 * fields alone, so listing every upload costs one request rather than one per
 * file. A file uploaded directly carries an empty `external_id` and is joined
 * to nothing, which is the honest answer for it.
 */
export interface CoverageSource {
  id: string; name: string; sha256: string; role: SourceRole; active: boolean;
  source_system: string; external_id: string; source_version: number;
  /** When the batch that carried this file in was created. */
  uploaded_at: string;
  /** Live records still drawn from this file. Zero means superseded, not deleted. */
  record_count: number;
}
export interface Coverage {
  workspace: IntakeWorkspace; snapshot: { id: string; revision: number; created_at: string } | null;
  counts: Record<string, number>;
  /** What the agents need from this workspace. Mirrors `api/app/requirements.py`,
   *  which is the only place that decides it, so Books cannot ask for something no
   *  agent reads or stay silent about something an agent depends on. */
  requirements: DataRequirement[];
  /** Agent id -> the requirement ids still blocking it. */
  blocked_agents: Record<string, string[]>;
  satisfied_count: number; required_count: number;
  sources: CoverageSource[];
  requests: EvidenceRequest[]; coverage_verified: boolean; note: string;
}
export interface SourceDetail {
  id: string; name: string; sha256: string; committed: boolean; options: SourceOptions;
  line_count: number; lines: { number: number; text: string }[];
  /** Set when this source was staged from a reviewed document extraction, so the
   *  preserved original can be opened beside the text that was derived from it. */
  extraction_origin?: {
    document_id: string; name: string; sha256: string;
    correction_id: string; has_images: boolean; pages: number[];
  } | null;
}
/** Mirrors `api/app/agents/registry.py` and `api/app/agents/api.py`.
 *  The standalone triage agent it replaced is gone; a run is now one registry agent
 *  against a bounded task, and it always reports what it cost. */
export interface AgentNode {
  id: string; name: string; tier: "orchestrator" | "worker" | "subagent";
  parent: string | null; charter: string; model: string;
  /** False when the work is deterministic and the model only judges exceptions. */
  uses_model_in_hot_path: boolean;
  reads: SourceRole[]; reviewer: string | null;
  /** Requirement labels still missing. Empty means ready. */
  blocked_by: string[]; ready: boolean;
  budget: { model_calls: number; tool_calls: number; usd_cents: number };
  escalates_when: {
    confidence_below: number; amount_above_cents: number | null; conditions: string[];
  };
  children: string[];
}

export interface AgentOrganization {
  agents: AgentNode[];
  spend: { today_cents: number; day_cap_cents: number; run_cap_cents: number };
  note: string;
}

export interface AgentRunResult {
  thread_id: string; agent_id: string; agent_name: string;
  result: {
    summary: string;
    disposition: "clear" | "exception" | "insufficient_evidence";
    rationale: string;
    citations: { role: string; record_key: string; source_id: string; line: number | null; note: string }[];
    exceptions: { code: string; detail: string }[];
    proposed_action: string; open_questions: string[];
  } | null;
  /** Computed from the match rubric, never asserted by the model. Null when no
   *  deterministic calculation ran, which is reported rather than defaulted. */
  confidence: number | null;
  escalated: boolean; escalation_reasons: string[];
  decision_id: string; cost_cents: number;
  model_calls: number; tool_calls: number;
  spend: { spent_cents: number; cap_cents: number; remaining_cents: number };
}

/**
 * The orchestrator conversation.
 *
 * A turn is recorded before its run starts and updated when it ends, so a `running` or
 * `failed` turn is a real state the screen has to render — not a transient one it can
 * assume away.
 */
export interface ChatTurn {
  id: string;
  /** Groups the exchange. Continuing a conversation passes this. */
  thread_id: string;
  /** The one investigation this turn started. A decision is addressed to this, never
   *  to the conversation: only one run is paused on the question. */
  run_id: string;
  role: "person" | "orchestrator";
  status: "sent" | "running" | "done" | "waiting_on_you" | "failed";
  created_at: string;
  body: ChatReply & { text: string; code?: string };
}

export interface ChatReply {
  text: string;
  plan?: string[];
  routed_to?: string[];
  findings?: {
    agent_id: string; agent_name: string; summary: string;
    /** Computed by the engine. Null when nothing scored ran, which is reported
     *  rather than defaulted to a number nobody derived. */
    confidence: number | null;
    escalated: boolean; decision_id?: string;
  }[];
  escalations?: Escalation[];
  /** Absent unless the sentence asked for one. Nothing is produced on its own. */
  deliverable?: { id: string; kind: string; title: string } | null;
  unresolved?: string[];
  status?: string;
  run_id?: string;
  spend?: { spent_cents: number; cap_cents: number; remaining_cents: number };
  note?: string;
}

/** One question a run stopped on. Answered by id: several agents can pause at once. */
export interface Escalation {
  approval_id: string;
  /** The id to address and the name to show. A bare id renders as "B4" to a reader who
   *  has no idea what B4 is, so both endpoints that carry an escalation send both. */
  agent: { id: string; name: string };
  title?: string;
  summary?: string;
  reasons?: string[];
  confidence?: number | null;
  decision_id?: string;
  thread_id?: string;
  interrupt_id?: string | null;
}

/** One economic event: the transaction, not any single document of it. */
export interface TimelineEvent {
  id: string; kind: string; title: string; occurred_on: string;
  period: string; status: string; record_count: number;
}

export interface EventDetail {
  event: TimelineEvent;
  roles: string[];
  records: { role: string; record_key: string; source_id: string; line: number }[];
  /** `method` separates an exact reference match from a fuzzy or inferred one, which is
   *  the difference a reviewer most needs to see. */
  links: { from_type: string; from_id: string; to_type: string; to_id: string;
           kind: string; method: string; confidence: number }[];
  decisions: { id: string; agent: string; action: string; summary: string;
               confidence: number | null; escalated: number; created_at: string }[];
}

/**
 * The period on one page. Computed in integer cents by `accounting/`; the renderer
 * formats and writes nothing, which is what makes a PDF of it defensible.
 */
export interface PeriodSnapshot {
  workspace: { name: string; start: string; end: string; period: string;
               jurisdiction: string; currency: string };
  snapshot_id: string | null;
  prepared_at: string;
  records: number;
  result: { revenue_cents: number; expense_cents: number; net_cents: number;
            expense_by_category_cents: Record<string, number> };
  position: { assets_cents: number; liabilities_cents: number; equity_cents: number;
              opening_cash_cents: number; closing_cash_cents: number };
  /** The identities that decide whether the figures above may be shown at all. */
  checks: { trial_balance_balances: boolean; balance_sheet_balances: boolean;
            balance_sheet_difference_cents: number; cash_flow_ties: boolean;
            reliable: boolean; problems: string[] };
  close: { ready: boolean; blocked_by: string[]; counts: Record<string, number>;
           items: { id: string; title: string; state: string; detail: string;
                    blocking: boolean }[] };
  controls: { exceptions: { id: string; title: string; amount_cents: number | null;
                            records: string[]; action: string }[];
              exception_count: number; passed: string[]; pass_count: number;
              gap_count: number; omitted: number };
  variance: { lines: { account: string; name: string; planned_cents: number;
                       actual_cents: number; variance_cents: number;
                       favourable: boolean }[];
              line_count: number; omitted: number;
              expense_planned_cents: number; expense_actual_cents: number;
              unplanned: { account: string; name: string }[] };
  accruals: { count: number; total_cents: number };
  bank: { bank_lines: number; matched: number; unmatched_bank: number;
          unmatched_book: number; differing: number } | null;
  limitations: string[];
}

/** A document someone asked for, frozen at the moment they asked. */
export interface DeliverableRow {
  id: string; kind: string; kind_label: string; title: string;
  requested_by: string; thread_id: string; snapshot_id: string | null;
  created_at: string;
  /** Drawn from records since superseded: historical rather than wrong. */
  stale: boolean;
}

export interface Deliverable extends DeliverableRow {
  /** Frozen at creation, never recomputed on read: a document that changes when you
   *  reopen it is not a document. */
  payload: PeriodSnapshot;
}
