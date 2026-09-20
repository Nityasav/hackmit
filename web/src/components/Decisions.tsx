"use client";

import { useState } from "react";

import { intakeApi, useData } from "@/lib/data";
import type { Approval } from "@/lib/types";

/**
 * Where a person answers what an agent could not.
 *
 * An agent that escalates is saying the workspace's own thresholds put this
 * beyond its authority. Until this screen existed the runtime wrote that on
 * the decision and then offered nobody anywhere to supply the judgement, so
 * the answer never came, no precedent was ever written, and the agents began
 * every run knowing nothing anyone had ever decided.
 *
 * Deciding here does two separate things, and the difference matters enough to
 * say on screen: it records the judgement against this conclusion, and it
 * writes precedent the next run has to re-check. It does not approve a
 * payment, post a journal, or change the books.
 */
export function Decisions() {
  const { bundle, refreshBundle } = useData();
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [instructions, setInstructions] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");

  const pending = bundle.approvals.filter((a) => a.status === "pending");
  const decided = bundle.approvals.filter((a) => a.status !== "pending");

  async function decide(approval: Approval, decision: "approved" | "rejected") {
    setBusy(approval.id);
    setError("");
    try {
      await intakeApi(`/api/approvals/${encodeURIComponent(approval.id)}/decision`, {
        method: "POST",
        body: { workspace: bundle.workspace.id, decision }, timeout: 600000,
      });
      await refreshBundle();
      setMessage("Decision saved. Paused workflows resume; completed standalone tasks are resolved. Add revised instructions below for further work.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "The decision could not be saved.");
    } finally {
      setBusy("");
    }
  }

  async function revise(approval: Approval) {
    setBusy(approval.id); setError(""); setMessage("");
    try {
      await intakeApi(`/api/workspaces/${bundle.workspace.id}/agents/approvals/${encodeURIComponent(approval.id)}/revise`,
        { method: "POST", body: { objective: instructions[approval.id] }, timeout: 600000 });
      await refreshBundle();
      setMessage("The revised task finished. Its new conclusion and any new approval request are available.");
    } catch (e) { setError(e instanceof Error ? e.message : "The revised task failed. Check its recorded history."); }
    finally { setBusy(""); }
  }
  const editor = (approval: Approval) => <details className="mt-3 border-t border-line pt-3">
    <summary className="cursor-pointer text-sm font-semibold">Revise instructions and rerun</summary>
    <textarea aria-label={`Revised instructions for ${approval.title}`} rows={3} maxLength={2000}
      className="mt-3 w-full border border-line bg-white p-3 text-sm"
      placeholder="Describe what the agent should do differently. For example: focus on overdue balances and show the source rows."
      value={instructions[approval.id] || ""} onChange={e => setInstructions({ ...instructions, [approval.id]: e.target.value })} />
    <p className="my-2 text-xs text-ink-dim">Starts a new paid task for this agent. A pending proposal is rejected, not silently edited. Existing decisions and evidence remain in history.</p>
    <button disabled={!!busy || !instructions[approval.id]?.trim()} className="bg-ink px-3 py-2 text-sm text-white disabled:opacity-40" onClick={() => void revise(approval)}>
      {busy === approval.id ? "Working…" : "Revise and rerun"}
    </button>
  </details>;

  return (
    <section className="border border-line p-5">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 className="text-xl font-semibold">Waiting on you</h2>
        <span className="text-sm text-ink-dim">
          {pending.length === 0
            ? "Nothing an agent could not settle on its own."
            : `${pending.length} conclusion(s) an agent escalated rather than settle.`}
        </span>
      </div>

      {error && (
        <p role="alert" className="mt-3 border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}
      {message && <p role="status" className="mt-3 border border-line p-3 text-sm">{message}</p>}

      {pending.length === 0 ? (
        <p className="mt-3 max-w-2xl text-sm text-ink-dim">
          An agent escalates when a conclusion crosses a threshold this workspace set — an
          amount above the approval limit, confidence below the bar, or a named condition.
          Run an investigation and anything that crosses one will appear here.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {pending.map((approval) => (
            <li key={approval.id} className="border border-line p-4">
              <span className="text-xs uppercase tracking-wide text-ink-dim">
                {approval.agent} · {approval.kind}
                {approval.verified ? " · independently reviewed" : " · not independently reviewed"}
              </span>
              <b className="my-2 block">{approval.title}</b>
              <p className="text-sm leading-relaxed text-ink-dim">{approval.summary}</p>

              {approval.journal && (
                <p className="mt-2 text-xs text-amber-800">
                  This proposal carries a journal. Approving still posts nothing; a posting is a
                  separate, explicit step.
                </p>
              )}

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  className="min-h-11 bg-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
                  disabled={busy === approval.id}
                  onClick={() => void decide(approval, "approved")}
                >
                  {busy === approval.id ? "Continuing…" : "Approve and continue"}
                </button>
                <button
                  className="min-h-11 border border-line px-4 py-2 text-sm disabled:opacity-40"
                  disabled={busy === approval.id}
                  onClick={() => void decide(approval, "rejected")}
                >
                  Reject
                </button>
                <span className="text-xs text-ink-dim">
                  Either way this becomes precedent the next run must re-check. Nothing is paid,
                  posted or approved in the books.
                </span>
              </div>
              {editor(approval)}
            </li>
          ))}
        </ul>
      )}

      {decided.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm">
            Already decided ({decided.length})
          </summary>
          <ul className="mt-2 space-y-1 text-sm">
            {decided.map((approval) => (
              <li key={approval.id} className="border-b border-line py-1.5">
                <span
                  className={
                    approval.status === "approved" ? "text-green-800" : "text-ink-dim"
                  }
                >
                  {approval.status}
                </span>{" "}
                · {approval.title}
                {editor(approval)}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
