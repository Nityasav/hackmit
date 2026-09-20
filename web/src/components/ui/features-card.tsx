"use client";

import { useState } from "react";
import {
  ChartColumn,
  Layers,
  Lightbulb,
  Lock,
  ShieldCheck,
  Sparkles,
  Terminal,
  Users,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { useData } from "@/lib/data";
import { AGENT_NAME, AgentAvatar } from "@/components/ui";
import { Badge } from "@/components/ui/badge";

export const Component = () => {
  const { bundle } = useData();
  const { agents, playbooks, ablation, decisions, findings, workspace } = bundle;

  const [activeAgent, setActiveAgent] = useState(0);
  const [selectedMetric, setSelectedMetric] = useState(0);

  const active = agents[activeAgent];

  // Every distinct tool the agents actually reached for, from the decision log.
  const tools = Array.from(
    new Set(decisions.flatMap((d) => d.how.map((h) => h.tool))),
  ).slice(0, 6);

  const metrics = ablation
    ? ablation.rows.map((r) => ({
        label: r.metric,
        without: r.without,
        with: r.with,
      }))
    : [];

  // The newest decision record, rendered the way it is stored.
  const record = decisions[0];
  const recordLines = record
    ? [
        `# ${record.id} · ${record.agent} · ${record.time}`,
        `action   ${record.action}`,
        ...record.how.map((h) => `tool     ${h.tool}(${h.input})`),
        `why      ${record.why}`,
        `outcome  ${record.outcome}`,
      ]
    : [];

  const stats = [
    { label: "Agents on the books", value: String(agents.length), icon: Users },
    { label: "Findings filed", value: String(findings.length), icon: ChartColumn },
    {
      label: "Precedent in use",
      value: String(playbooks.filter((p) => p.status === "active").length),
      icon: ShieldCheck,
    },
    {
      label: "Decisions logged",
      value: String(decisions.length),
      icon: Terminal,
    },
  ];

  return (
    <section className="w-full">
      <div className="mb-3 flex max-w-2xl flex-col gap-2">
        <div className="flex w-fit items-center gap-2 rounded-none border border-ink bg-surface-2 px-2.5 py-1">
          <Sparkles className="h-3.5 w-3.5 text-ink" aria-hidden />
          <span className="text-[13px] font-semibold text-ink">
            {workspace.mode === "live" ? "Running live" : `Mode: ${workspace.mode}`}
          </span>
        </div>
        <h2 className="text-xl font-bold tracking-tight">How the agents learn</h2>
        <p className="text-[14px] leading-relaxed text-ink-dim">
          Agents never write their own memory. A precedent exists only where you approved or
          rejected something, and the next run must re-check it against current evidence before
          relying on it — a matching vendor or amount is not enough to reuse one.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        {/* Who is on the books */}
        <div className="flex flex-col gap-3 rounded-none border border-line bg-surface p-3 md:col-span-2">
          <div>
            <div className="mb-2 flex w-fit items-center gap-2 rounded-md border border-line bg-surface-2 px-2 py-1 text-[12.5px] font-semibold text-ink-dim">
              <Lightbulb className="h-3.5 w-3.5" aria-hidden />
              The finance office
            </div>
            <h3 className="text-[14px] font-semibold">Pick an agent to see its brief</h3>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {agents.map((agent, i) => (
              <button
                key={agent.id}
                type="button"
                aria-pressed={activeAgent === i}
                onClick={() => setActiveAgent(i)}
                className={cn(
                  "flex cursor-pointer flex-col items-start gap-2 rounded-lg border p-2.5 text-left transition",
                  i === agents.length - 1 && agents.length % 2 === 1 && "col-span-2",
                  activeAgent === i
                    ? "border-ink bg-surface-2"
                    : "border-line bg-surface hover:border-ink",
                )}
              >
                <AgentAvatar id={agent.id} size="sm" />
                <span className="text-[13px] font-semibold">{agent.name}</span>
                <span className="line-clamp-1 text-[12.5px] text-ink-dim">
                  {agent.status}
                </span>
              </button>
            ))}
          </div>

          {active && (
            <div className="rounded-lg border border-line bg-surface-2 p-2.5">
              <div className="flex items-center gap-2">
                <AgentAvatar id={active.id} size="sm" />
                <p className="text-[14px] font-semibold">{AGENT_NAME[active.id]}</p>
              </div>
              <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-dim">
                {active.doing}
              </p>
            </div>
          )}
        </div>

        {/* Memory on vs off */}
        <div className="rounded-none border border-line bg-surface p-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="rounded-md border border-line bg-surface-2 p-1.5">
              <ChartColumn className="h-4 w-4 text-ink" aria-hidden />
            </div>
            {ablation?.example && <Badge variant="outline">Example numbers</Badge>}
          </div>
          <h3 className="text-[14px] font-semibold">Memory on vs off</h3>
          <p className="mb-2 text-[12.5px] text-ink-dim">
            {ablation ? ablation.note : "The evaluator has not run yet."}
          </p>

          <div className="space-y-1">
            {metrics.map((m, i) => (
              <button
                key={m.label}
                type="button"
                aria-pressed={selectedMetric === i}
                onClick={() => setSelectedMetric(i)}
                className={cn(
                  "w-full cursor-pointer rounded-lg border p-1.5 text-left transition",
                  selectedMetric === i
                    ? "border-ink bg-surface-2"
                    : "border-line bg-surface hover:border-ink",
                )}
              >
                <p className="text-[12.5px] text-ink-dim">{m.label}</p>
                <div className="mt-0.5 flex items-baseline justify-between gap-2">
                  <span className="text-[13.5px] font-semibold font-num tabular-nums">
                    {m.with}
                  </span>
                  <span className="text-[12.5px] font-num tabular-nums text-ink-faint">
                    was {m.without}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* What the agents are allowed to call */}
        <div className="rounded-none border border-line bg-surface p-3">
          <div className="mb-2 w-fit rounded-md border border-line bg-surface-2 p-1.5">
            <Layers className="h-4 w-4 text-ink" aria-hidden />
          </div>
          <h3 className="text-[14px] font-semibold">Tools they may call</h3>
          <p className="mb-2 text-[12.5px] text-ink-dim">
            Every call is typed and logged. Nothing else is reachable.
          </p>
          <ul className="flex flex-wrap gap-1">
            {tools.map((tool) => (
              <li
                key={tool}
                className="rounded border border-line bg-surface-2 px-1.5 py-1 font-mono text-[12px] text-ink-dim"
              >
                {tool}
              </li>
            ))}
            <li className="flex items-center gap-1 rounded border border-line bg-surface-2 px-1.5 py-1 text-[12px] text-ink-faint">
              <Lock className="h-3 w-3" aria-hidden />
              everything else
            </li>
          </ul>
        </div>

        {/* A real decision record */}
        <div className="rounded-none border border-line bg-surface p-3 md:col-span-4">
          <div className="mb-2 flex items-center gap-2">
            <div className="rounded-md border border-line bg-surface-2 p-1.5">
              <Terminal className="h-4 w-4 text-ink" aria-hidden />
            </div>
            <h3 className="text-[14px] font-semibold">The newest decision record</h3>
          </div>
          <pre className="max-h-36 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line bg-canvas p-2.5 font-mono text-[13px] leading-relaxed">
            {recordLines.map((line, i) => (
              <div key={i} className="flex gap-2">
                <span className="w-5 flex-none select-none text-right text-ink-faint">
                  {i + 1}
                </span>
                <span className={line.startsWith("#") ? "text-ink-faint" : "text-ink-dim"}>
                  {line}
                </span>
              </div>
            ))}
          </pre>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <div
              key={stat.label}
              className="rounded-none border border-line bg-surface p-3 transition-colors hover:border-ink"
            >
              <Icon className="mb-2 h-4 w-4 text-ink" aria-hidden />
              <p className="text-[12.5px] text-ink-dim">{stat.label}</p>
              <p className="mt-0.5 text-xl font-bold font-num tabular-nums">
                {stat.value}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
};
