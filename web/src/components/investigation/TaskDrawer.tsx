"use client";

import { useEffect } from "react";
import Link from "next/link";

import { AGENT_NAME, AgentAvatar, Pill, ProgressBar, Pulse } from "@/components/ui";
import { duration, elapsedSeconds } from "@/lib/format";
import type { Column, Task } from "@/lib/types";

const DISPOSITION_LABEL: Record<string, string> = {
  clear: "Nothing here needs a person",
  exception: "Exception raised",
  insufficient_evidence: "Not enough evidence to conclude",
};

const DISPOSITION_TONE: Record<string, "green" | "red" | "amber"> = {
  clear: "green",
  exception: "red",
  insufficient_evidence: "amber",
};

const VERDICT_LABEL: Record<string, string> = {
  accepted: "Accepted by the reviewer",
  rejected: "Rejected by the reviewer",
  needs_evidence: "Reviewer wants more evidence",
  not_reviewed: "Not reviewed",
};

const VERDICT_TONE: Record<string, "green" | "red" | "amber" | "gray"> = {
  accepted: "green",
  rejected: "red",
  needs_evidence: "amber",
  not_reviewed: "gray",
};

const COLUMN_LABEL: Record<Column, string> = {
  queued: "Queued",
  working: "Working",
  auditor_review: "Auditor review",
  needs_you: "Needs you",
  done: "Done",
};

