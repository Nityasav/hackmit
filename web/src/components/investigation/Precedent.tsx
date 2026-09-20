"use client";

import { Pill } from "@/components/ui";
import { useData } from "@/lib/data";

/**
 * What the agents learned from you, and what they did with it this run.
 *
 * The loop has two halves and both have to be visible or the claim is not
 * checkable: a decision you made became precedent (the rows), and the next run
 * had to reckon with that precedent before it concluded anything (the checks).
 *
 * A declined precedent is shown exactly as prominently as an applied one. An
 * agent that re-reads a past decision and says "this one does not apply here,
 * because…" is the loop working correctly — filtering those out would leave
 * only the flattering half and turn re-checking into replay.
 */
export function Precedent() {
  const { bundle } = useData();
  const { playbooks, decisions } = bundle;

  const active = playbooks.filter((p) => p.status === "active");
  // Every precedent this run weighed, newest run first.
  const checks = decisions.flatMap((d) => d.memory_checks);

  if (active.length === 0) {
    return (
      <p className="max-w-xl text-[14px] leading-relaxed text-ink-dim">
        Nothing yet. Precedent is written when you approve or reject a finding — never by an
        agent. Decide one and it appears here, and the next run has to re-check it against
        that run&rsquo;s own evidence before it may rely on it.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <ul className="space-y-3">
        {active.map((p) => (
          <li key={p.id} className="border-l-2 border-ink pl-4">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="font-accent text-[13px] text-ink-dim">{p.id}</span>
              <span className="text-[15px] font-semibold">{p.title}</span>
              <span className="ml-auto font-accent text-[13px] text-ink-dim">
                used {p.uses}×
              </span>
            </div>
            <p className="mt-1 text-[13.5px] leading-relaxed text-ink-dim">{p.status_note}</p>
            <p className="mt-0.5 font-accent text-[13px] text-ink-faint">from {p.source}</p>
          </li>
        ))}
      </ul>

      {checks.length > 0 && (
        <div>
          <h3 className="text-[13.5px] font-semibold">What this run did with it</h3>
          <ul className="mt-2 space-y-2">
            {checks.map((check, i) => (
              <li key={i} className="flex items-start gap-2.5 text-[13.5px] leading-relaxed">
                <Pill tone={check.ok ? "green" : "gray"} className="mt-px flex-none">
                  {check.ok ? "applied" : "declined"}
                </Pill>
                <span className="text-ink-dim">{check.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="max-w-xl text-[13px] leading-relaxed text-ink-faint">
        Agents never edit their own prompts and nothing is fine-tuned. A precedent exists only
        where you decided something, and a matching vendor or amount is not enough to reuse one.
      </p>
    </div>
  );
}
