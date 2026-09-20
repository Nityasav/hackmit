"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, intakeApi, isAbort } from "@/lib/api";
import type { AgentNode, AgentOrganization, AgentRunResult } from "@/lib/types";

/**
 * The agent organization, as the API reports it.
 *
 * Everything on screen comes from `/api/workspaces/{ws}/agents`, which is built from
 * the registry — so this cannot describe an organization that differs from the one that
 * would actually run. An agent's charter, what it reads, what blocks it and what always
 * sends it to a person are all declared there, not written here.
 */

function reason(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : fallback;
}

export interface Organization {
  agents: AgentNode[];
  spend: AgentOrganization["spend"] | null;
  loading: boolean;
  error: string | null;
  runErrors: Record<string, string>;
  /** The agent currently running, if any. */
  running: string | null;
  /** Results this session, newest first. */
  results: AgentRunResult[];
  refresh: () => Promise<void>;
  run: (agentId: string, objective: string) => Promise<void>;
}

export function useOrganization(ws: string): Organization {
  const [agents, setAgents] = useState<AgentNode[]>([]);
  const [spend, setSpend] = useState<AgentOrganization["spend"] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [results, setResults] = useState<AgentRunResult[]>([]);
  const [runErrors, setRunErrors] = useState<Record<string, string>>({});

  // The fetch lives inside the effect, so no state update can be traced back into the
  // effect body; `reload` is how a caller asks for a fresh read after something moved.
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!ws) return;
    const controller = new AbortController();

    void (async () => {
      try {
        const view = await intakeApi<AgentOrganization>(
          `/api/workspaces/${encodeURIComponent(ws)}/agents`,
          { signal: controller.signal });
        if (controller.signal.aborted) return;
        setAgents(view.agents);
        setSpend(view.spend);
        setError(null);
      } catch (e) {
        if (!isAbort(e)) setError(reason(e, "The agent organization could not be loaded."));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();

    return () => controller.abort();
  }, [ws, reload]);

  const refresh = useCallback(async () => {
    setReload((n) => n + 1);
  }, []);

  const run = useCallback(async (agentId: string, objective: string) => {
    setRunning(agentId);
    setError(null);
    setRunErrors(current => ({ ...current, [agentId]: "" }));
    try {
      const result = await intakeApi<AgentRunResult>(
        `/api/workspaces/${encodeURIComponent(ws)}/agents/${encodeURIComponent(agentId)}/runs`,
        { method: "POST", body: { objective }, timeout: 600000 });
      setResults((current) => [result, ...current]);
      // Spend moved, and an agent's readiness can change once it writes a decision.
      setReload((n) => n + 1);
    } catch (e) {
      setRunErrors(current => ({ ...current, [agentId]: reason(e, "The agent could not be run.") }));
    } finally {
      setRunning(null);
    }
  }, [ws]);

  return { agents, spend, loading, error, runErrors, running, results, refresh, run };
}

/** The workers, each with its subagents, in registry order. */
export function byWorker(agents: AgentNode[]): { worker: AgentNode; children: AgentNode[] }[] {
  return agents
    .filter((agent) => agent.tier === "worker")
    .map((worker) => ({
      worker,
      children: agents.filter((agent) => agent.parent === worker.id),
    }));
}

/** Money, from integer cents. The UI is the only place that formats. */
export function money(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const value = Math.abs(cents);
  return `${sign}$${Math.trunc(value / 100)}.${String(value % 100).padStart(2, "0")}`;
}
