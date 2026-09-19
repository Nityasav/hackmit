"use client";

import { useState } from "react";
import { useData } from "@/lib/data";
import { money } from "@/lib/format";
import { AgentAvatar, Card, EmptyState, FindingStatusPill, PageHeader } from "@/components/ui";
import { EvidenceTrail } from "@/components/findings/EvidenceTrail";

export default function FindingsPage() {
  const { bundle } = useData();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = bundle.findings.find((f) => f.id === selectedId) ?? bundle.findings[0];

  return (
    <>
      <PageHeader title="Findings" subtitle="What the agents found, and the evidence behind it" />
      <div className="grid gap-2.5 min-[900px]:grid-cols-[1.4fr_1fr]">
        <Card>
          {bundle.findings.length === 0 && (
            <EmptyState title="No findings yet">The agents are still working. Findings appear here once the Auditor has reviewed them.</EmptyState>
          )}
          {bundle.findings.map((f) => (
            <button
              key={f.id}
              type="button"
              aria-pressed={f.id === selected?.id}
              onClick={() => setSelectedId(f.id)}
              className={`flex w-full items-center gap-2 rounded-lg border p-2 text-left transition ${
                f.id === selected?.id ? "border-green-300 bg-green-50" : "border-transparent hover:bg-surface-2"
              }`}
            >
              <AgentAvatar id={f.agent} size="sm" />
              <div className="min-w-0">
                <b className="block truncate">{f.title}</b>
                <span className="text-ink-dim">{f.summary}</span>
              </div>
              <span className="ml-auto flex flex-none items-center gap-1.5">
                {f.amount_cents != null && <b className="tabular-nums">{money(f.amount_cents)}</b>}
                <FindingStatusPill status={f.status} />
              </span>
            </button>
          ))}
        </Card>

        {selected && (
          <Card>
            <EvidenceTrail key={selected.id} finding={selected} />
          </Card>
        )}
      </div>
    </>
  );
}
