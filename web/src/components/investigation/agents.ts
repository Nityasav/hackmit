import type { AgentId } from "@/lib/types";
import type { CFORun, RunEvent, TaskStatus } from "./run";

/**
 * What each agent does and how it does it, in words a ten-year-old can read.
 *
 * Every sentence here describes behaviour that exists in api/app/agents and
 * api/app/cfo. Nothing is aspirational. If the code stops doing it, the
 * sentence comes out.
 */
export interface AgentProfile {
  id: AgentId;
  name: string;
  /** The beat this agent covers, with any short name spelled out. */
  beat: string;
  /** What it does. */
  does: string;
  /** How it does it, including what stops it making things up. */
  how: string;
}

export const TEAM: readonly AgentProfile[] = [
  {
    id: "cfo",
    name: "CFO Agent",
    beat: "Planning & reporting",
    does:
      "Sets the review plan, assigns specialist tasks and prepares the briefing.",
    how:
      "Uses a committed snapshot and reports accepted findings alongside unresolved questions.",
  },
  {
    id: "ap",
    name: "AP & Payments",
    beat: "Invoices & purchase support",
    does:
      "Checks for duplicate invoices and missing purchase or receipt evidence.",
    how:
      "Reviews assigned records and flags missing support for follow-up.",
  },
  {
    id: "py",
    name: "Payroll & Budget",
    beat: "Payroll & spending",
    does:
      "Checks payroll totals, budget variances and charges allocated to restricted funds.",
    how:
      "Uses accounting calculations from the uploaded records to support amounts.",
  },
  {
    id: "gr",
    name: "Grants & Compliance",
    beat: "Award terms & expenditure",
    does:
      "Compares supplied charges with award terms, dates and funding limits.",
    how:
      "Cites uploaded terms and requests evidence where eligibility is unclear.",
  },
  {
    id: "au",
    name: "Internal Auditor",
    beat: "Independent review",
    does:
      "Checks specialist claims against the originals and repeats supporting calculations.",
    how:
      "Accepts supported claims, rejects unsupported claims or requests more evidence.",
  },
];

/** The most trust-building fact in the product, in one sentence. */
export const CROSS_CHECK =
  "Human approval remains separate from the Auditor’s review.";

/** The four beats of a run, for the line above the team. */
export const FLOW = [
  "The CFO plans",
  "Specialists investigate",
  "Auditor reviews",
  "CFO reports",
];

/** What a run actually does, shown before anyone has started one. */
export const WHAT_HAPPENS = [
  "The review uses your latest committed records.",
  "The CFO assigns tasks to AP, Payroll and Grants.",
  "Specialists review their assigned sources and cite findings.",
  "The Auditor checks the evidence and calculations.",
  "The CFO reports accepted findings and unresolved questions.",
];

const ROLE: Record<string, AgentId> = { cfo: "cfo", ap: "ap", py: "py", gr: "gr", au: "au" };

/** The agent a run event or task belongs to, or null if the service names one we do not know. */
export function agentOf(role: string): AgentId | null {
  return ROLE[role] ?? null;
}

const PHRASE: Record<string, string> = {
  "snapshot.started": "Pinning this company's records",
  "plan.started": "Writing the plan",
  "plan.completed": "Finished the plan",
  "plan.accepted": "Set the plan",
  "plan.coverage_added": "Added a missing area to the plan",
  delegate: "Handed a job to a specialist",
  "read_source.started": "Opening one of your files",
  "read_source.completed": "Read one of your files",
  "calculate.started": "Running a calculation",
  "calculate.completed": "Finished a calculation",
  "result.submitted": "Handed in what it found",
  "review.requested": "Asked the Auditor to re-check a claim",
  "review.accept": "Accepted a claim",
  "review.reject": "Rejected a claim",
  "review.needs_evidence": "Asked for more proof",
  "follow_up.started": "Deciding what to do about a challenge",
  "follow_up.completed": "Decided what to do about a challenge",
  "synthesize.started": "Writing the report",
  "synthesize.completed": "Finished the report",
  "synthesis.fallback": "Kept the plain report instead of the written one",
  "report.published": "Published the report",
  "task.blocked": "A job is waiting on another one",
  "task.finished": "A job finished",
  "task.failed": "A job stopped",
  "run.failed": "The run stopped",
  "run.interrupted": "The run was interrupted",
};

/** One plain phrase for a step the service recorded. Unknown steps keep their own name. */
export function describeStep(action: string): string {
  return PHRASE[action] ?? action.replaceAll("_", " ").replaceAll(".", " · ");
}

export type StateTone = "live" | "wait" | "done" | "stop" | "idle";

export interface AgentState {
  /** Two or three words: what this agent is right now. */
  label: string;
  tone: StateTone;
  /** One line about what it is doing, taken from the run. */
  detail: string;
}

const IDLE: AgentState = {
  label: "Not started",
  tone: "idle",
  detail: "This agent starts when you start an investigation.",
};

