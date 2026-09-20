"use client";

import { useCallback, useEffect, useMemo } from "react";

import { track } from "@/lib/activity";
import { useActiveBundle, useDashboardStore } from "@/lib/store";
import type { Bundle, IntakeWorkspace } from "@/lib/types";

export { API_URL, intakeApi } from "@/lib/api";

/**
 * The store is the state; this hook is the shape the components already use.
 */
interface DashboardApi {
  ws: string;
  setWs: (ws: string) => void;
  bundle: Bundle;
  apiError: string | null;
  loading: boolean;
  intakeWorkspaces: IntakeWorkspace[];
  refreshWorkspaces: () => Promise<void>;
  refreshBundle: () => Promise<void>;
}

/** Fetches the workspace list once, then the active bundle whenever it changes. */
export function DataProvider({ children }: { children: React.ReactNode }) {
  const ready = useDashboardStore((s) => s.ready);
  const workspaceId = useDashboardStore((s) => s.workspaceId);
  const loadIntakeWorkspaces = useDashboardStore((s) => s.loadIntakeWorkspaces);
  const loadBundle = useDashboardStore((s) => s.loadBundle);

  useEffect(() => {
    void loadIntakeWorkspaces();
  }, [loadIntakeWorkspaces]);

  useEffect(() => {
    if (!ready || !workspaceId) return;
    void loadBundle(workspaceId);

    // Records change while an import or an agent run is in flight, so the
    // active workspace is polled rather than refreshed only on navigation.
    const interval = setInterval(() => void loadBundle(workspaceId), 2000);
    return () => clearInterval(interval);
  }, [ready, workspaceId, loadBundle]);

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

  const setWs = useCallback((next: string) => {
    setWorkspace(next);
    void track("workspace_switch", { workspaceId: next, target: next });
  }, [setWorkspace]);

  const refreshBundle = useCallback(() => loadBundle(ws), [loadBundle, ws]);

  return useMemo(() => ({
    ws, setWs, bundle, apiError, loading,
    intakeWorkspaces, refreshWorkspaces: loadIntakeWorkspaces, refreshBundle,
  }), [ws, setWs, bundle, apiError, loading, intakeWorkspaces, loadIntakeWorkspaces, refreshBundle]);
}
