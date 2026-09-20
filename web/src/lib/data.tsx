"use client";

import { useCallback, useEffect, useMemo } from "react";

import { track } from "@/lib/activity";
import { useActiveBundle, useDashboardStore, type BundleSource } from "@/lib/store";
import type { ApprovalStatus, Bundle, IntakeWorkspace } from "@/lib/types";

export { API_URL, intakeApi } from "@/lib/api";

/**
 * The store is the state; this hook is the shape the components already use.
 * Keeping the old surface means the move to Zustand did not ripple through
 * every page.
 */
interface DashboardApi {
  ws: string;
  setWs: (ws: string) => void;
  bundle: Bundle;
  source: BundleSource;
  apiError: string | null;
  loading: boolean;
  intakeWorkspaces: IntakeWorkspace[];
  refreshWorkspaces: () => Promise<void>;
  refreshBundle: () => Promise<void>;
  decideApproval: (id: string, decision: Exclude<ApprovalStatus, "pending">) => void;
}

/** Fetches the workspace list once, then the active bundle whenever it changes. */
export function DataProvider({ children }: { children: React.ReactNode }) {
  const ready = useDashboardStore((s) => s.ready);
  const workspaceId = useDashboardStore((s) => s.workspaceId);
  const loadWorkspaceList = useDashboardStore((s) => s.loadWorkspaceList);
  const loadIntakeWorkspaces = useDashboardStore((s) => s.loadIntakeWorkspaces);
  const loadBundle = useDashboardStore((s) => s.loadBundle);
  const sourceFor = useDashboardStore((s) => s.sourceFor);

  useEffect(() => {
    void loadWorkspaceList();
    void loadIntakeWorkspaces();
  }, [loadWorkspaceList, loadIntakeWorkspaces]);

  useEffect(() => {
    if (!ready) return;
    void loadBundle(workspaceId);

    // Uploaded records change while an import runs, so that source is polled.
    // Database workspaces only change when someone decides an approval, and
    // that refreshes in place.
    if (sourceFor(workspaceId) !== "api") return;
    const interval = setInterval(() => void loadBundle(workspaceId), 2000);
    return () => clearInterval(interval);
  }, [ready, workspaceId, loadBundle, sourceFor]);

  if (!ready) {
    return <p className="p-6 text-[14px] text-ink-dim">Loading workspace…</p>;
  }
  return <>{children}</>;
}

export function useData(): DashboardApi {
  const bundle = useActiveBundle();
  const ws = useDashboardStore((s) => s.workspaceId);
  const apiError = useDashboardStore((s) => s.error);
  const loading = useDashboardStore((s) => s.loading);
  const intakeWorkspaces = useDashboardStore((s) => s.intakeWorkspaces);
  const setWorkspace = useDashboardStore((s) => s.setWorkspace);
  const loadBundle = useDashboardStore((s) => s.loadBundle);
  const loadIntakeWorkspaces = useDashboardStore((s) => s.loadIntakeWorkspaces);
  const decide = useDashboardStore((s) => s.decideApproval);
  const sourceFor = useDashboardStore((s) => s.sourceFor);

  const setWs = useCallback((next: string) => {
    setWorkspace(next);
    void track("workspace_switch", { workspaceId: next, target: next });
  }, [setWorkspace]);

  const decideApproval = useCallback((id: string, decision: Exclude<ApprovalStatus, "pending">) => {
    void decide(id, decision);
    void track("approval_decision", { workspaceId: ws, target: id, metadata: { decision } });
  }, [decide, ws]);

  const refreshBundle = useCallback(() => loadBundle(ws), [loadBundle, ws]);

  return useMemo(() => ({
    ws, setWs, bundle, source: sourceFor(ws), apiError, loading,
    intakeWorkspaces, refreshWorkspaces: loadIntakeWorkspaces, refreshBundle, decideApproval,
  }), [ws, setWs, bundle, sourceFor, apiError, loading, intakeWorkspaces, loadIntakeWorkspaces, refreshBundle, decideApproval]);
}
