"use client";

import { createClient } from "@/lib/supabase/client";

/**
 * What the person is doing, recorded as it happens.
 *
 * Every call is fire-and-forget: a failed write must never interrupt what the
 * person was actually doing, so errors are swallowed rather than surfaced.
 */
export type ActivityKind =
  | "sign_in"
  | "sign_up"
  | "sign_out"
  | "page_view"
  | "workspace_switch"
  | "tab_open"
  | "approval_decision"
  | "task_open"
  | "finding_open"
  | "decision_open"
  | "export"
  | "search"
  | "agent_run_started"
  | "agent_run_finished";

const SESSION_KEY = "st.session_id";

/** One session per browser tab-group, reused across reloads. */
async function sessionId(): Promise<string | null> {
  try {
    const existing = sessionStorage.getItem(SESSION_KEY);
    if (existing) return existing;
  } catch {
    return null;
  }

  const supabase = createClient();
  const { data: auth } = await supabase.auth.getUser();
  if (!auth.user) return null;

  const { data, error } = await supabase
    .from("user_sessions")
    .insert({
      user_id: auth.user.id,
      user_agent: typeof navigator === "undefined" ? null : navigator.userAgent,
      entry_path: typeof location === "undefined" ? null : location.pathname,
    })
    .select("id")
    .single();

  if (error || !data) return null;
  try {
    sessionStorage.setItem(SESSION_KEY, data.id);
  } catch {}
  return data.id;
}

export async function track(
  kind: ActivityKind,
  options: { workspaceId?: string | null; target?: string | null; metadata?: Record<string, unknown> } = {},
): Promise<void> {
  try {
    const supabase = createClient();
    const { data: auth } = await supabase.auth.getUser();
    if (!auth.user) return;

    await supabase.from("activity_events").insert({
      user_id: auth.user.id,
      session_id: await sessionId(),
      workspace_id: options.workspaceId ?? null,
      kind,
      path: typeof location === "undefined" ? null : location.pathname,
      target: options.target ?? null,
      metadata: options.metadata ?? {},
    });

    // Keep "last seen" current so presence does not need the event log scanned.
    await supabase.rpc("touch_presence", { ws: options.workspaceId ?? null, p_path: null });
  } catch {
    // Recording what happened must never break what is happening.
  }
}

/** Clears the session marker so signing out starts a new one next time. */
export function endActivitySession(): void {
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {}
}
