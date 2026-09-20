"use client";

import { AgentAvatar, Pill, Pulse } from "@/components/ui";
import type { AgentId } from "@/lib/types";

import { agentState, CROSS_CHECK, FLOW, TEAM, type AgentProfile, type AgentState, type StateTone } from "./agents";
import type { CFORun } from "./run";

/** One hairline rail per agent, in that agent's tone. Written out so Tailwind keeps them. */
const RAIL: Record<AgentId, string> = {
  cfo: "bg-agent-cfo",
  ap: "bg-agent-ap",
  py: "bg-agent-py",
  gr: "bg-agent-gr",
  au: "bg-agent-au",
};

/** The lead and the checker take the full width; the three specialists share a row. */
const SPAN: Record<AgentId, string> = {
  cfo: "md:col-span-6",
  ap: "md:col-span-2",
  py: "md:col-span-2",
  gr: "md:col-span-2",
  au: "md:col-span-6",
};

export function StatePill({ state }: { state: { label: string; tone: StateTone } }) {
  const tone = state.tone === "done" ? "green" : state.tone === "stop" ? "red" : "gray";
  return (
    <Pill tone={tone}>
      {state.tone === "live" && <Pulse />}
      {state.label}
    </Pill>
  );
}

/**
 * The five agents: what each one does, how it does it, and what it is doing
 * right now. The state line is read out of the run, so before anyone starts
 * one it says so rather than inventing a status.
 */
export function AgentTeam({ run, running }: { run: CFORun | null; running: boolean }) {
  return (
    <>
      <ol className="mb-5 flex flex-wrap items-center gap-x-2.5 gap-y-1 font-accent text-[13.5px] text-ink-dim">
        {FLOW.map((step, index) => (
          <li key={step} className="flex items-center gap-2.5">
            {index > 0 && <span aria-hidden="true">&rarr;</span>}
            {step}
          </li>
        ))}
      </ol>

      <div className="grid gap-px border border-line bg-line md:grid-cols-6">
        {TEAM.map((agent) => (
          <AgentCard key={agent.id} agent={agent} state={agentState(run, running, agent.id)} />
        ))}
      </div>
    </>
  );
}

function AgentCard({ agent, state }: { agent: AgentProfile; state: AgentState }) {
  return (
    <article className={`relative bg-surface p-5 pl-6 ${SPAN[agent.id]}`}>
      <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-[3px] ${RAIL[agent.id]}`} />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <AgentAvatar id={agent.id} size="lg" />
        <h3 className="text-[16px] font-semibold tracking-tight">{agent.name}</h3>
        <span className="ml-auto">
          <StatePill state={state} />
        </span>
      </div>

      <p className="mt-2 font-accent text-[13px] text-ink-dim">{agent.beat}</p>
      <p className="mt-3.5 max-w-prose text-[14.5px] leading-relaxed">{agent.does}</p>

      <p className="mt-4 max-w-prose border-t border-line pt-3 text-[13px] leading-relaxed text-ink-dim">
        <span className="font-semibold text-ink">How it does it. </span>
        {agent.how}
      </p>

      <Doing tone={state.tone} detail={state.detail} />

      {agent.id === "au" && (
        <p className="mt-4 max-w-prose border-t border-line pt-3 text-[13.5px] font-semibold leading-relaxed">
          {CROSS_CHECK}
        </p>
      )}
    </article>
  );
}

/** What this agent is doing, right now, from the run. */
function Doing({ tone, detail }: { tone: StateTone; detail: string }) {
  return (
    <p className="mt-4 flex items-start gap-2 text-[13px] leading-relaxed">
      {tone === "live" && <Pulse className="mt-[5px]" />}
      <span className={tone === "live" ? "shimmer-text font-medium" : "text-ink-dim"}>{detail}</span>
    </p>
  );
}
