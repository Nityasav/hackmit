"use client";

import { useEffect } from "react";

import { AGENT_NAME, AgentAvatar, Pill, ProgressBar, Pulse } from "@/components/ui";
import { duration, elapsedSeconds } from "@/lib/format";
import type { Column, Task } from "@/lib/types";
import { useData } from "@/lib/data";
import { TaskDeliverable } from "./TaskDeliverable";

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
  const { ws } = useData();
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
        className="fixed inset-y-0 right-0 z-40 flex w-[680px] max-w-[96vw] animate-slide-in flex-col border-l border-line bg-surface shadow-[-12px_0_30px_rgb(9_9_11_/_0.14)]"
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
          <p className="mt-1 break-all text-xs text-ink-dim">Run {task.workflow}</p>

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
          {task.id.startsWith("task-decision-") && <TaskDeliverable key={`${ws}-${task.id}`} ws={ws} decision={task.id.slice(5)} />}
          <details><summary className="cursor-pointer text-sm font-semibold">Task execution details</summary>
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
              <Heading className="mt-5">Recorded rationale</Heading>
              <p className="border border-line bg-surface-2 px-3 py-2.5 text-[13.5px] leading-relaxed">{task.rationale}</p>
            </>
          )}
          </details>
        </div>
      </aside>
    </>
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