const TASK_STATE: Record<TaskStatus, { label: string; tone: StateTone; detail: string }> = {
  queued: { label: "Waiting its turn", tone: "wait", detail: "It has a job and has not started it yet." },
  working: { label: "Working", tone: "live", detail: "Reading the files named in its job." },
  auditor_review: { label: "With the Auditor", tone: "wait", detail: "Its claim is being re-checked by the Internal Auditor." },
  done: { label: "Finished", tone: "done", detail: "It finished its job." },
  needs_evidence: { label: "Needs more proof", tone: "stop", detail: "It stopped and asked for paperwork it could not find." },
  failed: { label: "Stopped", tone: "stop", detail: "Its job stopped without a conclusion." },
  blocked: { label: "Blocked", tone: "wait", detail: "It is waiting on another agent's job." },
};

/** The plain label and tone for one delegated job. */
export function taskState(status: TaskStatus): { label: string; tone: StateTone } {
  const state = TASK_STATE[status];
  return { label: state.label, tone: state.tone };
}

/** The task a specialist is most alive in: what it is doing beats what it has finished. */
const TASK_ORDER: TaskStatus[] = ["working", "auditor_review", "needs_evidence", "failed", "blocked", "queued", "done"];

function lastEvent(run: CFORun, actor: AgentId): RunEvent | null {
  for (let i = run.events.length - 1; i >= 0; i -= 1) {
    if (run.events[i].actor === actor) return run.events[i];
  }
  return null;
}

function cfoState(run: CFORun): AgentState {
  const step = lastEvent(run, "cfo");
  const detail = step ? describeStep(step.action) + "." : "Getting ready.";
  if (run.status === "queued") return { label: "Starting", tone: "wait", detail: "The run is queued." };
  if (run.status === "planning") return { label: "Planning", tone: "live", detail };
  if (run.status === "running") return { label: "Working", tone: "live", detail };
  if (run.status === "completed") return { label: "Finished", tone: "done", detail: "It wrote up what the Auditor accepted." };
  if (run.status === "partial" || run.status === "needs_evidence")
    return { label: "Finished with gaps", tone: "stop", detail: "It wrote up what it could, and listed the rest as unresolved." };
  if (run.status === "stale")
    return { label: "Out of date", tone: "stop", detail: "The records changed during the run, so its conclusions were dropped." };
  return { label: "Stopped", tone: "stop", detail: detail };
}

function specialistState(run: CFORun, id: AgentId): AgentState {
  const mine = run.tasks.filter((task) => task.spec.role === id);
  if (mine.length === 0) {
    return run.plan
      ? { label: "No job this time", tone: "idle", detail: "The CFO agent did not give this agent a job in this run." }
      : { label: "Waiting for a job", tone: "wait", detail: "The CFO agent is still writing the plan." };
  }
  const task = [...mine].sort((a, b) => TASK_ORDER.indexOf(a.status) - TASK_ORDER.indexOf(b.status))[0];
  const state = TASK_STATE[task.status];
  const step = lastEvent(run, id);
  const detail = task.status === "working" && step ? describeStep(step.action) + "." : state.detail;
  return { label: state.label, tone: state.tone, detail };
}

function auditorState(run: CFORun, running: boolean): AgentState {
  const reviewing = run.tasks.find((task) => task.status === "auditor_review");
  if (reviewing) {
    const who = TEAM.find((agent) => agent.id === agentOf(reviewing.spec.role));
    return {
      label: "Re-checking",
      tone: "live",
      detail: who ? `Re-checking a claim from ${who.name}.` : "Re-checking a claim.",
    };
  }
  const checked = run.events.filter((event) => event.action.startsWith("review.") && event.actor === "au").length;
  if (checked > 0) {
    return {
      label: running ? "Between checks" : "Finished",
      tone: running ? "wait" : "done",
      detail: checked === 1 ? "It has re-checked one claim." : `It has re-checked ${checked} claims.`,
    };
  }
  if (running) return { label: "Waiting for a claim", tone: "wait", detail: "Nothing has been handed to it yet." };
  return { label: "Nothing to check", tone: "idle", detail: "No specialist produced a claim for it to re-check." };
}

/** What an agent is doing right now, taken only from the run. Never a fixed string. */
export function agentState(run: CFORun | null, running: boolean, id: AgentId): AgentState {
  if (!run) return IDLE;
  if (id === "cfo") return cfoState(run);
  if (id === "au") return auditorState(run, running);
  return specialistState(run, id);
}

/** What the run status means, in plain words, for the line under the title. */
export function describeRun(run: CFORun | null, running: boolean): string {
  if (!run) return "No investigation has run for this company yet.";
  if (running) return "The agents are working now.";
  if (run.status === "completed") return "The agents finished. Their accepted conclusions are below.";
  if (run.status === "partial" || run.status === "needs_evidence")
    return "The agents finished, and some questions are still open.";
  if (run.status === "stale") return "The records changed during the run, so its conclusions were dropped. Start again.";
  if (run.status === "interrupted") return "The run was interrupted before it finished.";
  return "The run stopped before it finished.";
}
