"use client";

import Link from "next/link";
import { useState } from "react";

import { AGENT_NAME, AgentAvatar, Button, Figure } from "@/components/ui";

import { agentOf, describeStep, taskState, WHAT_HAPPENS } from "./agents";
import { StatePill } from "./AgentTeam";
import type { CFORun, Investigation, RunEvent } from "./run";

const DEFAULT_OBJECTIVE =
  "Review the records we uploaded, point out anything that needs attention, and show the evidence.";

/**
 * Starting a run, and watching one happen.
 *
 * There is one mode: a run reads this company's committed records and makes
 * paid model calls, or it does not start. Nothing here is rendered before the
 * service has reported it.
 */
export function StartInvestigation({ state }: { state: Investigation }) {
  const [objective, setObjective] = useState(DEFAULT_OBJECTIVE);
  const blocked = !state.ready || !state.connected;
  const disabled = blocked || state.starting || state.running || !objective.trim();

  return (
    <div className="border border-line bg-surface p-5 md:p-6">
      <label htmlFor="objective" className="block text-[15px] font-semibold tracking-tight">
        What should the agents look into?
      </label>
      <p className="mt-1.5 max-w-prose text-[13.5px] leading-relaxed text-ink-dim">
        Specify the period, transactions or concern to review.
      </p>
      <textarea
        id="objective"
        value={objective}
        maxLength={2000}
        onChange={(event) => setObjective(event.target.value)}
        className="mt-3.5 min-h-24 w-full border border-line bg-white p-3 text-[14px] leading-relaxed"
      />

      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-3">
        <Button primary disabled={disabled} onClick={() => void state.start(objective.trim())}>
          {state.starting ? "Starting…" : state.running ? "Agents are working" : "Start the investigation"}
        </Button>
        <p className="max-w-md text-[13px] leading-relaxed text-ink-dim">
          Selected records are sent to the model provider. API charges apply. Changes require your approval.
        </p>
      </div>

      {!state.ready && (
        <p className="mt-4 border-t border-line pt-3 text-[13.5px]">
          There are no committed records for this company yet.{" "}
          <Link href="/" className="underline">
            Add them on Books
          </Link>{" "}
          and commit them first.
        </p>
      )}
      {state.ready && !state.connected && (
        <p className="mt-4 border-t border-line pt-3 text-[13.5px]">
          The agent service is not connected, so no investigation can start. Set its API address and reload.
        </p>
      )}
      {state.error && (
        <p role="alert" className="mt-4 border-t border-line pt-3 text-[13.5px] text-red-800">
          {state.error}
        </p>
      )}
    </div>
  );
}

/** Said before anyone has started a run. It describes the run, and previews nothing. */
export function BeforeAnyRun() {
  return (
    <div className="border border-line bg-surface p-5 md:p-6">
      <h3 className="text-[15px] font-semibold tracking-tight">Review steps</h3>
      <ol className="mt-4 max-w-2xl space-y-3">
        {WHAT_HAPPENS.map((step, index) => (
          <li key={step} className="flex gap-3.5 text-[14px] leading-relaxed">
            <span aria-hidden="true" className="font-num text-[13px] font-semibold text-ink-dim">
              {index + 1}
            </span>
            {step}
          </li>
        ))}
      </ol>
      <p className="mt-5 border-t border-line pt-3 font-accent text-[13.5px] text-ink-dim">
        Progress and findings appear here during the review.
      </p>
    </div>
  );
}

