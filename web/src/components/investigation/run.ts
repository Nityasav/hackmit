"use client";

import { useCallback, useEffect, useState } from "react";

import { CFO_API_URL, cfoRequest, cfoRequestOptional, isAbort } from "@/lib/api";

/**
 * The live five-agent run, as the CFO service returns it.
 *
 * These shapes mirror api/app/cfo/schemas.py. Only the fields this screen
 * actually renders are declared: everything on screen has to come from here,
 * so an undeclared field is a field nobody is allowed to display.
 */

export type RunStatus =
  | "queued" | "planning" | "running" | "completed"
  | "needs_evidence" | "partial" | "failed" | "stale" | "interrupted";

export type TaskStatus =
  | "queued" | "working" | "auditor_review" | "done" | "needs_evidence" | "failed" | "blocked";

export type Verdict = "accept" | "reject" | "needs_evidence";

export interface RunSource {
  id: string;
  title: string;
  locator: string;
}

export interface RunCalculation {
  id: string;
  amount_cents: number;
  cash_delta_cents: number;
  category: "reclassification" | "exposure" | "potential_recovery" | "none";
  description: string;
}

export interface RunClaim {
  id: string;
  title: string;
  conclusion: string;
  disposition: "substantiated" | "cleared" | "explained";
  evidence_ids: string[];
  proposed_action: string;
}

export interface AcceptedClaim {
  task_id: string;
  role: string;
  claim: RunClaim;
  review: { verdict: Verdict; rationale: string; required_action: string };
  calculation: RunCalculation | null;
}

export interface RunTask {
  spec: { id: string; role: string; objective: string; depends_on: string[] };
  status: TaskStatus;
  attempts: number;
}

export interface RunEvent {
  at: string;
  actor: string;
  action: string;
  detail: string;
  task_id: string | null;
}

export interface CFORun {
  id: string;
  request: { workspace: string; objective: string };
  status: RunStatus;
  model_label: string;
  model_calls: number;
  tool_calls: number;
  briefing: string;
  report_markdown: string;
  unresolved: string[];
  scope: { snapshot_id: string; institution: string; period: string; sources: RunSource[]; gaps: string[] } | null;
  plan: { rationale: string } | null;
  tasks: RunTask[];
  accepted: AcceptedClaim[];
  events: RunEvent[];
}

const ACTIVE: ReadonlySet<RunStatus> = new Set<RunStatus>(["queued", "planning", "running"]);

/** True while the agents are still working, which is also when the run is polled. */
export function isRunning(run: CFORun | null): run is CFORun {
  return !!run && ACTIVE.has(run.status);
}

export interface Investigation {
  run: CFORun | null;
  running: boolean;
  starting: boolean;
  error: string | null;
  /** The agent service has an address to call. */
  connected: boolean;
  /** This school exists and can be investigated. */
  ready: boolean;
  start: (objective: string) => Promise<void>;
}

function reason(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

/**
 * One run per school: the last one is loaded on arrival, and a new one is
 * polled while the agents work. There is no fixture path — a run is live or
 * it does not start.
 */
export function useInvestigation(ws: string): Investigation {
  const [run, setRun] = useState<CFORun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const runId = run?.id;
  const running = isRunning(run);

  // The last run for this school, so a reload continues where you were.
  useEffect(() => {
    if (!CFO_API_URL || !ws) return;
    const controller = new AbortController();
    void cfoRequestOptional<CFORun>(`/api/cfo/workspaces/${encodeURIComponent(ws)}/latest`, { signal: controller.signal })
      .then((latest) => {
        if (!latest || controller.signal.aborted || latest.request.workspace !== ws) return;
        setRun((current) => current ?? latest);
      })
      .catch((e) => {
        if (!isAbort(e)) setError(reason(e, "The last investigation could not be loaded."));
      });
    return () => controller.abort();
  }, [ws]);

  // While agents are working, the run is polled rather than waited on.
  useEffect(() => {
    if (!CFO_API_URL || !runId || !running) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const next = await cfoRequest<CFORun>(`/api/cfo/runs/${encodeURIComponent(runId)}`, { signal: controller.signal });
        if (!controller.signal.aborted) {
          setRun(next);
          setError(null);
        }
      } catch (e) {
        if (!controller.signal.aborted && !isAbort(e)) setError(reason(e, "The investigation could not be refreshed."));
      }
      if (!controller.signal.aborted) timer = setTimeout(() => void poll(), 1500);
    };

    void poll();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [runId, running]);

  const start = useCallback(async (objective: string) => {
    setStarting(true);
    setError(null);
    try {
      setRun(await cfoRequest<CFORun>("/api/cfo/runs", {
        method: "POST",
        body: { workspace: ws, objective, mode: "live", workflow: "five_agent" },
      }));
    } catch (e) {
      setError(reason(e, "The investigation could not be started."));
    } finally {
      setStarting(false);
    }
  }, [ws]);

  return { run, running, starting, error, connected: !!CFO_API_URL, ready: ws.startsWith("ws-"), start };
}