/** The wall-clock time a task started, or null when the run recorded none. */
function startedAtLabel(startedAt: string | null): string | null {
  if (!startedAt) return null;
  const started = Date.parse(startedAt);
  if (Number.isNaN(started)) return null;
  return new Date(started).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/**
 * One task, opened out: the steps it has taken, what it still owes, and the
 * clock against it. This is the workflow the board only summarises, and every
 * line of it is a field the run emitted.
 */
export function TaskDrawer({ task, now, onClose }: { task: Task | null; now: number | null; onClose: () => void }) {
  useEffect(() => {
    if (!task) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [task, onClose]);

  if (!task) return null;

  const doneSteps = task.steps.filter((step) => step.state === "done").length;
  const detail = task.detail ?? null;
  const output = detail?.result && Object.keys(detail.result).length > 0 ? detail.result : null;
  const review = detail?.review ?? null;
  const resolution = detail?.resolution ?? null;
  const running = task.column === "working" || task.column === "auditor_review";
  const seconds = elapsedSeconds(task.started_at, now);
  const started = startedAtLabel(task.started_at);

  return (
    <>
      <div className="fixed inset-0 z-30 animate-fade-in bg-ink/30" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${task.id}: ${task.title}`}
        className="fixed inset-y-0 right-0 z-40 flex w-[440px] max-w-[92vw] animate-slide-in flex-col border-l border-line bg-surface shadow-[-12px_0_30px_rgb(9_9_11_/_0.14)]"
      >
        <div className="border-b border-line px-4 py-3.5">
          <button
            type="button"
            onClick={onClose}
            aria-label="Close (Esc)"
            title="Close (Esc)"
            className="float-right cursor-pointer px-1 text-base text-ink-faint hover:text-ink"
          >
            ✕
          </button>

          <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
            <AgentAvatar id={task.agent} size="sm" />
            <b className="text-[14px]">{AGENT_NAME[task.agent]}</b>
            <Pill tone={task.column === "needs_you" ? "red" : task.column === "done" ? "green" : "gray"}>
              {running && <Pulse />}
              {COLUMN_LABEL[task.column]}
            </Pill>
          </div>
          <p className="mt-1 font-accent text-[13px] text-ink-dim">Run {task.workflow} · {task.id}</p>

          <h3 className="my-2 text-[17px] font-semibold leading-snug tracking-tight">{task.title}</h3>

          <div className="flex items-center gap-2">
            <ProgressBar value={task.progress} className="h-2 flex-1" />
            <b className="font-num text-[13px] tabular-nums">{task.progress}%</b>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-4">
            {task.steps.length > 0 && (
              <Stat label="Step" value={`${Math.min(doneSteps + 1, task.steps.length)} of ${task.steps.length}`} />
            )}
            {/* Nothing is shown when the run recorded no start: a zero would read as "just started". */}
            {seconds !== null && <Stat label="Since start" value={duration(seconds)} />}
            {started && <Stat label="Started" value={started} />}
            <Stat label="Tool calls" value={`${task.tool_calls.used} / ${task.tool_calls.budget}`} />
          </div>

          {task.note && (
            <div className="mt-3">
              <Pill tone={task.note_tone === "warn" ? "red" : "gray"}>{task.note}</Pill>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-auto px-4 py-3.5">
          {task.steps.length > 0 && (
            <>
              <Heading>Steps</Heading>
              {task.steps.map((step, index) => (
                <div key={index} className="grid grid-cols-[18px_1fr] gap-2 py-1.5">
                  <span
                    className={`flex h-[18px] w-[18px] items-center justify-center text-[11px] font-bold ${
                      step.state === "done"
                        ? "bg-surface-2 text-ink"
                        : step.state === "running"
                          ? "animate-ping-soft bg-ink text-white"
                          : "bg-surface-2 text-ink-faint"
                    }`}
                  >
                    {step.state === "done" ? "✓" : step.state === "running" ? "●" : ""}
                  </span>
                  <div>
                    <div className={`text-[13.5px] font-medium leading-snug ${step.state === "todo" ? "text-ink-dim" : ""}`}>
                      {step.title}
                    </div>
                    {step.detail && <div className="mt-0.5 font-mono text-[12px] leading-relaxed text-ink-dim">{step.detail}</div>}
                    {step.at && <div className="mt-0.5 font-num text-[11.5px] tabular-nums text-ink-faint">{stamp(step.at)}</div>}
                  </div>
                </div>
              ))}
            </>
          )}

          {task.todos.length > 0 && (
            <>
              <Heading className="mt-5">Still owed</Heading>
              {task.todos.map((todo) => (
                <div key={todo} className="flex items-start gap-2 py-1.5 text-[13.5px] leading-snug">
                  <i aria-hidden="true" className="mt-[3px] h-3 w-3 flex-none border-[1.5px] border-line" />
                  {todo}
                </div>
              ))}
            </>
          )}

          {task.rationale && (
            <>
              <Heading className="mt-5">What it concluded</Heading>
              <p className="border border-line bg-surface-2 px-3 py-2.5 text-[13.5px] leading-relaxed">{task.rationale}</p>
            </>
          )}

          {/* The output, whole. A finished task that shows only a headline sends a
              person to the database for the work they just paid for. */}
          {output && (
            <>
              <Heading className="mt-5">What it produced</Heading>
              {output.disposition && (
                <div className="mb-2">
                  <Pill tone={DISPOSITION_TONE[output.disposition] ?? "gray"}>
                    {DISPOSITION_LABEL[output.disposition] ?? output.disposition}
                  </Pill>
                </div>
              )}
              {output.summary && <p className="text-[13.5px] leading-relaxed">{output.summary}</p>}

              {output.proposed_action && (
                <>
                  <Heading className="mt-4">What it proposes</Heading>
                  <p className="border border-line bg-surface-2 px-3 py-2.5 text-[13.5px] leading-relaxed">
                    {output.proposed_action}
                  </p>
                  <p className="mt-1 font-accent text-[12px] text-ink-dim">
                    A proposal. Nothing an agent can call approves, posts or pays anything.
                  </p>
                </>
              )}

              {(output.exceptions?.length ?? 0) > 0 && (
                <>
                  <Heading className="mt-4">What did not hold</Heading>
                  {output.exceptions?.map((exception) => (
                    <div key={exception.code + exception.detail} className="border border-line bg-surface-2 px-3 py-2 mb-1.5">
                      <div className="font-mono text-[12px] text-red-800">{exception.code}</div>
                      <div className="mt-0.5 text-[13px] leading-snug">{exception.detail}</div>
                    </div>
                  ))}
                </>
              )}

              {(output.citations?.length ?? 0) > 0 && (
                <>
                  <Heading className="mt-4">What it rests on</Heading>
                  {output.citations?.map((citation, index) => (
                    <div key={index} className="border-b border-line py-1.5 text-[13px] last:border-0">
                      <span className="font-mono text-[12px] text-ink-dim">{citation.role}</span>{" "}
                      <span className="font-mono text-[12px]">{citation.record_key || citation.source_id}</span>
                      {citation.line ? <span className="font-num text-[12px] text-ink-dim"> · line {citation.line}</span> : null}
                      {citation.note && <div className="mt-0.5 leading-snug text-ink-dim">{citation.note}</div>}
                    </div>
                  ))}
                </>
              )}

              {(output.open_questions?.length ?? 0) > 0 && (
                <>
                  <Heading className="mt-4">What it could not settle</Heading>
                  {output.open_questions?.map((question) => (
                    <div key={question} className="border-b border-line py-1.5 text-[13px] leading-snug last:border-0">
                      {question}
                    </div>
                  ))}
                </>
              )}

              {(output.memory_checks?.length ?? 0) > 0 && (
                <>
                  <Heading className="mt-4">Earlier decisions it re-checked</Heading>
                  {output.memory_checks?.map((check) => (
                    <div key={check.precedent_id} className="border-b border-line py-1.5 text-[13px] leading-snug last:border-0">
                      <b className="font-mono text-[12px]">{check.precedent_id}</b>{" "}
                      <span className={check.applied ? "text-green-800" : "text-ink-dim"}>
                        {check.applied ? "applied" : "declined"}
                      </span>
                      <div className="text-ink-dim">{check.reason}</div>
                    </div>
                  ))}
                </>
              )}
            </>
          )}

          {resolution && (
            <>
              <Heading className="mt-5">Your decision</Heading>
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone={resolution.decision === "approved" ? "green" : "red"}>
                  {resolution.decision === "approved" ? "Approved" : "Rejected"}
                </Pill>
                <span className="text-[13px] text-ink-dim">
                  by {resolution.by} at {stamp(resolution.at)}
                </span>
              </div>
              <p className="mt-1 font-accent text-[12px] text-ink-dim">
                Recorded as your judgement, and written as precedent the next run has to
                re-check. It posts nothing, pays nothing and changes no external system.
              </p>
            </>
          )}

          {review && (
            <>
              <Heading className="mt-5">Independent review</Heading>
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone={VERDICT_TONE[review.verdict] ?? "gray"}>{VERDICT_LABEL[review.verdict] ?? review.verdict}</Pill>
                <span className="text-[13px] text-ink-dim">by {review.reviewer_name ?? review.reviewer}</span>
              </div>
              {review.summary && <p className="mt-2 text-[13.5px] leading-relaxed">{review.summary}</p>}
              {review.rationale && <p className="mt-1.5 text-[13px] leading-relaxed text-ink-dim">{review.rationale}</p>}
              <p className="mt-1 font-accent text-[12px] text-ink-dim">
                A reviewer accepting the work is not a person approving it.
              </p>
            </>
          )}

          {/* A finished card was a dead end: the conclusion went into the briefing and
              the trail, and nothing on the board said so. */}
          {(task.column === "done" || task.column === "needs_you") && (
            <>
              <Heading className="mt-5">Where this went</Heading>
              <ul className="space-y-1 text-[13.5px] leading-relaxed">
                <li>
                  <Link href="/briefing" className="underline underline-offset-4">
                    The briefing
                  </Link>{" "}
                  — this conclusion, its evidence and its next step, with a copy to download.
                </li>
                <li>
                  <Link href="/investigation" className="underline underline-offset-4">
                    Investigation
                  </Link>{" "}
                  — the finding, the reasoning log, and anything still waiting on you.
                </li>
              </ul>
            </>
          )}

          {/* Everything else the run recorded. A person who opens a card should not
              have to go anywhere else to find out what this agent is, what it was
              asked, what it spent or what stopped it. */}
          {detail && (
            <>
              <Heading className="mt-5">This agent</Heading>
              <p className="text-[13.5px] leading-relaxed">{detail.charter}</p>
              <dl className="mt-2 border border-line bg-surface-2 text-[13px]">
                <Row label="Reports to" value={detail.parent ?? "Nobody — it routes the work"} />
                <Row label="Reviewed by" value={detail.reviewer ?? "Not independently reviewed"} />
                <Row label="Model" value={detail.model} />
                <Row label="Level" value={detail.tier} />
              </dl>

              <Heading className="mt-5">What it was asked</Heading>
              <p className="whitespace-pre-wrap border border-line bg-surface-2 px-3 py-2.5 text-[13.5px] leading-relaxed">
                {detail.objective || "No objective was recorded."}
              </p>

              <Heading className="mt-5">What it spent</Heading>
              <dl className="border border-line bg-surface-2 text-[13px]">
                <Row label="Tool calls" value={`${task.tool_calls.used} of ${task.tool_calls.budget}`} />
                <Row label="Model calls" value={`${detail.model_calls} of ${detail.model_budget}`} />
                <Row label="Cost" value={`${money(detail.cost_cents)} of ${money(detail.cost_budget_cents)}`} />
                {detail.confidence !== null && (
                  <Row label="Confidence" value={`${detail.confidence}% — computed by the engine, not stated by the model`} />
                )}
              </dl>

              {detail.escalation_reasons.length > 0 && (
                <>
                  <Heading className="mt-5">Why a person is needed</Heading>
                  {detail.escalation_reasons.map((reason) => (
                    <div key={reason} className="border-b border-line py-1.5 font-mono text-[12.5px] last:border-0">
                      {reason}
                    </div>
                  ))}
                </>
              )}

              {detail.error && (
                <>
                  <Heading className="mt-5">Why it stopped</Heading>
                  <p className="border border-line bg-surface-2 px-3 py-2.5 font-mono text-[12.5px] leading-relaxed">
                    {detail.error}
                  </p>
                </>
              )}

              <Heading className="mt-5">On the record</Heading>
              <dl className="border border-line bg-surface-2 text-[13px]">
                <Row label="Run" value={detail.thread_id} />
                <Row label="Task" value={task.id} />
                {task.decision_id && <Row label="Decision" value={task.decision_id} />}
                {task.approval_id && <Row label="Awaiting approval" value={task.approval_id} />}
                <Row label="Delegated" value={stamp(detail.created_at)} />
                {detail.started_at && <Row label="Started" value={stamp(detail.started_at)} />}
                <Row label="Last step" value={stamp(detail.updated_at)} />
                {detail.finished_at && <Row label="Finished" value={stamp(detail.finished_at)} />}
              </dl>
            </>
          )}
        </div>
      </aside>
    </>
  );
}

const money = (cents: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);

/** A recorded instant, in the reader's own clock. Unparseable text is shown as it was. */
function stamp(value: string): string {
  const moment = Date.parse(value);
  return Number.isNaN(moment) ? value : new Date(moment).toLocaleTimeString([], {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3 border-b border-line px-3 py-1.5 last:border-0">
      <dt className="w-32 flex-none text-ink-dim">{label}</dt>
      <dd className="min-w-0 break-words">{value}</dd>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface px-2.5 py-2">
      <small className="block text-[11.5px] text-ink-dim">{label}</small>
      <b className="font-num text-[14px] tabular-nums">{value}</b>
    </div>
  );
}

function Heading({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`mb-1.5 text-[11.5px] font-semibold uppercase tracking-wider text-ink-faint ${className}`}>
      {children}
    </div>
  );
}
