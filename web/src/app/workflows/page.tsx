"use client";

import { Check, UserCheck } from "lucide-react";

import { useData } from "@/lib/data";
import type { StageState } from "@/lib/types";
import { AGENT_NAME, AgentAvatar, Card, PageHeader, Pulse } from "@/components/ui";
import { TabGate } from "@/components/shell/TabGate";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";

const STAGE_STYLE: Record<StageState, string> = {
  done: "border-line bg-surface-2 text-ink-dim",
  running: "border-ink bg-surface text-ink",
  human: "border-ink bg-surface text-ink",
  todo: "border-line bg-surface-2 text-ink-dim",
};

export default function WorkflowsPage() {
  const { bundle } = useData();
  if (bundle.workspace.intake) return <ReviewWorkspace />;
  return (
    <TabGate tab="workflows">
      <PageHeader
        title="Workflows"
        subtitle="The finance processes the agents run end to end. You only step in where a stage is marked for you."
      />
      {bundle.workflows.map((w) => (
        <Card key={w.id} className="mb-4">
          <div className="mb-2 flex items-center gap-2">
            <AgentAvatar id={w.owner} size="sm" />
            <b className="text-[15px]">{w.name}</b>
            <span className="font-accent text-[14px] text-ink-dim">owner: {AGENT_NAME[w.owner]}</span>
            <b className="ml-auto font-num tabular-nums">{w.progress}%</b>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {w.stages.map((s, i) => (
              <span key={s.name} className="flex items-center gap-1">
                <span className={`flex items-center gap-2 rounded-none border px-2.5 py-2.5 text-[13px] font-medium ${STAGE_STYLE[s.state]}`}>
                  {s.state === "running" && <Pulse />}
                  {s.state === "done" && <Check className="h-3.5 w-3.5" aria-hidden />}
                  {s.state === "human" && <UserCheck className="h-3.5 w-3.5" aria-hidden />}
                  {s.name}
                </span>
                {i < w.stages.length - 1 && <span className="text-ink-faint">→</span>}
              </span>
            ))}
          </div>
        </Card>
      ))}
      <p className="mt-4 text-[13px] text-ink-dim">
        Payments and payroll changes are simulated in the sandbox. Agents prepare them; a human releases them.
      </p>
    </TabGate>
  );
}
