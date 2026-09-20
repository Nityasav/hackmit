"use client";

import { Section } from "@/components/ui";

import { AgentBoard } from "./AgentBoard";
import { AgentTeam } from "./AgentTeam";
import { BeforeAnyRun, RunProgress, StartInvestigation } from "./CfoRun";
import { describeRun } from "./agents";
import { RunFindings } from "./Findings";
import { RecordChecks } from "./RecordChecks";
import { Precedent } from "./Precedent";
import { useInvestigation } from "./run";

/**
 * The Investigation screen: five agents check one company's books.
 *
 * The page reads top to bottom the way the work happens — ask, meet the team,
 * watch them work, read what they found. Every status, number and quotation
 * on it comes out of the run; when there is no run it says so.
 */
export function Investigation({ ws }: { ws: string }) {
  const state = useInvestigation(ws);
  const { run, running } = state;

  return (
    <div className="mx-auto max-w-5xl pb-16">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-ink-dim">Investigation</p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
          Review the records.
        </h1>
        <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-ink-dim">
          Set a question for the team. Follow the review and open the evidence behind each finding.
        </p>
        <p className="mt-4 font-accent text-[14px] text-ink-dim">{describeRun(run, running)}</p>
        {run?.scope && (
          <p className="mt-1 font-accent text-[14px] text-ink-dim">
            {run.scope.institution} · {run.scope.period}
          </p>
        )}
      </header>

      <Section title="Record checks">
        <RecordChecks ws={ws} />
      </Section>

      <Section title="Review scope">
        <StartInvestigation state={state} />
      </Section>

      <Section title="Agent team">
        <AgentTeam run={run} running={running} />
      </Section>

      <Section title={run ? "Progress" : "Review process"}>
        {run ? <RunProgress run={run} running={running} /> : <BeforeAnyRun />}
      </Section>

      <Section title="Agent tasks">
        <AgentBoard />
      </Section>

      {run && (
        <Section title="Findings">
          <RunFindings ws={ws} run={run} running={running} />
        </Section>
      )}

      <Section title="Previous decisions">
        <Precedent />
      </Section>
    </div>
  );
}
