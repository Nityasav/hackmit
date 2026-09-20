"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, intakeApi } from "@/lib/api";
import { Button, Pill } from "@/components/ui";
import type { ChatReply, ChatTurn, Escalation } from "@/lib/types";
import { RunActivity } from "./RunActivity";
import { AuditDeliverable } from "./AuditDeliverable";
import { TaskDeliverable } from "./TaskDeliverable";

/**
 * The orchestrator, as a conversation.
 *
 * One box. You say what you want looked at, the organization runs, and what comes back is
 * the run itself — which domains it reached, what each concluded, what it cost, and
 * anything that stopped for you.
 *
 * Nothing on this screen is written by a model. Every sentence in a reply is a count the
 * API computed or a line an agent recorded, and a question waiting on you is rendered
 * from the interrupt the run actually paused on. An answer is addressed to one question
 * by id: several agents can stop at once, and one answer applied to all of them would
 * record a decision on questions nobody was shown.
 */

const money = (cents: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);

function reason(error: unknown, fallback: string) {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : fallback;
}

export function Orchestrator({ ws }: { ws: string }) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  // Which questions are *still* open, read live. The escalations inside a turn are
  // frozen at the moment the reply was written, so a question answered since — here,
  // or on the approvals page — kept offering buttons that could only fail.
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [deciding, setDeciding] = useState("");
  const [activeThread, setActiveThread] = useState("");
  const [confirmAudit, setConfirmAudit] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const [body, queue] = await Promise.all([
      intakeApi<{ turns: ChatTurn[] }>(`/api/workspaces/${ws}/chat`),
      intakeApi<{ escalations: Escalation[] }>(`/api/workspaces/${ws}/agents/escalations`),
    ]);
    setTurns(body.turns);
    setOpen(new Set(queue.escalations.map((item) => item.approval_id)));
  }, [ws]);

  useEffect(() => {
    // The read lives inside the effect rather than being called from its body, so no
    // state update is traceable back to the render that scheduled it.
    void (async () => {
      try {
        await load();
      } catch (e) {
        setError(reason(e, "The conversation could not be read"));
      }
    })();
  }, [load]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, busy]);

  const thread = turns.length ? turns[turns.length - 1].thread_id : "";
  const hasUnfinishedRun = turns.some(t => t.status === "running" || t.status === "waiting_on_you");
  useEffect(() => {
    if (!hasUnfinishedRun || busy) return;
    const timer = setInterval(() => { void load().catch(() => undefined); }, 3000);
    return () => clearInterval(timer);
  }, [hasUnfinishedRun, busy, load]);
  const auditRequest = [...turns].reverse().find(t => t.role === "person" && (t.body.full_review || t.body.text.startsWith("Review all domains:")));
  const auditAnswer = auditRequest && [...turns].reverse().find(t => t.role === "orchestrator" && t.thread_id === auditRequest.thread_id);

  async function send(fullReview = false) {
    const message = fullReview ? "Run a full financial review of these books and identify supported issues." : draft.trim();
    if (!message || busy) return;
    setBusy(true);
    setError("");
    setDraft("");
    setConfirmAudit(false);
    const runThread = crypto.randomUUID();
    setActiveThread(runThread);
    try {
      await intakeApi(`/api/workspaces/${ws}/chat`, {
        method: "POST",
        body: { message, thread_id: runThread, full_review: fullReview },
        timeout: 600000,
      });
    } catch (e) {
      setError(reason(e, "The run did not complete"));
    } finally {
      // Reloaded either way. A turn is recorded before its run starts, so a failure is
      // on the record too and the conversation must show it rather than the question
      // vanishing along with the error.
      await load().catch(() => undefined);
      setBusy(false);
    }
  }

  // `runId`, not the conversation: the paused investigation is what resumes.
  async function decide(runId: string, approvalId: string, decision: "approved" | "rejected") {
    setDeciding(approvalId);
    setError("");
    try {
      await intakeApi(`/api/workspaces/${ws}/agents/escalations/decide`, {
        method: "POST",
        body: { thread_id: runId, approval_id: approvalId, decision },
        timeout: 600000,
      });
    } catch (e) {
      setError(reason(e, "The decision was not recorded"));
    } finally {
      await load().catch(() => undefined);
      setDeciding("");
    }
  }

  return (
    <section className="border border-line bg-surface">
      <div className="grid border-b border-line lg:grid-cols-[minmax(0,1.8fr)_minmax(18rem,1fr)]">
      <header className="min-w-0 p-5 sm:p-6">
        <div className="flex items-center gap-3"><span aria-hidden="true" className="grid h-10 w-10 shrink-0 place-items-center bg-ink text-xs font-semibold tracking-wide text-white">CFO</span><div><h2 className="text-xl font-semibold">Ask the CFO agent</h2><p className="mt-1 text-xs text-ink-dim">A focused answer, backed by your books.</p></div></div>
        <p className="mt-4 max-w-xl text-sm leading-relaxed text-ink-dim">Choose a starting point or ask your own question. The CFO coordinates the relevant specialists.</p>
        {!turns.length && <div className="mt-4 flex flex-wrap gap-2">{["Can we close the period?", "Review receivables and overdue balances.", "Explain budget variances."].map(prompt => <button key={prompt} disabled={busy} onClick={() => setDraft(prompt)} className="border border-line bg-white px-3 py-2 text-left text-xs transition-colors hover:border-ink disabled:opacity-40">{prompt}</button>)}</div>}
      </header>
      <aside className="flex flex-col justify-center border-t border-line bg-surface-2 p-5 sm:p-6 lg:border-l lg:border-t-0">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-ink-dim">All four finance domains</p>
        <h3 className="mt-2 text-base font-semibold">Full financial audit</h3><p className="mt-2 text-xs leading-relaxed text-ink-dim">Review the supplied books and get a report with findings, gaps and next steps.</p>
        <button className="mt-4 w-full bg-ink px-4 py-3 text-sm font-semibold text-white disabled:opacity-40" disabled={busy} onClick={() => setConfirmAudit(true)}>Run financial audit</button>
        {confirmAudit && <div className="mt-4 border border-line bg-zinc-50 p-4"><p className="text-sm">This runs record checks and requests all 17 specialists across four domains. Missing inputs stay blocked. Selected evidence goes to the model provider; configured API spending limits apply.</p>
          <div className="mt-3 flex gap-3"><button className="bg-ink px-3 py-2 text-sm text-white" onClick={() => void send(true)}>Start review</button><button className="border border-line px-3 py-2 text-sm" onClick={() => setConfirmAudit(false)}>Cancel</button></div></div>}
        <p className="mt-2 text-[11px] leading-relaxed text-ink-dim">API charges apply. Not a certified audit. Nothing is posted or paid.</p>
      </aside>
      </div>

      {(turns.length > 0 || busy) && <div className="max-h-[28rem] space-y-4 overflow-y-auto p-5 sm:p-6">
        {turns.map((turn) =>
          turn.role === "person" ? (
            <p key={turn.id} className="ml-auto max-w-[80%] border border-ink bg-ink px-4 py-3 text-[14px] text-white">
              {turn.body.text}
            </p>
          ) : (
            <Reply
              key={turn.id}
              turn={turn}
              open={open}
              ws={ws}
              deciding={deciding}
              onDecide={(approvalId, decision) =>
                void decide(turn.run_id || turn.thread_id, approvalId, decision)}
            />
          ),
        )}
        {busy && <p className="text-[13.5px] text-ink-dim">The organization is working. This costs money and is not instant.</p>}
        <div ref={bottom} />
      </div>}

      {error && (
        <p role="alert" className="mx-5 mb-4 border border-red-300 bg-red-50 p-3 text-[13.5px] text-red-800">
          {error}
        </p>
      )}

      <div className="grid gap-3 p-5 sm:grid-cols-[minmax(0,1fr)_7rem] sm:p-6">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          rows={2}
          maxLength={2000}
          placeholder="Ask about your books…"
          className="min-h-20 w-full min-w-0 resize-y border border-line bg-white px-3 py-3 text-sm leading-relaxed focus:outline-2 focus:outline-offset-2 focus:outline-ink"
          aria-label="Ask the orchestrator"
        />
        <button className="min-h-12 bg-ink px-4 py-3 text-sm font-semibold text-white disabled:opacity-40" disabled={busy || !draft.trim()} onClick={() => void send()}>{busy ? "Running…" : "Ask CFO →"}</button>
      </div>
      {!busy && auditAnswer && auditAnswer.status !== "running" && <AuditDeliverable key={`${ws}:${auditAnswer.id}:${auditAnswer.status}:${auditAnswer.body.escalations?.length || 0}`} ws={ws} thread={auditAnswer.thread_id} />}
      {(activeThread || thread) && <RunActivity key={activeThread || thread} ws={ws} thread={activeThread || thread} running={busy || !!deciding || turns.some(t => t.status === "running")} />}
      {turns.length > 0 && <a href="/briefing" className="block border-t border-line px-5 py-3 text-sm font-semibold underline">View findings and download the PDF briefing →</a>}
    </section>
  );
}

