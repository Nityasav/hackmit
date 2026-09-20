"use client";

import Link from "next/link";
import { useState } from "react";

import { useData } from "@/lib/data";
import type { Column, Task } from "@/lib/types";
import { duration } from "@/lib/format";
import { AGENT_NAME, AgentAvatar, EmptyState, PageHeader, Pill, ProgressBar, Pulse } from "@/components/ui";
import { TaskDrawer } from "@/components/board/TaskDrawer";

/** Left to right, the order work actually moves in. */
const COLUMNS: { id: Column; label: string; note: string }[] = [
  { id: "queued", label: "Queued", note: "Delegated, not started" },
  { id: "working", label: "Working", note: "Reading evidence" },
  { id: "auditor_review", label: "Auditor review", note: "Being re-checked independently" },
  { id: "needs_you", label: "Needs you", note: "Blocked on a human" },
  { id: "done", label: "Done", note: "Finished this run" },
];

export default function BoardPage() {
  const { bundle } = useData();
  const [openId, setOpenId] = useState<string | null>(null);
  const open = bundle.tasks.find((t) => t.id === openId) ?? null;

  return (
    <>
      <PageHeader
        title="Agent board"
        subtitle="Every task an agent is running. A card's column is derived from what the agent is actually doing, so it is not something you can drag."
      />

      {bundle.tasks.length === 0 ? (
        <EmptyState icon="○" title="No tasks yet">
          Tasks appear here once an investigation runs. Start one from the Command center.
        </EmptyState>
      ) : (
        <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-5 [&>*]:min-w-0">
          {COLUMNS.map((column) => {
            const tasks = bundle.tasks.filter((t) => t.column === column.id);
            return (
              <section key={column.id} className="border border-line bg-surface-2 p-2">
                <div className="mb-2 flex items-baseline gap-2">
                  <b className="text-[13.5px]">{column.label}</b>
                  <span className="font-num tabular-nums text-[13px] text-ink-dim">{tasks.length}</span>
                </div>
                <div className="mb-2 text-[12px] text-ink-faint">{column.note}</div>
                {tasks.map((task) => (
                  <TaskCard key={task.id} task={task} onOpen={() => setOpenId(task.id)} />
                ))}
                {tasks.length === 0 && (
                  <div className="border border-dashed border-line px-2 py-3 text-center text-[12px] text-ink-faint">
                    Nothing here
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}

      <TaskDrawer task={open} onClose={() => setOpenId(null)} />
    </>
  );
}

function TaskCard({ task, onOpen }: { task: Task; onOpen: () => void }) {
  const running = task.column === "working" || task.column === "auditor_review";
  const budget = task.tool_calls.budget;

  return (
    <div className="mb-2 border border-line bg-surface">
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Open ${task.id}: ${task.title}`}
        className="w-full cursor-pointer px-2 py-2.5 text-left transition hover:bg-surface-2"
      >
        <div className="flex items-center gap-2">
          <AgentAvatar id={task.agent} size="sm" />
          <span className="truncate text-[12px] text-ink-dim">{AGENT_NAME[task.agent]}</span>
          {running && <Pulse className="ml-auto" />}
        </div>

        <div className="mt-1.5 line-clamp-3 text-[13.5px] font-medium">{task.title}</div>

        {/* A progress bar on a queued task would imply work that has not happened. */}
        {task.column !== "queued" && (
          <div className="mt-2 flex items-center gap-2">
            <ProgressBar value={task.progress} className="h-1.5 flex-1" />
            <span className="font-num tabular-nums text-[12px] text-ink-dim">{task.progress}%</span>
          </div>
        )}

        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-ink-faint">
          <span className="font-num tabular-nums" title="Evidence tool calls used of this task's budget">
            {task.tool_calls.used}/{budget} tools
          </span>
          {running && task.eta_s !== null && <span className="font-num tabular-nums">~{duration(task.eta_s)}</span>}
          {task.todos.length > 0 && <span>{task.todos.length} to-do</span>}
        </div>

        {task.note && (
          <div className="mt-1.5">
            <Pill tone={task.note_tone === "warn" ? "amber" : "gray"}>{task.note}</Pill>
          </div>
        )}
      </button>

      {/* The one place a card is more than a card: where it hands off to you. */}
      {task.column === "needs_you" && (
        <div className="border-t border-line px-2 py-1.5 text-[12px]">
          {task.approval_id ? (
            <Link href="/approvals" className="font-semibold text-ink underline">
              Decide {task.approval_id} in Approvals →
            </Link>
          ) : (
            <span className="text-ink-dim">
              Waiting on evidence, not on a decision. Open the task for what it asked for.
            </span>
          )}
        </div>
      )}
      {task.column === "auditor_review" && (
        <div className="border-t border-line px-2 py-1.5 text-[12px] text-ink-dim">
          The Internal Auditor is re-reading the sources and redoing the math.
        </div>
      )}
    </div>
  );
}
