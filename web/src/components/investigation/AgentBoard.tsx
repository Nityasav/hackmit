"use client";

import { useState, useSyncExternalStore } from "react";

import { AGENT_NAME, AgentAvatar, Pill, ProgressBar, Pulse } from "@/components/ui";
import { duration, elapsedSeconds } from "@/lib/format";
import type { Column, Task } from "@/lib/types";

import { useBoard } from "./board";
import { TaskDrawer } from "./TaskDrawer";

/** Left to right, the order work actually moves in. */
const COLUMNS: { id: Column; label: string; note: string }[] = [
  { id: "queued", label: "Queued", note: "Delegated, not started" },
  { id: "working", label: "Working", note: "Reading evidence" },
  { id: "auditor_review", label: "Auditor review", note: "Being re-checked independently" },
  { id: "needs_you", label: "Needs you", note: "Blocked on a human" },
  { id: "done", label: "Done", note: "Finished this run" },
];

/*
 * One second hand for the whole board.
 *
 * Elapsed time has to move, and every card has to measure against the same
 * instant, so a single interval feeds them all. It is read through
 * useSyncExternalStore because the server has no clock: the server snapshot is
 * null, so the markup it sends carries no time at all and hydration cannot
 * disagree with it.
 */
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | undefined;
let instant = 0;

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  instant = Date.now();
  timer ??= setInterval(() => {
    instant = Date.now();
    for (const listener of listeners) listener();
  }, 1000);

  return () => {
    listeners.delete(onChange);
    if (listeners.size === 0 && timer) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

function readInstant(): number {
  if (instant === 0) instant = Date.now();
  return instant;
}

/** The current time in the browser, and null wherever there is no browser. */
function useNow(): number | null {
  return useSyncExternalStore(subscribe, readInstant, () => null);
}

/**
 * The agent board: every task the run handed out, in the column that matches
 * what its agent is doing, with the clock running against it.
 *
 * Nothing here is authored. Each card is one row of `agent_tasks`, which the
 * runtime opens when a task is delegated, appends to on every tool call, and
 * closes with what the task produced. The column, the percentage, the tool
 * count and the start time are all things the run did.
 *
 * It refreshes itself while work is in flight, so a task appears when it is
 * handed out and its steps appear as they land, rather than all at once at the
 * end.
 */
export function AgentBoard({ ws }: { ws: string }) {
  const board = useBoard(ws);
  const now = useNow();
  const [openId, setOpenId] = useState<string | null>(null);
  const open = board.tasks.find((task) => task.id === openId) ?? null;

  if (board.error) {
    return (
      <p className="max-w-prose border border-line bg-surface p-5 text-[14px] leading-relaxed text-ink-dim">
        The board could not be read: {board.error}
      </p>
    );
  }

  if (board.loading && board.tasks.length === 0) {
    return (
      <p className="max-w-prose border border-line bg-surface p-5 text-[14px] leading-relaxed text-ink-dim">
        Reading the board&hellip;
      </p>
    );
  }

  if (board.tasks.length === 0) {
    return (
      <p className="max-w-prose border border-line bg-surface p-5 text-[14px] leading-relaxed text-ink-dim">
        No tasks yet. Ask the organization something on Investigation, or run one agent on its own, and every task it
        hands out appears here as it happens &mdash; in the column that matches what its agent is doing at that moment.
      </p>
    );
  }

  return (
    <>
      <div className="mb-5 flex max-w-prose flex-wrap items-center gap-x-3 gap-y-2">
        <p className="text-[13.5px] leading-relaxed text-ink-dim">
          Every task an agent is running. A card&rsquo;s column is derived from what the agent is actually doing, so it
          is not something you can drag. Each time is counted from the moment that task started.
        </p>
        <span className="flex items-center gap-2 font-accent text-[12.5px] text-ink-dim">
          {board.live ? (
            <>
              <Pulse />
              {board.active} running &middot; refreshing as it happens
            </>
          ) : (
            <>Nothing running. This checks again every few seconds.</>
          )}
        </span>
      </div>

      <div className="grid gap-px border border-line bg-line md:grid-cols-3 xl:grid-cols-5 [&>*]:min-w-0">
        {COLUMNS.map((column) => {
          const tasks = board.tasks.filter((task) => task.column === column.id);
          return (
            <section key={column.id} className="bg-surface-2 p-3">
              <div className="flex items-baseline gap-2">
                <h3 className="text-[13.5px] font-semibold tracking-tight">{column.label}</h3>
                <span className="font-num text-[13px] tabular-nums text-ink-dim">{tasks.length}</span>
              </div>
              <p className="mb-3 mt-1 font-accent text-[12.5px] text-ink-dim">{column.note}</p>

              {tasks.map((task) => (
                <TaskCard key={task.id} task={task} now={now} onOpen={() => setOpenId(task.id)} />
              ))}

              {tasks.length === 0 && (
                <p className="border border-dashed border-line px-2 py-3 text-center text-[12.5px] text-ink-faint">
                  Nothing here
                </p>
              )}
            </section>
          );
        })}
      </div>

      <TaskDrawer task={open} now={now} onClose={() => setOpenId(null)} />
    </>
  );
}

function TaskCard({ task, now, onOpen }: { task: Task; now: number | null; onOpen: () => void }) {
  const running = task.column === "working" || task.column === "auditor_review";
  const seconds = elapsedSeconds(task.started_at, now);

  return (
    <div className="mb-2 border border-line bg-surface last:mb-0">
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Open ${task.id}: ${task.title}`}
        className="w-full cursor-pointer px-2.5 py-2.5 text-left transition hover:bg-surface-2"
      >
        <div className="flex items-center gap-2">
          <AgentAvatar id={task.agent} size="sm" />
          <span className="truncate text-[12px] text-ink-dim">{AGENT_NAME[task.agent]}</span>
          {running && <Pulse className="ml-auto" />}
        </div>

        <div className="mt-1.5 line-clamp-3 text-[13.5px] font-medium leading-snug">{task.title}</div>

        {/* A progress bar on a queued task would imply work that has not happened. */}
        {task.column !== "queued" && (
          <div className="mt-2 flex items-center gap-2">
            <ProgressBar value={task.progress} className="h-1.5 flex-1" />
            <span className="font-num text-[12px] tabular-nums text-ink-dim">{task.progress}%</span>
          </div>
        )}

        {/* No start time in the run means no time on the card. A zero would be a claim. */}
        {seconds !== null && (
          <div className="mt-2 text-[12.5px]" title={`Started ${task.started_at}`}>
            <span className="font-num tabular-nums">{duration(seconds)}</span>
            <span className="text-ink-dim"> since start</span>
          </div>
        )}

        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-ink-faint">
          <span className="font-num tabular-nums" title="Evidence tool calls used of this task's budget">
            {task.tool_calls.used}/{task.tool_calls.budget} tools
          </span>
          <span>
            {task.steps.length} step{task.steps.length === 1 ? "" : "s"}
          </span>
          {task.todos.length > 0 && <span>{task.todos.length} still owed</span>}
        </div>

        {task.note && (
          <div className="mt-2">
            <Pill tone={task.note_tone === "warn" ? "red" : "gray"}>{task.note}</Pill>
          </div>
        )}
      </button>

      {/* The one place a card is more than a card: where it hands off to you. */}
      {task.column === "needs_you" && (
        <p className="border-t border-line px-2.5 py-1.5 text-[12px] text-ink-dim">
          Waiting on a person, not on a decision screen. Open the task for what it asked for.
        </p>
      )}
      {task.column === "auditor_review" && (
        <p className="border-t border-line px-2.5 py-1.5 text-[12px] text-ink-dim">
          The Internal Auditor is re-reading the sources and redoing the math.
        </p>
      )}
    </div>
  );
}