export function Reply({
  turn,
  ws,
  open = new Set((turn.body as ChatReply).escalations?.map(e => e.approval_id) || []),
  deciding,
  onDecide,
}: {
  turn: ChatTurn;
  open?: Set<string>;
  ws?: string;
  deciding: string;
  onDecide: (approvalId: string, decision: "approved" | "rejected") => void;
}) {
  const body = turn.body as ChatReply & { text: string; code?: string; source_decision_ids?: string[] };
  const asked = body.escalations ?? [];
  // Only what is still open gets buttons. The rest is shown as answered rather than
  // removed: a question that vanishes leaves a person unsure it was ever theirs.
  const waiting = asked.filter((item) => open.has(item.approval_id));
  const settled = asked.filter((item) => !open.has(item.approval_id));
  const findings = body.findings ?? [];

  return (
    <div className="max-w-[92%] border border-line bg-surface-2 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={turn.status === "failed" ? "red" : turn.status === "waiting_on_you" ? "amber" : "green"}>
          {turn.status === "failed" ? "Stopped" : turn.status === "waiting_on_you" ? "Waiting on you" : "Done"}
        </Pill>
        {(body.routed_to ?? []).map((name) => (
          <Pill key={name}>{name}</Pill>
        ))}
        {body.spend && <span className="font-accent text-[12.5px] text-ink-dim">{money(body.spend.spent_cents)}</span>}
      </div>

      <p className="mt-3 whitespace-pre-wrap text-[14px] leading-relaxed">{body.text}</p>
      {ws && turn.status !== "running" && turn.status !== "failed" && <ResponseDownload ws={ws} turn={turn} />}
      {ws && !!body.source_decision_ids?.length && <details className="mt-3 border-t border-line pt-3"><summary className="cursor-pointer text-sm font-semibold">Sources behind this answer ({body.source_decision_ids.length})</summary>{body.source_decision_ids.map(id => <details key={id} className="mt-3"><summary className="cursor-pointer text-xs underline">Saved task {id}</summary><TaskDeliverable ws={ws} decision={id} /></details>)}</details>}

      {findings.length > 0 && (
        <details className="mt-3 border-t border-line pt-3"><summary className="cursor-pointer text-sm font-semibold">Agent conclusions ({findings.length})</summary><ul className="mt-3 space-y-2">
          {findings.map((finding) => (
            <li key={`${turn.id}-${finding.decision_id ?? finding.agent_id}`} className="border-l-2 border-line pl-3">
              <p className="text-[13px] font-semibold">
                {finding.agent_name}
                {finding.confidence !== null && finding.confidence !== undefined && (
                  <span className="ml-2 font-normal text-ink-dim">
                    confidence {finding.confidence} of 100, computed
                  </span>
                )}
              </p>
              <p className="text-[13.5px]">{finding.summary}</p>
              {ws && finding.decision_id && <details className="mt-2"><summary className="cursor-pointer text-xs font-semibold underline">View task deliverable</summary><TaskDeliverable ws={ws} decision={finding.decision_id} /></details>}
            </li>
          ))}
        </ul></details>
      )}

      {!!body.unresolved?.length && <details className="mt-3 border-t border-line pt-3"><summary className="cursor-pointer text-sm font-semibold">Missing inputs & unresolved questions ({body.unresolved.length})</summary><ul className="mt-3 list-disc space-y-2 pl-4 text-xs leading-relaxed">{body.unresolved.map((item, i) => <li key={i}>{item}</li>)}</ul></details>}

      {waiting.map((question) => (
        <Question
          key={question.approval_id}
          question={question}
          busy={deciding === question.approval_id}
          onDecide={(decision) => onDecide(question.approval_id, decision)}
        />
      ))}

      {settled.map((question) => (
        <p key={question.approval_id} className="mt-3 border-l-2 border-line pl-3 text-[13px] text-ink-dim">
          {typeof question.agent === "string" ? question.agent : question.agent?.name ?? "An agent"} asked about this and it has since been
          answered. Nothing is outstanding.
        </p>
      ))}

      {body.deliverable && (
        <div className="mt-3 border border-ink bg-white p-4">
          <p className="text-[13px] font-semibold">{body.deliverable.title}</p>
          <p className="mt-1 text-[13px] text-ink-dim">
            Ready on the Briefing tab, where it opens and prints to PDF. Every figure on
            it was computed from the ledger; none was written by a model.
          </p>
          <Link href="/briefing" className="mt-2 inline-block text-[13px] underline">
            Open the Briefing tab &rarr;
          </Link>
        </div>
      )}

      {body.note && <p className="mt-3 text-[12.5px] text-ink-dim">{body.note}</p>}
    </div>
  );
}

