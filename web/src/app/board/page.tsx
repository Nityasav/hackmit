"use client";

import { useState } from "react";
import { useData } from "@/lib/data";
import type { Column, Task } from "@/lib/types";
import { duration } from "@/lib/format";
import { AGENT_NAME, AgentAvatar, PageHeader, Pill, ProgressBar, Pulse } from "@/components/ui";
import { TaskDrawer } from "@/components/board/TaskDrawer";

const COLUMNS: { id: Column; label: string }[] = [
  { id: "queued", label: "Queued" },
  { id: "working", label: "Working" },
  { id: "needs_you", label: "Needs you" },
  { id: "auditor_review", label: "Auditor review" },
  { id: "done", label: "Done" },
];

const EMPTY_COLUMN: Record<Column, string> = {
  queued: "Nothing waiting",
  working: "No agent is running right now",
  needs_you: "You're all caught up",
  auditor_review: "Nothing to re-check",
  done: "Nothing finished yet",
};

export default function BoardPage() {
  const { bundle } = useData();
  const [openId, setOpenId] = useState<string | null>(null);
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const open = bundle.tasks.find((t) => t.id === openId) ?? null;
  const visible = bundle.tasks.filter((t) => agentFilter === "all" || t.agent === agentFilter);

  return (
    <>
      <PageHeader
        title="Agent board"
        subtitle="Every task the agents are running. Click a card for its steps, progress and to-dos."
        right={
          <div className="flex flex-wrap items-center gap-1">
            <FilterChip active={agentFilter === "all"} onClick={() => setAgentFilter("all")}>
              All agents
            </FilterChip>
            {bundle.agents.map((a) => (
              <FilterChip key={a.id} active={agentFilter === a.id} onClick={() => setAgentFilter(a.id)}>
                <AgentAvatar id={a.id} size="sm" />
                <span className="hidden xl:inline">{AGENT_NAME[a.id]}</span>
              </FilterChip>
            ))}
          </div>
        }
      />
      <div className="grid grid-cols-2 items-start gap-2 lg:grid-cols-5">
        {COLUMNS.map((col) => {
          const tasks = visible.filter((t) => t.column === col.id);
          return (
            <section key={col.id} aria-label={col.label} className="min-h-[430px] rounded-[10px] bg-surface-2 p-2">
              <div className="sticky top-0 z-[1] mx-0.5 mb-2 flex items-center gap-2 rounded bg-surface-2 py-0.5 text-[13.5px] font-semibold">
                {col.id === "working" && <Pulse />}
                {col.label}
                <span className="ml-auto font-normal text-ink-dim tabular-nums">{tasks.length}</span>
              </div>
              {tasks.length === 0 ? (
                <div className="rounded-lg border border-dashed border-line px-2 py-6 text-center text-[12.5px] text-ink-faint">
                  {EMPTY_COLUMN[col.id]}
                </div>
              ) : (
                tasks.map((t) => <TaskCard key={t.id} task={t} onOpen={() => setOpenId(t.id)} />)
              )}
            </section>
          );
        })}
      </div>
      <TaskDrawer task={open} onClose={() => setOpenId(null)} />
    </>
  );
}

function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`flex cursor-pointer items-center gap-1 rounded-full border px-2 py-1 text-[13px] transition ${
        active ? "border-surface-3 bg-surface-2 text-white" : "border-line bg-surface text-ink-dim hover:border-ink"
      }`}
    >
      {children}
    </button>
  );
}

function TaskCard({ task, onOpen }: { task: Task; onOpen: () => void }) {
  const current = task.steps.find((s) => s.state === "running");
  const isDone = task.column === "done";
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`mb-1.5 block w-full cursor-pointer rounded-lg border border-line bg-surface p-2 text-left transition hover:border-ink hover:shadow-[0_1px_3px_rgba(0,0,0,0.08)] ${
        isDone ? "opacity-75" : ""
      }`}
    >
      <div className="flex items-center gap-2">
        <AgentAvatar id={task.agent} size="sm" />
        <span className="truncate text-[12.5px] text-ink-dim">{task.id}</span>
        {task.column === "working" && task.eta_s != null && (
          <span className="ml-auto text-[12px] text-ink-dim">~{duration(task.eta_s)}</span>
        )}
        {isDone && <span className="ml-auto text-[12px] font-bold text-ink">✓</span>}
      </div>
      <div className={`mb-1 mt-1 text-[13.5px] ${isDone ? "font-medium" : "font-semibold"}`}>{task.title}</div>
      {current && <div className="mb-1.5 shimmer-text text-[12.5px]">{current.title}…</div>}
      {task.note && !current && (
        <div className="mb-1">
          <Pill tone={task.note_tone === "warn" ? "amber" : task.note_tone === "info" ? "teal" : "gray"}>{task.note}</Pill>
        </div>
      )}
      {!isDone && task.progress > 0 && (
        <div className="flex items-center gap-2">
          <ProgressBar value={task.progress} className="h-1.5 flex-1" />
          <span className="text-[12.5px] tabular-nums text-ink-dim">{task.progress}%</span>
        </div>
      )}
    </button>
  );
}
