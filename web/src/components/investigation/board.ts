"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, intakeApi, isAbort } from "@/lib/api";
import type { AgentActivity, Task } from "@/lib/types";

/**
 * The board, polled while anything is moving.
 *
 * `/agents/activity` is written by the runtime as the work happens, so the only thing
 * needed here is to keep asking. How often is a property of the run rather than of the
 * screen — the API says how many tasks are still active, and a board with nothing
 * running backs off to a slow heartbeat instead of hammering a workspace nobody is
 * using.
 *
 * There is no streaming transport in this codebase. A poll that says so plainly is
 * better than a socket that claims to be live and silently stops reconnecting.
 */

/** While an agent is working. Fast enough that steps appear as they land. */
const ACTIVE_MS = 1500;
/** When nothing is running. Slow enough to be free, quick enough to catch a new run. */
const IDLE_MS = 8000;

export interface Board {
  tasks: Task[];
  active: number;
  waiting: number;
  loading: boolean;
  error: string | null;
  /** Whether the last poll found work in flight. */
  live: boolean;
  refresh: () => void;
}

export function useBoard(ws: string): Board {
  const [state, setState] = useState<AgentActivity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Held in a ref so changing the interval never restarts the effect: a poll loop that
  // tears itself down every time its own result changes the delay drops the request in
  // flight and stutters exactly when the board is busiest.
  const delay = useRef(ACTIVE_MS);

  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    if (!ws) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const poll = async () => {
      try {
        const view = await intakeApi<AgentActivity>(
          `/api/workspaces/${encodeURIComponent(ws)}/agents/activity`,
          { signal: controller.signal },
        );
        if (stopped) return;
        setState(view);
        setError(null);
        delay.current = view.active > 0 ? ACTIVE_MS : IDLE_MS;
      } catch (e) {
        if (isAbort(e) || stopped) return;
        setError(e instanceof ApiError ? e.message : "The board could not be read.");
        // A failing endpoint is not a reason to keep asking every 1.5 seconds.
        delay.current = IDLE_MS;
      } finally {
        if (!stopped) {
          setLoading(false);
          timer = setTimeout(poll, delay.current);
        }
      }
    };

    void poll();
    return () => {
      stopped = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [ws, tick]);

  return {
    tasks: state?.tasks ?? [],
    active: state?.active ?? 0,
    waiting: state?.waiting ?? 0,
    loading,
    error,
    live: (state?.active ?? 0) > 0,
    refresh,
  };
}