function ResponseDownload({ ws, turn }: { ws: string; turn: ChatTurn }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function download() {
    setBusy(true); setError("");
    try {
      const response = await api.get(`/api/workspaces/${encodeURIComponent(ws)}/chat/${encodeURIComponent(turn.id)}/pdf`, { responseType: "blob", timeout: 60000 });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a"); link.href = url; link.download = "sherlock-cfo-response.pdf";
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setError("Export failed. Your answer is still saved here."); }
    finally { setBusy(false); }
  }
  return <div className="mt-3"><button className="border border-line bg-white px-3 py-2 text-xs font-semibold disabled:opacity-40" disabled={busy} onClick={() => void download()}>{busy ? "Preparing…" : "Download response PDF"}</button>{error && <p role="alert" className="mt-2 text-xs text-red-700">{error}</p>}</div>;
}

function Question({
  question,
  busy,
  onDecide,
}: {
  question: Escalation;
  busy: boolean;
  onDecide: (decision: "approved" | "rejected") => void;
}) {
  return (
    <div className="mt-3 border border-amber-300 bg-amber-50 p-4">
      <p className="text-[13px] font-semibold">
        {typeof question.agent === "string" ? question.agent : question.agent?.name ?? question.agent?.id ?? "An agent"} stopped for you
      </p>
      <p className="mt-1 text-[14px]">{question.title ?? question.summary}</p>
      {(question.reasons ?? []).length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px]">
          {(question.reasons ?? []).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button primary disabled={busy} onClick={() => onDecide("approved")}>
          {busy ? "Recording…" : "Approve"}
        </Button>
        <Button disabled={busy} onClick={() => onDecide("rejected")}>
          Reject
        </Button>
      </div>
      <p className="mt-3 text-[12.5px] text-ink-dim">
        Deciding this resumes the run from where it stopped. Nothing is posted, paid or
        sent either way, and what you decide here is what a later period will be shown.
      </p>
    </div>
  );
}
