"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import sandboxFixture from "../../../contracts/fixtures/sandbox.json";
import mitFixture from "../../../contracts/fixtures/mit.json";
import type { ApprovalStatus, Bundle, WorkspaceId } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const POLL_MS = 2000;

const FIXTURES: Record<WorkspaceId, Bundle> = {
  sandbox: sandboxFixture as unknown as Bundle,
  mit: mitFixture as unknown as Bundle,
};

interface DataContextValue {
  ws: WorkspaceId;
  setWs: (ws: WorkspaceId) => void;
  bundle: Bundle;
  /** "fixtures" = offline replay of contracts/fixtures; "api" = polling the FastAPI server. */
  source: "fixtures" | "api";
  apiError: string | null;
  decideApproval: (id: string, decision: Exclude<ApprovalStatus, "pending">) => void;
}

const DataContext = createContext<DataContextValue | null>(null);

export function DataProvider({ children }: { children: React.ReactNode }) {
  const [ws, setWsState] = useState<WorkspaceId>("sandbox");
  const [bundles, setBundles] = useState<Record<WorkspaceId, Bundle>>(FIXTURES);
  const [apiError, setApiError] = useState<string | null>(null);
  const source = API_URL ? "api" : "fixtures";

  useEffect(() => {
    try {
      const saved = localStorage.getItem("st.ws");
      if (saved === "sandbox" || saved === "mit") setWsState(saved);
    } catch {}
  }, []);

  const setWs = useCallback((next: WorkspaceId) => {
    setWsState(next);
    try {
      localStorage.setItem("st.ws", next);
    } catch {}
  }, []);

  // Live mode: poll the API for the active workspace's bundle.
  useEffect(() => {
    if (!API_URL) return;
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${API_URL}/api/workspaces/${ws}/bundle`, { cache: "no-store" });
        if (!res.ok) throw new Error(`API ${res.status}`);
        const next = (await res.json()) as Bundle;
        if (!cancelled) {
          setBundles((b) => ({ ...b, [ws]: next }));
          setApiError(null);
        }
      } catch (e) {
        if (!cancelled) setApiError(e instanceof Error ? e.message : "API unreachable");
      }
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [ws]);

  // Offline replay: advance in-flight tasks so the recorded run plays back.
  useEffect(() => {
    if (API_URL) return;
    const id = setInterval(() => {
      setBundles((b) => {
        const cur = b.sandbox;
        const tasks = cur.tasks.map((t) => {
          if (t.column !== "working" && t.column !== "auditor_review") return t;
          const bump = Math.random() < 0.35 ? 1 : 0;
          return {
            ...t,
            progress: Math.min(95, t.progress + bump),
            eta_s: t.eta_s == null ? null : Math.max(3, t.eta_s - 1),
          };
        });
        return { ...b, sandbox: { ...cur, tasks } };
      });
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const decideApproval = useCallback(
    (id: string, decision: Exclude<ApprovalStatus, "pending">) => {
      setBundles((b) => {
        const cur = b[ws];
        const approvals = cur.approvals.map((a) => (a.id === id ? { ...a, status: decision } : a));
        const tasks = cur.tasks.map((t) =>
          t.approval_id === id ? { ...t, column: "done" as const, progress: 100 } : t,
        );
        return { ...b, [ws]: { ...cur, approvals, tasks } };
      });
      if (API_URL) {
        fetch(`${API_URL}/api/approvals/${id}/decision`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workspace: ws, decision }),
        }).catch(() => setApiError("Could not save decision"));
      }
    },
    [ws],
  );

  const value = useMemo<DataContextValue>(
    () => ({ ws, setWs, bundle: bundles[ws], source, apiError, decideApproval }),
    [ws, setWs, bundles, source, apiError, decideApproval],
  );

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}

export function useData(): DataContextValue {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error("useData must be used inside <DataProvider>");
  return ctx;
}