/** The live run: how much it has done, who is doing what, and every step in order. */
export function RunProgress({ run, running }: { run: CFORun; running: boolean }) {
  return (
    <>
      <div className="grid grid-cols-2 gap-y-5 border border-line bg-surface px-5 py-4 sm:grid-cols-4 sm:gap-y-0 sm:divide-x sm:divide-line">
        <Figure label="CFO calls" value={run.model_calls} note="planning and reporting" />
        <Figure label="Evidence checks" value={run.tool_calls} note="source reads and calculations" />
        <Figure label="Claims accepted" value={run.accepted.length} note="passed the Auditor's re-check" />
        <Figure label="Still unresolved" value={run.unresolved.length} note="questions left open" />
      </div>

      <p className="mt-3 break-words font-accent text-[12.5px] text-ink-dim">
        Run {run.id} · {run.model_label}
        {run.scope && ` · records frozen as ${run.scope.snapshot_id}`}
      </p>

      {run.plan && (
        <div className="mt-6 border border-line bg-surface p-5 md:p-6">
          <h3 className="text-[15px] font-semibold tracking-tight">Assigned tasks</h3>
          <p className="mt-2 max-w-prose text-[13.5px] leading-relaxed text-ink-dim">{run.plan.rationale}</p>
          <ul className="mt-4">
            {run.tasks.map((task) => {
              const id = agentOf(task.spec.role);
              const state = taskState(task.status);
              return (
                <li key={task.spec.id} className="flex flex-wrap gap-3 border-t border-line py-3.5">
                  {id && <AgentAvatar id={id} />}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                      <h4 className="text-[14.5px] font-semibold">{id ? AGENT_NAME[id] : task.spec.role}</h4>
                      <span className="ml-auto">
                        <StatePill state={state} />
                      </span>
                    </div>
                    <p className="mt-1.5 max-w-prose text-[13.5px] leading-relaxed text-ink-dim">
                      {task.spec.objective}
                    </p>
                    <p className="mt-1.5 font-accent text-[12.5px] text-ink-dim">
                      Job {task.spec.id} · {task.attempts === 1 ? "1 attempt" : `${task.attempts} attempts`}
                      {task.spec.depends_on.length > 0 && ` · waiting on ${task.spec.depends_on.join(", ")}`}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {run.scope && run.scope.gaps.length > 0 && (
        <div className="mt-6 border border-line bg-surface p-5 md:p-6">
          <h3 className="text-[15px] font-semibold tracking-tight">Missing evidence</h3>
          <ul className="mt-3 max-w-2xl space-y-2">
            {run.scope.gaps.map((gap) => (
              <li key={gap} className="border-t border-line pt-2 text-[13.5px] leading-relaxed text-ink-dim">
                {gap}
              </li>
            ))}
          </ul>
        </div>
      )}

      {run.events.length > 0 && (
        <div className="mt-6 border border-line bg-surface p-5 md:p-6">
          <h3 className="text-[15px] font-semibold tracking-tight">
            Activity, newest first{" "}
            <span className="ml-1 font-num text-[13px] font-medium text-ink-dim">{run.events.length}</span>
          </h3>
          <p className="mt-1.5 text-[13.5px] text-ink-dim">
            {running ? "Updates as the review progresses." : "Saved activity for this run."}
          </p>
          <ol className="mt-3 max-h-[28rem] overflow-y-auto">
            {[...run.events].reverse().map((event, index) => (
              <Step key={`${event.at}-${index}`} event={event} />
            ))}
          </ol>
        </div>
      )}
    </>
  );
}

function Step({ event }: { event: RunEvent }) {
  const id = agentOf(event.actor);
  return (
    <li className="border-t border-line py-2.5">
      <details>
        {/* Left as a list item so the browser keeps its own open/closed marker. */}
        <summary className="cursor-pointer text-[13.5px] leading-relaxed marker:text-ink-dim">
          <span className="inline-flex flex-wrap items-center gap-x-2.5 gap-y-1 align-middle">
            <span className="font-num text-[12px] text-ink-dim">{clock(event.at)}</span>
            {id && <AgentAvatar id={id} size="sm" />}
            <span className="font-medium">{id ? AGENT_NAME[id] : event.actor}</span>
            <span className="text-ink-dim">{describeStep(event.action)}</span>
            {event.task_id && <span className="font-accent text-[12.5px] text-ink-dim">{event.task_id}</span>}
          </span>
        </summary>
        <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words bg-surface-2 p-3 font-mono text-[12px] leading-relaxed text-ink-dim">
          {event.detail || "No detail was recorded for this step."}
        </pre>
      </details>
    </li>
  );
}

/** The clock time of a step. Unparseable timestamps are shown as they arrived. */
function clock(at: string): string {
  const time = new Date(at);
  return Number.isNaN(time.getTime())
    ? at
    : time.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
