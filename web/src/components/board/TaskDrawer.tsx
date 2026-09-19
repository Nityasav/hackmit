"use client";

import Link from "next/link";
import { useEffect } from "react";
import type { Task } from "@/lib/types";
import { duration } from "@/lib/format";
import { AGENT_NAME, AgentAvatar, Button, Pill, ProgressBar } from "@/components/ui";

const COLUMN_LABEL = {
  queued: "Queued",
  working: "Working",
  needs_you: "Needs you",
  auditor_review: "Auditor review",
  done: "Done",
} as const;

export function TaskDrawer({ task, onClose }: { task: Task | null; onClose: () => void }) {
  useEffect(() => {
    if (!task) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [task, onClose]);

  if (!task) return null;
  const doneSteps = task.steps.filter((s) => s.state === "done").length;
  const running = task.column === "working" || task.column === "auditor_review";

  return (
    <>
      <div className="fixed inset-0 z-10 animate-fade-in bg-slate-900/10" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${task.id}: ${task.title}`}
        className="fixed inset-y-0 right-0 z-20 flex w-[440px] max-w-[92vw] animate-slide-in flex-col border-l border-line bg-white shadow-[-12px_0_30px_rgba(15,23,42,0.12)]"
      >
        <div className="border-b border-slate-100 px-4 py-3.5">
          <button
            type="button"
            onClick={onClose}
            aria-label="Close (Esc)"
            title="Close (Esc)"
            className="float-right cursor-pointer rounded px-1 text-base text-slate-400 hover:text-slate-700"
          >
            ✕
          </button>
          <div className="flex items-center gap-1.5">
            <AgentAvatar id={task.agent} size="sm" />
            <b className="text-[12.5px]">{AGENT_NAME[task.agent]}</b>
            <Pill tone={running ? "teal" : task.column === "needs_you" ? "amber" : "gray"}>{COLUMN_LABEL[task.column]}</Pill>
            <span className="text-[11px] text-slate-500">· {task.workflow} workflow</span>
          </div>
          <div className="my-1.5 text-[15px] font-bold">{task.title}</div>
          <div className="flex items-center gap-2">
            <ProgressBar value={task.progress} className="h-2 flex-1" />
            <b className="tabular-nums">{task.progress}%</b>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            <Stat label="Step" value={`${Math.min(doneSteps + 1, task.steps.length)} of ${task.steps.length}`} />
            <Stat label={running ? "Done in" : "Started"} value={running ? `~${duration(task.eta_s)}` : (task.started_at ?? "—")} />
            <Stat label="Tool budget" value={`${task.tool_calls.used} / ${task.tool_calls.budget}`} />
          </div>
        </div>

        <div className="flex-1 overflow-auto px-4 py-3">
          <Section>Steps</Section>
          {task.steps.map((s, i) => (
            <div key={i} className="grid grid-cols-[20px_1fr] gap-2 py-1">
              <span
                className={`flex h-[18px] w-[18px] items-center justify-center rounded-full text-[10px] font-bold ${
                  s.state === "done"
                    ? "bg-green-100 text-green-800"
                    : s.state === "running"
                      ? "animate-ping-soft bg-teal-500 text-white"
                      : "bg-slate-100 text-slate-400"
                }`}
              >
                {s.state === "done" ? "✓" : s.state === "running" ? "●" : ""}
              </span>
              <div>
                <div className={`text-[11.5px] font-medium ${s.state === "todo" ? "text-slate-500" : ""}`}>{s.title}</div>
                {s.detail && (
                  <div className={`font-mono text-[10.5px] ${s.memory ? "text-amber-700" : "text-slate-500"}`}>{s.detail}</div>
                )}
              </div>
            </div>
          ))}

          {task.todos.length > 0 && (
            <>
              <Section className="mt-3">Agent to-dos</Section>
              {task.todos.map((t) => (
                <div key={t} className="flex items-start gap-2 py-1 text-[11.5px]">
                  <i className="mt-0.5 h-3 w-3 flex-none rounded border-[1.5px] border-slate-300" />
                  {t}
                </div>
              ))}
            </>
          )}

          {task.rationale && (
            <>
              <Section className="mt-3">Why (decision rationale)</Section>
              <div className="rounded-lg border border-teal-100 bg-teal-50 px-2.5 py-2 text-[11.5px]">{task.rationale}</div>
            </>
          )}

          <div className="mt-3 flex flex-wrap gap-1.5">
            <Button disabled title="Wired to the orchestrator in the live build">⏸ Pause</Button>
            {task.approval_id && (
              <Link href="/approvals">
                <Button primary>Open in Approvals</Button>
              </Link>
            )}
            <Link href={`/reasoning?q=${encodeURIComponent(task.id)}`}>
              <Button>Open in Reasoning log</Button>
            </Link>
          </div>
        </div>
      </aside>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[7px] bg-slate-50 px-2 py-1.5">
      <small className="block text-[10px] text-slate-500">{label}</small>
      <b className="text-[13px] tabular-nums">{value}</b>
    </div>
  );
}

function Section({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400 ${className}`}>{children}</div>
  );
}
