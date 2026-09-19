"use client";

import { useState } from "react";
import { useData } from "@/lib/data";
import type { Column, Task } from "@/lib/types";
import { duration } from "@/lib/format";
import { AgentAvatar, PageHeader, Pill, ProgressBar, Pulse } from "@/components/ui";
import { TaskDrawer } from "@/components/board/TaskDrawer";

const COLUMNS: { id: Column; label: string }[] = [
  { id: "queued", label: "Queued" },
  { id: "working", label: "Working" },
  { id: "needs_you", label: "Needs you" },
  { id: "auditor_review", label: "Auditor review" },
  { id: "done", label: "Done" },
];

export default function BoardPage() {
  const { bundle } = useData();
  const [openId, setOpenId] = useState<string | null>(null);
  const open = bundle.tasks.find((t) => t.id === openId) ?? null;

  return (
    <>
      <PageHeader
        title="Agent board"
        subtitle="Every task the agents are running. Click a card for its steps, progress and to-dos."
      />
      <div className="grid grid-cols-2 items-start gap-2 lg:grid-cols-5">
        {COLUMNS.map((col) => {
          const tasks = bundle.tasks.filter((t) => t.column === col.id);
          return (
            <div key={col.id} className="min-h-[430px] rounded-[10px] bg-slate-100 p-2">
              <div className="mx-0.5 mb-2 flex items-center gap-1.5 text-[11.5px] font-semibold">
                {col.id === "working" && <Pulse />}
                {col.label}
                <span className="ml-auto font-normal text-slate-500">{tasks.length}</span>
              </div>
              {tasks.map((t) => (
                <TaskCard key={t.id} task={t} onOpen={() => setOpenId(t.id)} />
              ))}
            </div>
          );
        })}
      </div>
      <TaskDrawer task={open} onClose={() => setOpenId(null)} />
    </>
  );
}

function TaskCard({ task, onOpen }: { task: Task; onOpen: () => void }) {
  const current = task.steps.find((s) => s.state === "running");
  const isDone = task.column === "done";
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`mb-1.5 block w-full cursor-pointer rounded-lg border border-line bg-white p-2 text-left transition hover:border-teal-400 hover:shadow-[0_2px_8px_rgba(15,118,110,0.12)] ${
        isDone ? "opacity-75" : ""
      }`}
    >
      <div className="flex items-center gap-1.5">
        <AgentAvatar id={task.agent} size="sm" />
        <span className="truncate text-[10.5px] text-slate-500">{task.id}</span>
        {task.column === "working" && task.eta_s != null && (
          <span className="ml-auto text-[10px] text-slate-500">~{duration(task.eta_s)}</span>
        )}
        {isDone && <span className="ml-auto text-[10px] font-bold text-green-700">✓</span>}
      </div>
      <div className={`mb-1 mt-1 text-[11.5px] ${isDone ? "font-medium" : "font-semibold"}`}>{task.title}</div>
      {current && <div className="mb-1.5 shimmer-text text-[10.5px]">{current.title}…</div>}
      {task.note && !current && (
        <div className="mb-1">
          <Pill tone={task.note_tone === "warn" ? "amber" : task.note_tone === "info" ? "teal" : "gray"}>{task.note}</Pill>
        </div>
      )}
      {!isDone && task.progress > 0 && (
        <div className="flex items-center gap-1.5">
          <ProgressBar value={task.progress} className="h-1.5 flex-1" />
          <span className="text-[10.5px] tabular-nums text-slate-500">{task.progress}%</span>
        </div>
      )}
    </button>
  );
}
