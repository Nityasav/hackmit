"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

import { intakeApi } from "@/lib/api";
import { bundleSchema, parseOrThrow } from "@/lib/schemas";
import type { Bundle, IntakeWorkspace } from "@/lib/types";

/** Workspaces are created by the intake service, which issues these ids. */
const WORKSPACE_ID = /^ws-[a-f0-9]{16}$/;

/** Shown while a workspace exists but no records are committed yet. */
function emptyBundle(id: string, info?: IntakeWorkspace): Bundle {
  return {
    workspace: {
      id,
      name: info?.name || "Your institution",
      kind: info?.kind || "synthetic",
      period: info ? `${info.start} — ${info.end}` : "Loading",
      mode: "not_started",
      snapshot_id: "No records loaded",
      model: "Not configured",
      run_budget: { used: 0, total: 0 },
      intake: true,
    },
    agents: [],
    briefing: {
      generated_at: "—",
      text: "Upload records to get started. No investigation has run.",
      actions: [],
    },
    tasks: [],
    findings: [],
    decisions: [],
    playbooks: [],
    approvals: [],
  };
}

interface DashboardState {
  workspaceId: string;
  bundles: Record<string, Bundle>;
  intakeWorkspaces: IntakeWorkspace[];
  error: string | null;
  loading: boolean;
  ready: boolean;

  setWorkspace: (id: string) => void;
  loadIntakeWorkspaces: () => Promise<void>;
  loadBundle: (id: string) => Promise<void>;
}

export const useDashboardStore = create<DashboardState>()(
  persist(
    (set, get) => ({
      workspaceId: "",
      bundles: {},
      intakeWorkspaces: [],
      error: null,
      loading: true,
      ready: false,

      setWorkspace: (id) => {
        if (!WORKSPACE_ID.test(id)) return;
        set({ workspaceId: id, error: null });
      },

      loadIntakeWorkspaces: async () => {
        // ready must be set on every path. If it is not, the provider renders
        // "Loading workspace…" forever and never says why.
        try {
          const list = await intakeApi<IntakeWorkspace[]>("/api/workspaces");
          const current = get().workspaceId;
          set({
            intakeWorkspaces: list,
            // Remember the chosen workspace only while it still exists.
            workspaceId: list.some((w) => w.id === current) ? current : (list[0]?.id ?? ""),
            error: null,
          });
        } catch (e) {
          set({ error: e instanceof Error ? e.message : "Could not load your workspaces." });
        } finally {
          set({ ready: true });
        }
      },

      loadBundle: async (id) => {
        if (!id) {
          set({ loading: false });
          return;
        }
        try {
          const payload = await intakeApi<unknown>(`/api/workspaces/${encodeURIComponent(id)}/bundle`);
          const bundle = parseOrThrow(bundleSchema, payload, `Workspace "${id}"`);
          set((s) => ({ bundles: { ...s.bundles, [id]: bundle }, error: null, loading: false }));
        } catch (e) {
          const message = e instanceof Error ? e.message : "Could not load this workspace.";
          // A workspace may be deleted in another tab or by an administrator.
          // Refresh the list so a removed selection cannot keep polling a 404.
          if (/unknown workspace|not found/i.test(message)) {
            await get().loadIntakeWorkspaces();
            set({ error: null, loading: false });
            return;
          }
          set({ error: message, loading: false });
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
