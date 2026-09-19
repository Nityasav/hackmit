"use client";

import { useData } from "@/lib/data";
import type { StageState } from "@/lib/types";
import { AGENT_NAME, AgentAvatar, Card, PageHeader, Pulse } from "@/components/ui";
import { TabGate } from "@/components/shell/TabGate";

const STAGE_STYLE: Record<StageState, string> = {
  done: "border-green-300 bg-green-100 text-accent-good",
  running: "border-accent-good bg-green-100 text-green-800",
  human: "border-line bg-surface-2 text-ink-dim",
  todo: "border-line bg-surface-2 text-ink-dim",
};

export default function WorkflowsPage() {
  const { bundle } = useData();
  return (
    <TabGate tab="workflows">
      <PageHeader
        title="Workflows"
        subtitle="The finance processes the agents run end to end. You only step in at the amber stages."
      />
      {bundle.workflows.map((w) => (
        <Card key={w.id} className="mb-2">
          <div className="mb-2 flex items-center gap-2">
            <AgentAvatar id={w.owner} size="sm" />
            <b className="text-[13px]">{w.name}</b>
            <span className="text-[11.5px] text-ink-dim">owner: {AGENT_NAME[w.owner]}</span>
            <b className="ml-auto tabular-nums">{w.progress}%</b>
          </div>
          <div className="flex flex-wrap items-center gap-1">
            {w.stages.map((s, i) => (
              <span key={s.name} className="flex items-center gap-1">
                <span className={`flex items-center gap-1.5 rounded-[7px] border px-2.5 py-1.5 text-[11px] font-medium ${STAGE_STYLE[s.state]}`}>
                  {s.state === "running" && <Pulse />}
                  {s.state === "done" && "✓"}
                  {s.state === "human" && "✋"}
                  {s.name}
                </span>
                {i < w.stages.length - 1 && <span className="text-ink-faint">→</span>}
              </span>
            ))}
          </div>
        </Card>
      ))}
      <p className="mt-1 text-[11px] text-ink-dim">
        Payments and payroll changes are simulated in the sandbox. Agents prepare them; a human releases them.
      </p>
    </TabGate>
  );
}
