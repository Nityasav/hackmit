"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

import { getSupabaseClient } from "@/lib/supabase/client";
import { intakeApi } from "@/lib/api";
import {
  bundleSchema,
  parseOrThrow,
  workspaceSummaryListSchema,
  type WorkspaceSummary,
} from "@/lib/schemas";
import type { ApprovalStatus, Bundle, IntakeWorkspace } from "@/lib/types";

/** A workspace served by Postgres, or by the intake API for uploaded records. */
export type BundleSource = "database" | "api";

const WORKSPACE_ID = /^(sandbox|mit|ws-[a-f0-9]{16})$/;

/** Shown while a workspace has records but no investigation has run. */
function emptyBundle(id: string, info?: IntakeWorkspace): Bundle {
  return {
    workspace: {
      id, name: info?.name || "Your institution", kind: info?.kind || "synthetic",
      period: info ? `${info.start} — ${info.end}` : "Loading", mode: "not_started",
      snapshot_id: "No records loaded", disabled_tabs: ["workflows", "approvals", "learning"],
      model: "Not configured", run_budget: { used: 0, total: 0 }, intake: true,
    },
    agents: [],
    briefing: { generated_at: "—", text: "Upload records to get started. No investigation has run.", actions: [] },
    kpis: [], workflows: [], tasks: [], findings: [], approvals: [], decisions: [],
    playbooks: [], ablation: null,
    report: { title: "No investigation report yet", sections: [], comparisons: [] },
  };
}

interface DashboardState {
  workspaceId: string;
  bundles: Record<string, Bundle>;
  databaseWorkspaces: WorkspaceSummary[];
  intakeWorkspaces: IntakeWorkspace[];
  error: string | null;
  loading: boolean;
  ready: boolean;

  sourceFor: (id: string) => BundleSource;
  setWorkspace: (id: string) => void;
  loadWorkspaceList: () => Promise<void>;
  loadIntakeWorkspaces: () => Promise<void>;
  loadBundle: (id: string) => Promise<void>;
  decideApproval: (approvalId: string, decision: Exclude<ApprovalStatus, "pending">) => Promise<void>;
}

export const useDashboardStore = create<DashboardState>()(
  persist(
    (set, get) => ({
      workspaceId: "sandbox",
      bundles: {},
      databaseWorkspaces: [],
      intakeWorkspaces: [],
      error: null,
      loading: true,
      ready: false,

      sourceFor: (id) =>
        get().databaseWorkspaces.some((w) => w.id === id) ? "database" : "api",

      setWorkspace: (id) => {
        if (!WORKSPACE_ID.test(id)) return;
        set({ workspaceId: id, error: null });
      },

      loadWorkspaceList: async () => {
        // ready must be set on every path. If it is not, the provider renders
        // "Loading workspace…" forever and never says why.
        try {
          const { data, error } = await getSupabaseClient().rpc("list_workspaces");
          if (error) throw new Error(error.message);
          set({
            databaseWorkspaces: parseOrThrow(workspaceSummaryListSchema, data, "Workspace list"),
            error: null,
          });
        } catch (e) {
          set({ error: e instanceof Error ? e.message : "Could not load the workspace list." });
        } finally {
          set({ ready: true });
        }
      },

      loadIntakeWorkspaces: async () => {
        try {
          set({ intakeWorkspaces: await intakeApi<IntakeWorkspace[]>("/api/workspaces") });
        } catch {
          // The intake service is optional; its absence is not a dashboard error.
        }
      },

      loadBundle: async (id) => {
        try {
          let payload: unknown;
          if (get().sourceFor(id) === "database") {
            const { data, error } = await getSupabaseClient().rpc("get_bundle", { ws: id });
            if (error) throw new Error(error.message);
            if (!data) throw new Error(`Workspace "${id}" was not found.`);
            payload = data;
          } else {
            payload = await intakeApi<unknown>(`/api/workspaces/${encodeURIComponent(id)}/bundle`);
          }

          const bundle = parseOrThrow(bundleSchema, payload, `Workspace "${id}"`);
          set((s) => ({ bundles: { ...s.bundles, [id]: bundle }, error: null, loading: false }));
        } catch (e) {
          set({ error: e instanceof Error ? e.message : "Could not load this workspace.", loading: false });
        }
      },

      decideApproval: async (approvalId, decision) => {
        const id = get().workspaceId;

        if (get().sourceFor(id) === "database") {
          const { data, error } = await getSupabaseClient()
            .rpc("decide_approval", { ws: id, approval: approvalId, decision });
          if (error) {
            set({ error: error.message });
            return;
          }
          const bundle = parseOrThrow(bundleSchema, data, "Updated workspace");
          set((s) => ({ bundles: { ...s.bundles, [id]: bundle }, error: null }));
          return;
        }

        try {
          const payload = await intakeApi<unknown>(`/api/approvals/${approvalId}/decision`, {
            method: "POST",
            body: { workspace: id, decision },
          });
          const bundle = parseOrThrow(bundleSchema, payload, "Updated workspace");
          set((s) => ({ bundles: { ...s.bundles, [id]: bundle }, error: null }));
        } catch (e) {
          set({ error: e instanceof Error ? e.message : "Could not record that decision." });
        }
      },
    }),
    {
      name: "schooltrace.dashboard",
      storage: createJSONStorage(() => localStorage),
      // Only the chosen workspace is worth remembering. Bundles are refetched
      // so a stale one is never shown as current.
      partialize: (s) => ({ workspaceId: s.workspaceId }),
    },
  ),
);

/** The bundle for the active workspace, or an empty one while it loads. */
export function useActiveBundle(): Bundle {
  const workspaceId = useDashboardStore((s) => s.workspaceId);
  const bundle = useDashboardStore((s) => s.bundles[s.workspaceId]);
  const info = useDashboardStore((s) => s.intakeWorkspaces.find((w) => w.id === s.workspaceId));
  return bundle ?? emptyBundle(workspaceId, info);
}

