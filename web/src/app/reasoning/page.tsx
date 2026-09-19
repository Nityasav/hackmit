"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useData } from "@/lib/data";
import type { AgentId, Decision } from "@/lib/types";
import { AGENT_NAME, PageHeader } from "@/components/ui";
import { DecisionCard } from "@/components/reasoning/DecisionCard";

export default function ReasoningPage() {
  return (
    <Suspense fallback={<PageHeader title="Reasoning log" />}>
      <Reasoning />
    </Suspense>
  );
}

function Reasoning() {
  const { bundle } = useData();
  const params = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [agent, setAgent] = useState<AgentId | "all">("all");
  const [run, setRun] = useState<string>("all");
  const [memoryOnly, setMemoryOnly] = useState(false);

  const runs = useMemo(() => [...new Set(bundle.decisions.map((d) => d.run))], [bundle.decisions]);

  const filtered = bundle.decisions.filter((d) => {
    if (agent !== "all" && d.agent !== agent) return false;
    if (run !== "all" && d.run !== run) return false;
    if (memoryOnly && d.memory_checks.length === 0 && !d.tags.some((t) => t.kind)) return false;
    if (q.trim() && !haystack(d).includes(q.trim().toLowerCase())) return false;
    return true;
  });

  const grouped = runs
    .map((r) => ({ run: r, items: filtered.filter((d) => d.run === r) }))
    .filter((g) => g.items.length > 0);

  return (
    <>
      <PageHeader
        title="Reasoning log"
        subtitle="Every decision every agent made, and why. Click one to expand it."
      />

      <div className="mb-2 flex items-center gap-2 rounded-lg border border-line bg-slate-50 px-2.5 py-1.5 focus-within:border-teal-400">
        <span className="text-teal-700">✦</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask why… searches actions, reasons, tools, evidence IDs"
          className="w-full bg-transparent text-[12.5px] outline-none placeholder:text-slate-400"
        />
        {q && (
          <button type="button" onClick={() => setQ("")} className="cursor-pointer text-slate-400">
            ✕
          </button>
        )}
      </div>

      <div className="mb-2.5 flex flex-wrap gap-1.5">
        <Chip active={agent === "all"} onClick={() => setAgent("all")}>
          All agents
        </Chip>
        {(["cfo", "ap", "py", "gr", "au"] as AgentId[]).map((a) => (
          <Chip key={a} active={agent === a} onClick={() => setAgent(a)}>
            {AGENT_NAME[a]}
          </Chip>
        ))}
        <span className="mx-1 w-px bg-line" />
        <Chip active={run === "all"} onClick={() => setRun("all")}>
          All runs
        </Chip>
        {runs.map((r) => (
          <Chip key={r} active={run === r} onClick={() => setRun(r)}>
            {r.split(" · ")[0]}
          </Chip>
        ))}
        <Chip active={memoryOnly} onClick={() => setMemoryOnly((m) => !m)}>
          Used memory
        </Chip>
      </div>

      {grouped.length === 0 && (
        <div className="py-10 text-center text-slate-500">No decisions match that filter.</div>
      )}

      {grouped.map((g) => (
        <div key={g.run}>
          <div className="mb-1.5 mt-2.5 text-[10.5px] font-semibold uppercase tracking-wider text-slate-500">{g.run}</div>
          {g.items.map((d) => (
            <DecisionCard key={d.id} decision={d} defaultOpen={filtered.length === 1} />
          ))}
        </div>
      ))}
    </>
  );
}

function haystack(d: Decision): string {
  return [
    d.id,
    d.action,
    d.summary,
    d.why,
    d.outcome,
    d.when.trigger,
    d.when.step,
    ...d.tags.map((t) => t.label),
    ...d.how.map((h) => `${h.tool} ${h.input} ${h.output}`),
    ...d.alternatives.map((a) => `${a.option} ${a.reason}`),
    ...d.memory_checks.map((m) => m.text),
  ]
    .join(" ")
    .toLowerCase();
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`cursor-pointer rounded-full border px-2.5 py-1 text-[11px] ${
        active ? "border-slate-900 bg-slate-900 text-white" : "border-line bg-white text-slate-600 hover:border-teal-300"
      }`}
    >
      {children}
    </button>
  );
}
