"use client";

import { useState } from "react";

import { Section } from "@/components/ui";
import type { AgentNode, AgentRunResult } from "@/lib/types";

import { AgentBoard } from "./AgentBoard";
import { byWorker, money, useOrganization } from "./organization";
import { Precedent } from "./Precedent";
import { RecordChecks } from "./RecordChecks";

/**
 * Investigation: the finance organization, and what it has concluded.
 *
 * Every status, number and quotation comes from the API. Nothing is authored here —
 * an agent that has not run shows nothing, and an agent that is blocked says which
 * upload would unblock it rather than producing an empty result.
 */
export function Investigation({ ws }: { ws: string }) {
  const state = useOrganization(ws);
  const workers = byWorker(state.agents);
  const blocked = state.agents.filter((a) => a.tier === "subagent" && !a.ready).length;

  return (
    <div className="mx-auto max-w-5xl pb-16">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-ink-dim">Investigation</p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
          Put the organization on the books.
        </h1>
        <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-ink-dim">
          Each agent reads only the records it declared it needs, cites what it used, and
          escalates what a person has to decide.
        </p>
        {state.spend && (
          <p className="mt-4 font-accent text-[14px] text-ink-dim">
            Spent today {money(state.spend.today_cents)} of {money(state.spend.day_cap_cents)} ·
            {" "}up to {money(state.spend.run_cap_cents)} per run
          </p>
        )}
        {blocked > 0 && (
          <p className="mt-1 font-accent text-[14px] text-ink-dim">
            {blocked} agent{blocked === 1 ? "" : "s"} waiting on records. Books lists what each needs.
          </p>
        )}
      </header>

      <Section title="Record checks">
        <RecordChecks ws={ws} />
      </Section>

      <Section title="The organization">
        {state.error && (
          <p role="alert" className="mb-3 border border-line bg-surface p-4 text-[13.5px] text-red-800">
            {state.error}
          </p>
        )}
        {state.loading ? (
          <p className="text-[14px] text-ink-dim">Loading the organization…</p>
        ) : (
          <div className="space-y-6">
            {workers.map(({ worker, children }) => (
              <Worker key={worker.id} worker={worker} subagents={children} state={state} />
            ))}
          </div>
        )}
      </Section>

      {state.results.length > 0 && (
        <Section title="This session">
          <div className="space-y-3">
            {state.results.map((result) => (
              <RunResult key={result.decision_id} result={result} />
            ))}
          </div>
        </Section>
      )}

      <Section title="Agent tasks">
        <AgentBoard />
      </Section>

      <Section title="Previous decisions">
        <Precedent />
      </Section>
    </div>
  );
}

function Worker({
  worker, subagents, state,
}: {
  worker: AgentNode;
  subagents: AgentNode[];
  state: ReturnType<typeof useOrganization>;
}) {
  return (
    <div className="border border-line bg-surface p-5">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h3 className="text-[15px] font-semibold tracking-tight">{worker.name}</h3>
        <span className="font-accent text-[13px] text-ink-dim">{worker.id}</span>
      </div>
      <p className="mt-1 max-w-prose text-[13.5px] leading-relaxed text-ink-dim">{worker.charter}</p>

      <ul className="mt-4">
        {subagents.map((agent) => (
          <Subagent key={agent.id} agent={agent} state={state} />
        ))}
      </ul>
    </div>
  );
}

function Subagent({
  agent, state,
}: {
  agent: AgentNode;
  state: ReturnType<typeof useOrganization>;
}) {
  const [objective, setObjective] = useState("");
  const busy = state.running === agent.id;
  const anyRunning = state.running !== null;

  return (
    <li className="border-t border-line py-3.5">
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <span className="font-accent text-[12.5px] text-ink-dim">{agent.id}</span>
        <h4 className="text-[14.5px] font-semibold">{agent.name}</h4>
        {!agent.uses_model_in_hot_path && (
          <span className="bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-dim" title="The work is deterministic; a model only judges exceptions around it.">
            deterministic
          </span>
        )}
        <span className="ml-auto font-num text-[12px] tabular-nums text-ink-faint">
          up to {money(agent.budget.usd_cents)}
        </span>
      </div>

      <p className="mt-1 max-w-prose text-[13.5px] leading-relaxed text-ink-dim">{agent.charter}</p>

      <p className="mt-1.5 font-accent text-[12.5px] text-ink-faint">
        Reads {agent.reads.join(", ") || "nothing yet"}
        {agent.reviewer && ` · reviewed by ${agent.reviewer}`}
      </p>

      {agent.ready ? (
        <div className="mt-2.5 flex flex-col gap-2 sm:flex-row">
          <input
            aria-label={`What should ${agent.name} look into?`}
            className="min-w-0 flex-1 border border-line bg-white px-2.5 py-1.5 text-[13px]"
            placeholder={`What should ${agent.name} look into?`}
            value={objective}
            disabled={anyRunning}
            onChange={(event) => setObjective(event.target.value)}
          />
          <button
            type="button"
            className="whitespace-nowrap border border-line px-3 py-1.5 text-[13px] font-semibold disabled:opacity-40"
            disabled={anyRunning || !objective.trim()}
            onClick={() => void state.run(agent.id, objective.trim())}
          >
            {busy ? "Working…" : "Run"}
          </button>
        </div>
      ) : (
        <p className="mt-2 border-t border-line pt-2 text-[13px] text-ink-dim">
          Waiting on {agent.blocked_by.join(", ")}. Supply it on Books.
        </p>
      )}
    </li>
  );
}

function RunResult({ result }: { result: AgentRunResult }) {
  const escalated = result.escalated;
  return (
    <div className="border border-line bg-surface p-4">
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <span className="font-accent text-[12.5px] text-ink-dim">{result.agent_id}</span>
        <h4 className="text-[14.5px] font-semibold">{result.agent_name}</h4>
        {/* Computed by the match rubric, never asserted by the model. */}
        {result.confidence !== null && (
          <span className="bg-surface-2 px-1.5 py-0.5 font-num text-[11px] tabular-nums" title="Computed from the recorded match features, not stated by the model">
            confidence {result.confidence}/100
          </span>
        )}
        <span className="ml-auto font-num text-[12px] tabular-nums text-ink-faint">
          {money(result.cost_cents)} · {result.model_calls} model call(s)
        </span>
      </div>

      {result.result && (
        <>
          <p className="mt-2 text-[14px] leading-relaxed">{result.result.summary}</p>
          <p className="mt-1.5 max-w-prose text-[13.5px] leading-relaxed text-ink-dim">
            {result.result.rationale}
          </p>

          {result.result.exceptions.length > 0 && (
            <ul className="mt-2.5 space-y-1">
              {result.result.exceptions.map((exception) => (
                <li key={exception.code} className="text-[13px] leading-relaxed">
                  <span className="font-accent text-ink-dim">{exception.code}</span> — {exception.detail}
                </li>
              ))}
            </ul>
          )}

          {result.result.citations.length > 0 && (
            <p className="mt-2 font-accent text-[12.5px] text-ink-faint">
              Cited {result.result.citations.length} record(s):{" "}
              {result.result.citations.map((c) => c.record_key || c.source_id).join(", ")}
            </p>
          )}
        </>
      )}

      {escalated && (
        <div className="mt-3 border-t border-line pt-2">
          <p className="text-[13px] font-semibold">Needs a person</p>
          <ul className="mt-1 space-y-0.5">
            {result.escalation_reasons.map((reason) => (
              <li key={reason} className="text-[13px] text-ink-dim">{reason}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
