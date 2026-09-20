import type { Bundle } from "./types";

/**
 * Where someone is in the one workflow this product has:
 * Books → Investigation → Briefing.
 *
 * The step is derived, never stored. Every signal below is either live intake
 * state reported by the records panel or a value already in the bundle, so the
 * guide can never claim progress that did not happen.
 */

/** What the records panel on Books knows that the bundle does not. */
export interface IntakeUiProgress {
  loaded: boolean;
  selectedFileCount: number;
  batchStatus: string | null;
  batchIssues: number;
  hasSnapshot: boolean;
  runRunning: boolean;
}

/**
 * Where the step's button goes. The three route actions are the three
 * destinations; the rest scroll to a section of Books.
 */
export type WorkflowAction = "create" | "records" | "import" | "investigation" | "briefing";

export interface WorkflowStep {
  label: string;
  detail: string;
  state: "done" | "current" | "upcoming";
}

export interface GuidedWorkflow {
  eyebrow: string;
  title: string;
  detail: string;
  action: WorkflowAction;
  actionLabel: string;
  steps: WorkflowStep[];
}

const STEPS = [
  ["Add the school", "Name it and set the months you are looking at."],
  ["Add the records", "Choose files, or stage the fictional sample pack."],
  ["Check the import", "See how each file was read, and fix anything flagged."],
  ["Commit the records", "Save one fixed set of records for the agents to work from."],
  ["Run the investigation", "Five agents read the records and cite every line."],
  ["Hand over the briefing", "Take the write-up to whoever asked for it."],
] as const;

function withCurrent(current: number): WorkflowStep[] {
  return STEPS.map(([label, detail], index) => ({
    label,
    detail,
    state: index < current ? "done" : index === current ? "current" : "upcoming",
  }));
}

export function deriveGuidedWorkflow(bundle: Bundle, intake?: IntakeUiProgress | null): GuidedWorkflow {
  const { workspace } = bundle;

  if (!workspace.id) {
    return {
      eyebrow: "Step 1 of 6",
      title: "Add the school you are reviewing",
      detail: "Nothing exists until you create one. Give it a name and the period its records cover.",
      action: "create",
      actionLabel: "Add a school",
      steps: withCurrent(0),
    };
  }

  // The bundle says whether a snapshot exists; the panel knows sooner, because
  // it has just committed one. Either is enough.
  const hasSnapshot = Boolean(intake?.hasSnapshot) || workspace.mode === "live";
  const batchStatus = intake?.batchStatus ?? null;
  const findings = bundle.findings.length;
  const running = Boolean(intake?.runRunning) || bundle.agents.some((agent) => agent.status === "working");

  if (batchStatus && batchStatus !== "committed") {
    const issues = intake?.batchIssues ?? 0;
    if (batchStatus === "ready_to_commit") {
      return {
        eyebrow: "Step 4 of 6",
        title: "Commit the records",
        detail: "The import checked out. Committing saves one fixed set of records; the agents only ever read a committed set.",
        action: "import",
        actionLabel: "Go to the import",
        steps: withCurrent(3),
      };
    }
    return {
      eyebrow: "Step 3 of 6",
      title: issues ? `Fix ${issues} flagged ${issues === 1 ? "row" : "rows"}` : "Check how the files were read",
      detail: issues
        ? "Open each flagged row against its original line and correct the mapping, then check it again."
        : "Look at how every column was understood before any of it is committed.",
      action: "import",
      actionLabel: "Open the import",
      steps: withCurrent(2),
    };
  }

  if ((intake?.selectedFileCount ?? 0) > 0) {
    return {
      eyebrow: "Step 3 of 6",
      title: "Check how the files were read",
      detail: "The files are staged and nothing has been saved yet. Preview them to see how each column was understood.",
      action: "records",
      actionLabel: "Preview the staged files",
      steps: withCurrent(2),
    };
  }

  if (!hasSnapshot) {
    return {
      eyebrow: "Step 2 of 6",
      title: "Add this school's records",
      detail: "Upload CSV, text or Markdown files — or stage the fictional sample pack. Nothing is saved until you preview it.",
      action: "records",
      actionLabel: "Add records",
      steps: withCurrent(1),
    };
  }

  if (running) {
    return {
      eyebrow: "Step 5 of 6",
      title: "The agents are working",
      detail: "Follow them on Investigation. Each one says what it is doing and points at the line it is reading.",
      action: "investigation",
      actionLabel: "Watch the investigation",
      steps: withCurrent(4),
    };
  }

  if (findings === 0) {
    return {
      eyebrow: "Step 5 of 6",
      title: "Run the investigation",
      detail: "Ask the agents a question in your own words. They read the committed records and make paid model calls only when you press start.",
      action: "investigation",
      actionLabel: "Start the investigation",
      steps: withCurrent(4),
    };
  }

  return {
    eyebrow: "Step 6 of 6",
    title: "Hand over the briefing",
    detail: `${findings} ${findings === 1 ? "finding is" : "findings are"} ready to read. The briefing is written from the records committed here and the decisions recorded against them.`,
    action: "briefing",
    actionLabel: "Open the briefing",
    steps: withCurrent(5),
  };
}
