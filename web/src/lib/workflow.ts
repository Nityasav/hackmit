import type { Bundle } from "./types";

export interface IntakeUiProgress {
  loaded: boolean;
  selectedFileCount: number;
  batchStatus: string | null;
  batchIssues: number;
  hasSnapshot: boolean;
  completedRunCount: number;
  runRunning: boolean;
}

export type WorkflowAction = "create" | "records" | "import" | "run" | "findings" | "approvals" | "report";

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

const LIVE_STEPS = [
  ["Create institution", "Set the reporting period and data type."],
  ["Add records", "Choose files or stage the fictional starter pack."],
  ["Validate import", "Review mappings, totals, and validation issues."],
  ["Commit snapshot", "Save an immutable set of validated records."],
  ["Run investigation", "Choose one agent or the coordinated five-agent workflow."],
  ["Review outputs", "Inspect evidence, findings, and any proposals needing a decision."],
  ["Read report", "Open the briefing built from the current workspace state."],
] as const;

function withCurrent(current: number): WorkflowStep[] {
  return LIVE_STEPS.map(([label, detail], index) => ({
    label,
    detail,
    state: index < current ? "done" : index === current ? "current" : "upcoming",
  }));
}

export function deriveGuidedWorkflow(bundle: Bundle, intake?: IntakeUiProgress | null): GuidedWorkflow {
  if (!bundle.workspace.intake) {
    return {
      eyebrow: "Recorded example",
      title: "Explore a completed investigation",
      detail: "This workspace is a saved example. Browse its findings and reasoning, or create an institution to test the live intake flow with fictional records.",
      action: "findings",
      actionLabel: "Explore recorded findings",
      steps: [
        { label: "Review the briefing", detail: "See the CFO summary and close status.", state: "done" },
        { label: "Trace the evidence", detail: "Open findings and their source citations.", state: "current" },
        { label: "Test it yourself", detail: "Create an institution and use the fictional starter pack.", state: "upcoming" },
      ],
    };
  }

  const hasSnapshot = intake
    ? Boolean(intake.hasSnapshot || intake.batchStatus === "committed")
    : !bundle.workspace.snapshot_id.startsWith("No ");
  const hasReport = Boolean(bundle.report.markdown || bundle.report.sections.length > 0);
  const hasRun = (intake?.completedRunCount ?? 0) > 0 || bundle.findings.length > 0 || hasReport;
  const runRunning = Boolean(intake?.runRunning) || bundle.workflows.some((workflow) => workflow.stages.some((stage) => stage.state === "running"));
  const pending = bundle.approvals.filter((approval) => approval.status === "pending").length;
  const hasSelectedFiles = (intake?.selectedFileCount ?? 0) > 0;
  const batchStatus = intake?.batchStatus ?? null;

  if (batchStatus && batchStatus !== "committed") {
    const issues = intake?.batchIssues ?? 0;
    if (batchStatus === "ready_to_commit") {
      return { eyebrow: "Step 4 of 7", title: "Commit the validated snapshot", detail: "The import is ready. Confirm it to create the immutable snapshot agents can investigate.", action: "import", actionLabel: "Commit records", steps: withCurrent(3) };
    }
    return { eyebrow: "Step 3 of 7", title: issues ? `Resolve ${issues} validation issue${issues === 1 ? "" : "s"}` : "Preview and validate the import", detail: issues ? "Open the flagged source rows, adjust mappings, then revalidate." : "Review how each selected source will be interpreted before committing it.", action: "import", actionLabel: "Review the import", steps: withCurrent(2) };
  }
  if (hasSelectedFiles) {
    return { eyebrow: "Step 3 of 7", title: "Preview and validate the import", detail: "Preview the selected files and verify how each source will be interpreted.", action: "records", actionLabel: "Preview selected records", steps: withCurrent(2) };
  }
  if (!hasSnapshot) {
    return { eyebrow: "Step 2 of 7", title: "Add records", detail: "For the quickest test, stage the fictional starter pack below. Nothing is uploaded until you preview it.", action: "records", actionLabel: "Go to record intake", steps: withCurrent(1) };
  }
  if (!hasRun || runRunning) {
    return { eyebrow: "Step 5 of 7", title: runRunning ? "Investigation in progress" : "Run an investigation", detail: runRunning ? "The agents are working from the committed snapshot. Follow the run or wait for the workspace to refresh." : "Choose a focused agent or the coordinated five-agent workflow. A model call only starts when you press Run.", action: "run", actionLabel: runRunning ? "Follow the investigation" : "Choose an agent", steps: withCurrent(4) };
  }
  const hasUnreviewedFindings = bundle.findings.some((finding) => !finding.verified_by && finding.status !== "cleared" && finding.status !== "explained");
  if (pending > 0 || hasUnreviewedFindings || !hasReport) {
    return { eyebrow: "Step 6 of 7", title: pending > 0 ? `Review ${pending} proposal${pending === 1 ? "" : "s"} needing a decision` : "Review the investigation output", detail: "Check each claim against its cited source. Findings are candidate analysis until a person reviews them.", action: pending > 0 ? "approvals" : "findings", actionLabel: pending > 0 ? "Review proposals" : "Review findings", steps: withCurrent(5) };
  }
  return { eyebrow: "Step 7 of 7", title: "Read the current report", detail: "The report reflects the current snapshot and recorded decisions. Return to findings whenever you need to trace a claim.", action: "report", actionLabel: "Open report", steps: withCurrent(6) };
}
