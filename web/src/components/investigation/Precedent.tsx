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
        No decisions yet. Approve or reject a finding to save guidance for future reviews.
      </p>
    );
  }

  return (
    <details className="border border-line p-4">
      <summary className="cursor-pointer text-sm font-semibold">Saved guidance ({active.length}) <span className="ml-2 font-normal text-ink-dim">Checked before reuse</span></summary>
      <ul className="mt-4 max-h-80 space-y-3 overflow-y-auto">
        {active.map((p) => (
          <li key={p.id} className="border border-line p-3"><details>
            <summary className="cursor-pointer text-sm">
              <span className="font-semibold">{p.title.length > 100 ? p.title.slice(0, 100) + "…" : p.title}</span>
              <span className="ml-auto font-accent text-[13px] text-ink-dim">
                used {p.uses}×
              </span>
            </summary>
            <p className="mt-3 text-sm">{p.title}</p>
            <p className="mt-1 text-[13.5px] leading-relaxed text-ink-dim">{p.status_note}</p>
            <p className="mt-0.5 font-accent text-[13px] text-ink-faint">from {p.source}</p>
          </details></li>
        ))}
      </ul>

      {checks.length > 0 && (
        <details className="mt-4 border-t border-line pt-3">
          <summary className="cursor-pointer text-sm font-semibold">Decisions considered ({checks.length})</summary>
          <ul className="mt-2 max-h-60 space-y-2 overflow-y-auto">
            {checks.map((check, i) => (
              <li key={i} className="flex items-start gap-2.5 text-[13.5px] leading-relaxed">
                <Pill tone={check.ok ? "green" : "gray"} className="mt-px flex-none">
                  {check.ok ? "Applied" : "Declined"}
                </Pill>
                <span className="text-ink-dim">{check.text}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

    </details>
  );
}
