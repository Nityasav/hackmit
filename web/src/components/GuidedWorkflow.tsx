"use client";

import Link from "next/link";
import { Check, Circle, CircleDot } from "lucide-react";
import type { Bundle } from "@/lib/types";
import { deriveGuidedWorkflow, type IntakeUiProgress, type WorkflowAction } from "@/lib/workflow";

/** The two steps that are somewhere else. The rest happen on this page. */
const ROUTES: Partial<Record<WorkflowAction, string>> = {
  investigation: "/investigation",
  briefing: "/briefing",
};

/** Section of Books each on-page step belongs to. */
const SECTION: Partial<Record<WorkflowAction, string>> = {
  records: "source-records",
  import: "source-import",
};

function runAction(action: WorkflowAction) {
  if (action === "create") {
    window.dispatchEvent(new Event("schooltrace:new-institution"));
    return;
  }
  const id = SECTION[action] ?? "source-records";
  (document.getElementById(id) ?? document.getElementById("source-records"))?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

/**
 * One box that says what to do next, and a list showing where that sits in the
 * whole job. Every state on it is derived from the records panel and the
 * bundle — it never claims a step someone has not actually reached.
 */
export function GuidedWorkflow({ bundle, intake }: { bundle: Bundle; intake?: IntakeUiProgress | null }) {
  const guide = deriveGuidedWorkflow(bundle, intake);
  const route = ROUTES[guide.action];

  return (
    <section className="border border-line bg-surface" aria-labelledby="next-step-title">
      <div className="grid gap-6 p-5 lg:grid-cols-[minmax(0,1fr)_minmax(340px,1fr)]">
        <div>
          <p className="font-num text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-dim">{guide.eyebrow}</p>
          <h2 id="next-step-title" className="mt-2 text-xl font-bold tracking-tight">{guide.title}</h2>
          <p className="mt-2 max-w-xl text-[14px] leading-6 text-ink-dim">{guide.detail}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {route ? (
              <Link href={route} className="inline-flex min-h-10 items-center bg-ink px-4 text-[13px] font-semibold text-white hover:bg-ink-dim">
                {guide.actionLabel}
              </Link>
            ) : (
              <button type="button" onClick={() => runAction(guide.action)} className="min-h-10 bg-ink px-4 text-[13px] font-semibold text-white hover:bg-ink-dim">
                {guide.actionLabel}
              </button>
            )}
            {guide.action !== "create" && (
              <button type="button" onClick={() => runAction("create")} className="min-h-10 border border-ink px-4 text-[13px] font-semibold hover:bg-surface-2">
                Add another school
              </button>
            )}
          </div>
        </div>
        <ol className="grid gap-2 sm:grid-cols-2" aria-label="Where this sits in the whole job">
          {guide.steps.map((step) => {
            const Icon = step.state === "done" ? Check : step.state === "current" ? CircleDot : Circle;
            return (
              <li
                key={step.label}
                className={`flex gap-2 border-l-2 px-3 py-2 ${
                  step.state === "current" ? "border-ink bg-surface-2" : step.state === "done" ? "border-accent-good" : "border-line"
                }`}
              >
                <Icon
                  aria-hidden="true"
                  className={`mt-0.5 h-4 w-4 shrink-0 ${
                    step.state === "done" ? "text-accent-good" : step.state === "upcoming" ? "text-ink-faint" : "text-ink"
                  }`}
                />
                <span>
                  <b className="block text-[12.5px]">{step.label}</b>
                  <span className="mt-0.5 block text-[11px] leading-4 text-ink-dim">{step.detail}</span>
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
