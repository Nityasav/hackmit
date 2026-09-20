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
  ["Add the company", "Enter the company and review period."],
  ["Add the records", "Upload the files for this review."],
  ["Check the import", "Confirm columns and resolve flagged rows."],
  ["Commit the records", "Save the validated records for review."],
  ["Run the investigation", "Set the scope and start the agents."],
  ["Review the briefing", "Read the findings and export the report."],
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
      title: "Add an institution",
      detail: "Enter its name, currency and review period.",
      action: "create",
      actionLabel: "Add a company",
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
        detail: "Validation passed. Commit the import to make it available for review.",
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
        : "Confirm the column mappings before committing.",
      action: "import",
      actionLabel: "Open the import",
      steps: withCurrent(2),
    };
  }

  if ((intake?.selectedFileCount ?? 0) > 0) {
    return {
      eyebrow: "Step 3 of 6",
      title: "Check how the files were read",
      detail: "Preview the selected files and check their column mappings.",
      action: "records",
      actionLabel: "Preview the staged files",
      steps: withCurrent(2),
    };
  }

  if (!hasSnapshot) {
    return {
      eyebrow: "Step 2 of 6",
      title: "Add this company's records",
      detail: "Upload CSV, text or Markdown files to begin.",
      action: "records",
      actionLabel: "Add records",
      steps: withCurrent(1),
    };
  }

  if (running) {
    return {
      eyebrow: "Step 5 of 6",
      title: "The agents are working",
      detail: "Open Investigation for progress and results.",
      action: "investigation",
      actionLabel: "Watch the investigation",
      steps: withCurrent(4),
    };
  }

  if (findings === 0) {
    return {
      eyebrow: "Step 5 of 6",
      title: "Run the investigation",
      detail: "Set a review question and start the agents. API charges apply.",
      action: "investigation",
      actionLabel: "Start the investigation",
      steps: withCurrent(4),
    };
  }

  return {
    eyebrow: "Step 6 of 6",
    title: "Review the briefing",
    detail: `${findings} ${findings === 1 ? "finding is" : "findings are"} ready to read. Open the briefing to review and export the results.`,
    action: "briefing",
    actionLabel: "Open the briefing",
    steps: withCurrent(5),
  };
}
