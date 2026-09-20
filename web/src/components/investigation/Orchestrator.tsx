"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, intakeApi } from "@/lib/api";
import { Button, Pill } from "@/components/ui";
import type { ChatReply, ChatTurn, Escalation } from "@/lib/types";

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
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [deciding, setDeciding] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const body = await intakeApi<{ turns: ChatTurn[] }>(`/api/workspaces/${ws}/chat`);
    setTurns(body.turns);
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

  async function send() {
    const message = draft.trim();
    if (!message || busy) return;
    setBusy(true);
    setError("");
    setDraft("");
    try {
      await intakeApi(`/api/workspaces/${ws}/chat`, {
        method: "POST",
        body: { message, thread_id: thread },
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

  async function decide(threadId: string, approvalId: string, decision: "approved" | "rejected") {
    setDeciding(approvalId);
    setError("");
    try {
      await intakeApi(`/api/workspaces/${ws}/agents/escalations/decide`, {
        method: "POST",
        body: { thread_id: threadId, approval_id: approvalId, decision },
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
      <header className="border-b border-line px-5 py-4">
        <h2 className="text-[15px] font-semibold">Ask the Chief Financial Agent</h2>
        <p className="mt-1 text-[13.5px] text-ink-dim">
          It routes what you ask to the domains it touches and hands back what each one
          concluded. It cannot approve, post or pay anything.
        </p>
      </header>

      <div className="max-h-[28rem] space-y-4 overflow-y-auto px-5 py-5">
        {turns.length === 0 && (
          <p className="text-[13.5px] text-ink-dim">
            Nothing has been asked about this company yet. Try &ldquo;Can we close the
            period?&rdquo; or &ldquo;Review the payables and the bank.&rdquo;
          </p>
        )}
        {turns.map((turn) =>
          turn.role === "person" ? (
            <p key={turn.id} className="ml-auto max-w-[80%] border border-ink bg-ink px-4 py-3 text-[14px] text-white">
              {turn.body.text}
            </p>
          ) : (
            <Reply
              key={turn.id}
              turn={turn}
              deciding={deciding}
              onDecide={(approvalId, decision) => void decide(turn.thread_id, approvalId, decision)}
            />
          ),
        )}
        {busy && <p className="text-[13.5px] text-ink-dim">The organization is working. This costs money and is not instant.</p>}
        <div ref={bottom} />
      </div>

      {error && (
        <p role="alert" className="mx-5 mb-4 border border-red-300 bg-red-50 p-3 text-[13.5px] text-red-800">
          {error}
        </p>
      )}

      <div className="flex items-end gap-3 border-t border-line px-5 py-4">
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
          placeholder="What should the organization look at?"
          className="min-h-16 flex-1 resize-y border border-line bg-white px-3 py-2 text-[14px]"
          aria-label="Ask the orchestrator"
        />
        <Button primary disabled={busy || !draft.trim()} onClick={() => void send()}>
          {busy ? "Running…" : "Ask"}
        </Button>
      </div>
    </section>
  );
}

function Reply({
  turn,
  deciding,
  onDecide,
}: {
  turn: ChatTurn;
  deciding: string;
  onDecide: (approvalId: string, decision: "approved" | "rejected") => void;
}) {
  const body = turn.body as ChatReply & { text: string; code?: string };
  const waiting = body.escalations ?? [];
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

      <p className="mt-3 text-[14px] leading-relaxed">{body.text}</p>

      {findings.length > 0 && (
        <ul className="mt-3 space-y-2">
          {findings.map((finding) => (
            <li key={finding.decision_id ?? finding.agent_id} className="border-l-2 border-line pl-3">
              <p className="text-[13px] font-semibold">
                {finding.agent_name}
                {finding.confidence !== null && finding.confidence !== undefined && (
                  <span className="ml-2 font-normal text-ink-dim">
                    confidence {finding.confidence} of 100, computed
                  </span>
                )}
              </p>
              <p className="text-[13.5px]">{finding.summary}</p>
            </li>
          ))}
        </ul>
      )}

      {waiting.map((question) => (
        <Question
          key={question.approval_id}
          question={question}
          busy={deciding === question.approval_id}
          onDecide={(decision) => onDecide(question.approval_id, decision)}
        />
      ))}

      {body.note && <p className="mt-3 text-[12.5px] text-ink-dim">{body.note}</p>}
    </div>
  );
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
        {question.agent} stopped for you
      </p>
      <p className="mt-1 text-[14px]">{question.title ?? question.summary}</p>
      {(question.reasons ?? []).length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px]">
          {question.reasons.map((line) => (
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
