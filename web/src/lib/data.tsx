"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { createClient } from "@/lib/supabase/client";
import { track } from "@/lib/activity";
import type { ApprovalStatus, Bundle, IntakeWorkspace } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function intakeApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(API_URL + path, { ...init, credentials: "include", cache: "no-store", headers: {
    ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    "X-SchoolTrace-Reviewer": "local-reviewer", ...init.headers,
  } });
  const data = await response.json();
  if (!response.ok) {
    const d = data.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d)
      ? d.map((e: { msg: string }) => e.msg).join("; ") : d?.message || `API ${response.status}`);
  }
  return data;
}

/** Shown while a workspace has records but no investigation has run yet. */
function empty(ws: string, info?: IntakeWorkspace): Bundle {
  return { workspace: { id: ws, name: info?.name || "Your institution", kind: info?.kind || "synthetic",
    period: info ? `${info.start} — ${info.end}` : "Loading", mode: "not_started",
    snapshot_id: "No records loaded", disabled_tabs: ["workflows", "approvals", "learning"],
    model: "Not configured", run_budget: { used: 0, total: 0 }, intake: true },
    agents: [], briefing: { generated_at: "—", text: "Upload records to get started. No investigation has run.", actions: [] },
    kpis: [], workflows: [], tasks: [], findings: [], approvals: [], decisions: [], playbooks: [], ablation: null,
    report: { title: "No investigation report yet", sections: [], comparisons: [] } };
}

/**
 * Where a workspace's data comes from. Postgres holds the institutions the
 * dashboard ships with; the intake API serves workspaces a person creates by
 * uploading their own records.
 */
type Source = "database" | "api";

interface DataContextValue {
  ws: string; setWs: (ws: string) => void; bundle: Bundle; source: Source; apiError: string | null;
  loading: boolean;
  intakeWorkspaces: IntakeWorkspace[]; refreshWorkspaces: () => Promise<void>; refreshBundle: () => Promise<void>;
  decideApproval: (id: string, decision: Exclude<ApprovalStatus, "pending">) => void;
}

const DataContext = createContext<DataContextValue | null>(null);

export function DataProvider({ children }: { children: React.ReactNode }) {
  const [ws, setWsState] = useState("sandbox");
  const [bundles, setBundles] = useState<Record<string, Bundle>>({});
  const [dbWorkspaces, setDbWorkspaces] = useState<string[]>([]);
  const [intakeWorkspaces, setIntakeWorkspaces] = useState<IntakeWorkspace[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);
  const [restored, setRestored] = useState(false);
  const [loading, setLoading] = useState(true);

  // A workspace served by the intake API is one the API knows about and the
  // database does not.
  const source: Source = dbWorkspaces.includes(ws) ? "database" : "api";

  const refreshWorkspaces = useCallback(async () => {
    setIntakeWorkspaces(await intakeApi<IntakeWorkspace[]>("/api/workspaces"));
  }, []);

  useEffect(() => {
    let cancelled = false;

    const boot = async () => {
      const supabase = createClient();
      const { data, error } = await supabase.rpc("list_workspaces");
      if (!cancelled && !error && Array.isArray(data)) {
        setDbWorkspaces(data.map((w: { id: string }) => w.id));
      }

      let saved: string | null = null;
      try {
        saved = localStorage.getItem("st.ws");
      } catch {}
      if (!cancelled && saved && /^(sandbox|mit|ws-[a-f0-9]{16})$/.test(saved)) setWsState(saved);
      if (!cancelled) setRestored(true);
    };

    void boot();
    intakeApi<IntakeWorkspace[]>("/api/workspaces").then(setIntakeWorkspaces).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const setWs = useCallback((next: string) => {
    setWsState(next); setApiError(null);
    try { localStorage.setItem("st.ws", next); } catch {}
    void track("workspace_switch", { workspaceId: next, target: next });
  }, []);

  const loadFromDatabase = useCallback(async (id: string) => {
    const supabase = createClient();
    const { data, error } = await supabase.rpc("get_bundle", { ws: id });
    if (error) throw new Error(error.message);
    if (!data) throw new Error(`workspace ${id} not found`);
    return data as Bundle;
  }, []);

  const refreshBundle = useCallback(async () => {
    if (source === "database") {
      setBundles((b) => ({ ...b, [ws]: b[ws] }));
      const next = await loadFromDatabase(ws);
      setBundles((b) => ({ ...b, [ws]: next })); setApiError(null);
      return;
    }
    const next = await intakeApi<Bundle>(`/api/workspaces/${encodeURIComponent(ws)}/bundle`);
    setBundles((b) => ({ ...b, [ws]: next })); setApiError(null);
  }, [source, ws, loadFromDatabase]);

  useEffect(() => {
    if (!restored) return;
    let cancelled = false;

    const load = async () => {
      try {
        const next = source === "database"
          ? await loadFromDatabase(ws)
          : await intakeApi<Bundle>(`/api/workspaces/${encodeURIComponent(ws)}/bundle`);
        if (!cancelled) { setBundles((b) => ({ ...b, [ws]: next })); setApiError(null); }
      } catch (e) {
        if (!cancelled) setApiError(e instanceof Error ? e.message : "Could not load this workspace");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    // The intake API changes while records are being imported; the database
    // workspaces only change when someone decides an approval, which already
    // refreshes in place.
    if (source === "api") {
      const id = setInterval(load, 2000);
      return () => { cancelled = true; clearInterval(id); };
    }
    return () => { cancelled = true; };
  }, [restored, source, ws, loadFromDatabase]);

  const decideApproval = useCallback((id: string, decision: Exclude<ApprovalStatus, "pending">) => {
    if (source === "database") {
      const supabase = createClient();
      void supabase
        .rpc("decide_approval", { ws, approval: id, decision })
        .then(({ data, error }) => {
          if (error) { setApiError(error.message); return; }
          if (data) setBundles((b) => ({ ...b, [ws]: data as Bundle }));
        });
      return;
    }
    intakeApi<Bundle>(`/api/approvals/${id}/decision`, { method: "POST", body: JSON.stringify({ workspace: ws, decision }) })
      .then((next) => setBundles((b) => ({ ...b, [ws]: next })))
      .catch((e) => setApiError(e.message));
    void track("approval_decision", { workspaceId: ws, target: id, metadata: { decision } });
  }, [source, ws]);

  const bundle = useMemo(() => bundles[ws] || empty(ws, intakeWorkspaces.find((w) => w.id === ws)),
    [bundles, ws, intakeWorkspaces]);

  const value = useMemo<DataContextValue>(() => ({ ws, setWs, bundle, source, apiError, decideApproval,
    loading, intakeWorkspaces, refreshWorkspaces, refreshBundle }),
    [ws, setWs, bundle, source, apiError, decideApproval, loading, intakeWorkspaces, refreshWorkspaces, refreshBundle]);

  return (
    <DataContext.Provider value={value}>
      {restored ? children : <p className="p-6 text-[14px] text-ink-dim">Loading workspace…</p>}
    </DataContext.Provider>
  );
}

export function useData() {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error("useData must be used inside DataProvider");
  return ctx;
}
