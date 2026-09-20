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
    beat: "Chief financial officer: the one in charge.",
    does:
      "Reads everything you uploaded, decides which parts are worth a closer look, gives each of the other four agents a job, and writes up what the team found.",
    how:
      "It works from one frozen copy of your records, so nothing can change underneath it while it works. It can read them; it cannot edit them. Before its write-up is allowed through, every claim has to point at a line in your files, and every dollar figure has to match one it actually read. If it does not, the write-up is thrown back and it starts that part again.",
  },
  {
    id: "ap",
    name: "AP & Payments",
    beat: "Accounts payable: the bills the school pays.",
    does:
      "Checks the bills. It looks for the same bill being paid twice, and for bills with no proof that anyone ordered the thing or that it ever arrived.",
    how:
      "First it names the files it wants, then it is allowed to open only those. A gate refuses anything outside the job it was given. Anything it writes that it did not actually read is dropped before you see it, and turned into a request for the missing paperwork. It may say a payment looks like a duplicate. It is not allowed to say a duplicate is confirmed.",
  },
  {
    id: "py",
    name: "Payroll & Budget",
    beat: "Pay, and the budget it is spent against.",
    does:
      "Checks the pay records: that the pay adds up, that spending matches what the budget allowed, and that pay charged to a restricted pot of money belongs there.",
    how:
      "The agent decides what to look at and what it means. The sums are done by plain arithmetic in whole cents, straight from your records, with no model involved. Every amount you see here came from that calculator. A claim with no calculation behind it is knocked down before it reaches you.",
  },
  {
    id: "gr",
    name: "Grants & Compliance",
    beat: "Grant money, and the rules attached to it.",
    does:
      "Some money may only be spent on one thing, during one stretch of time. This agent reads those rules and checks the spending against them, and says so plainly when the paperwork that would prove it is simply missing.",
    how:
      "It may only use the award letter you uploaded, never a rule it half-remembers from somewhere else. A fixed check adds up the pay charged to an award, compares it with that award's limit, and tests every date against the award's window. When the terms are missing it has to answer needs evidence. It is not allowed to call anything a violation.",
  },
  {
    id: "au",
    name: "Internal Auditor",
    beat: "The checker: reviews the other four.",
    does:
      "Double-checks the others' work. It goes back to the original paperwork, redoes the sums itself, and then says accept, reject, or show me more proof.",
    how:
      "It starts with a blank sheet: none of the other agents' reading counts as its own. To accept a claim it has to open the same lines itself and get the same number from the same calculation. If it has not done that, the acceptance fails instead of letting something through unchecked. It cannot approve anything either. Approval stays with you.",
  },
];

/** The most trust-building fact in the product, in one sentence. */
export const CROSS_CHECK =
  "The Internal Auditor is never one of the agents it reviews. The run refuses to start if it is, so no agent can mark its own work correct.";

/** The four beats of a run, for the line above the team. */
export const FLOW = [
  "The CFO plans",
  "three specialists dig",
  "the Internal Auditor re-checks",
  "the CFO writes it up",
];

/** What a run actually does, shown before anyone has started one. */
export const WHAT_HAPPENS = [
  "Your committed records are frozen into one copy the agents cannot change.",
  "The CFO agent writes a short plan and gives AP & Payments, Payroll & Budget and Grants & Compliance one job each.",
  "Each specialist opens only the files named in its job, and writes down what it found with the lines it read.",
  "The Internal Auditor re-opens those lines, redoes the sums, and accepts, rejects, or asks for more proof.",
  "The CFO agent writes up only what the Auditor accepted. Everything else is listed here as unresolved.",
];

const ROLE: Record<string, AgentId> = { cfo: "cfo", ap: "ap", py: "py", gr: "gr", au: "au" };

/** The agent a run event or task belongs to, or null if the service names one we do not know. */
export function agentOf(role: string): AgentId | null {
  return ROLE[role] ?? null;
}

const PHRASE: Record<string, string> = {
  "snapshot.started": "Pinning this school's records",
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
  if (!run) return "No investigation has run for this school yet.";
  if (running) return "The agents are working now.";
  if (run.status === "completed") return "The agents finished. Their accepted conclusions are below.";
  if (run.status === "partial" || run.status === "needs_evidence")
    return "The agents finished, and some questions are still open.";
  if (run.status === "stale") return "The records changed during the run, so its conclusions were dropped. Start again.";
  if (run.status === "interrupted") return "The run was interrupted before it finished.";
  return "The run stopped before it finished.";
}
