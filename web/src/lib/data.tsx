"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import sandboxFixture from "../fixtures/sandbox.json";
import mitFixture from "../fixtures/mit.json";
import type { ApprovalStatus, Bundle, IntakeWorkspace } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const FIXTURES: Record<string, Bundle> = {
  sandbox: sandboxFixture as unknown as Bundle, mit: mitFixture as unknown as Bundle,
};
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
function empty(ws: string, info?: IntakeWorkspace): Bundle {
  return { workspace: { id: ws, name: info?.name || "Your institution", kind: info?.kind || "synthetic",
    period: info ? `${info.start} — ${info.end}` : "Loading", mode: "not_started",
    // Mirrors projection._disabled_tabs: a public-documents workspace holds no
    // transactions, everything else only waits on the Learning workstream. A
    // placeholder that disables more than the API does flickers tabs off then on.
    snapshot_id: "No records loaded",
    disabled_tabs: info?.kind === "public" ? ["workflows", "approvals", "learning"] : ["learning"],
    model: "Not configured", run_budget: { used: 0, total: 0 }, intake: true },
    agents: [], briefing: { generated_at: "—", text: "Upload records to get started. No investigation has run.", actions: [] },
    kpis: [], workflows: [], tasks: [], findings: [], approvals: [], decisions: [], playbooks: [], ablation: null,
    report: { title: "No investigation report yet", sections: [], comparisons: [] } };
}
interface DataContextValue {
  ws: string; setWs: (ws: string) => void; bundle: Bundle; source: "fixtures" | "api"; apiError: string | null;
  intakeWorkspaces: IntakeWorkspace[]; refreshWorkspaces: () => Promise<void>; refreshBundle: () => Promise<void>;
  decideApproval: (id: string, decision: Exclude<ApprovalStatus, "pending">) => void;
}
const DataContext = createContext<DataContextValue | null>(null);
export function DataProvider({ children }: { children: React.ReactNode }) {
  const [ws, setWsState] = useState("sandbox");
  const [bundles, setBundles] = useState<Record<string, Bundle>>(FIXTURES);
  const [intakeWorkspaces, setIntakeWorkspaces] = useState<IntakeWorkspace[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);
  const [restored, setRestored] = useState(false);
  const source = process.env.NEXT_PUBLIC_API_URL || !FIXTURES[ws] ? "api" : "fixtures";
  const refreshWorkspaces = useCallback(async () => {
    setIntakeWorkspaces(await intakeApi<IntakeWorkspace[]>("/api/workspaces"));
  }, []);
  useEffect(() => {
    queueMicrotask(() => {
      try {
        const saved = localStorage.getItem("st.ws");
        if (saved && /^(sandbox|mit|ws-[a-f0-9]{16})$/.test(saved)) setWsState(saved);
      } catch {}
      setRestored(true);
    });
    intakeApi<IntakeWorkspace[]>("/api/workspaces").then(setIntakeWorkspaces).catch(() => {});
  }, []);
  const setWs = useCallback((next: string) => {
    setWsState(next); setApiError(null);
    try { localStorage.setItem("st.ws", next); } catch {}
  }, []);
  const refreshBundle = useCallback(async () => {
    if (source !== "api") return;
    const next = await intakeApi<Bundle>(`/api/workspaces/${encodeURIComponent(ws)}/bundle`);
    setBundles((b) => ({ ...b, [ws]: next })); setApiError(null);
  }, [source, ws]);
  useEffect(() => {
    if (source !== "api") return;
    let cancelled = false;
    const load = async () => {
      try {
        const next = await intakeApi<Bundle>(`/api/workspaces/${encodeURIComponent(ws)}/bundle`);
        if (!cancelled) { setBundles((b) => ({ ...b, [ws]: next })); setApiError(null); }
      } catch (e) { if (!cancelled) setApiError(e instanceof Error ? e.message : "API unreachable"); }
    };
    void load(); const id = setInterval(load, 2000);
    return () => { cancelled = true; clearInterval(id); };
  }, [source, ws]);
  const decideApproval = useCallback((id: string, decision: Exclude<ApprovalStatus, "pending">) => {
    if (source === "api") {
      intakeApi<Bundle>(`/api/approvals/${id}/decision`, { method: "POST", body: JSON.stringify({ workspace: ws, decision }) })
        .then((next) => setBundles((b) => ({ ...b, [ws]: next }))).catch((e) => setApiError(e.message));
      return;
    }
    setBundles((b) => ({ ...b, [ws]: { ...b[ws],
      approvals: b[ws].approvals.map((a) => a.id === id ? { ...a, status: decision } : a),
      tasks: b[ws].tasks.map((t) => t.approval_id === id && decision === "approved"
        ? { ...t, column: "done" as const, progress: 100 } : t),
    } }));
  }, [source, ws]);
  const bundle = useMemo(() => bundles[ws] || empty(ws, intakeWorkspaces.find((w) => w.id === ws)),
    [bundles, ws, intakeWorkspaces]);
  const value = useMemo<DataContextValue>(() => ({ ws, setWs, bundle, source, apiError, decideApproval,
    intakeWorkspaces, refreshWorkspaces, refreshBundle }),
    [ws, setWs, bundle, source, apiError, decideApproval, intakeWorkspaces, refreshWorkspaces, refreshBundle]);
  return <DataContext.Provider value={value}>{restored ? children : <p className="p-6 text-sm text-slate-500">Loading workspace…</p>}</DataContext.Provider>;
}
export function useData() {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error("useData must be used inside DataProvider");
  return ctx;
}
