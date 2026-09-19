"use client";

import { useState } from "react";
import { useData } from "@/lib/data";
import { money } from "@/lib/format";
import type { EvidenceNode } from "@/lib/types";
import { AGENT_NAME, AgentAvatar, AiTag, Card, CardTitle, FindingStatusPill, PageHeader } from "@/components/ui";

const KIND_ICON: Record<EvidenceNode["kind"], string> = {
  record: "💵",
  award: "🎓",
  doc: "📄",
  calc: "🧮",
  page: "📑",
};

const TONE_STYLE: Record<EvidenceNode["tone"], string> = {
  neutral: "border-line bg-slate-50",
  bad: "border-red-200 bg-red-50",
  good: "border-teal-200 bg-teal-50",
};

export default function FindingsPage() {
  const { bundle } = useData();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = bundle.findings.find((f) => f.id === selectedId) ?? bundle.findings[0];

  return (
    <>
      <PageHeader
        title="Findings"
        subtitle="What the agents found, and the evidence trail behind it"
      />
      <div className="grid gap-2.5 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          {bundle.findings.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setSelectedId(f.id)}
              className={`flex w-full cursor-pointer items-center gap-2 rounded-lg p-2 text-left ${
                f.id === selected?.id ? "border border-teal-200 bg-teal-50" : "border border-transparent hover:bg-slate-50"
              }`}
            >
              <AgentAvatar id={f.agent} size="sm" />
              <div className="min-w-0">
                <b className="block truncate">{f.title}</b>
                <span className="text-slate-500">{f.summary}</span>
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
            <CardTitle>
              Evidence trail · {selected.id}
              <span className="ml-1">
                <AiTag>
                  found by {AGENT_NAME[selected.agent]}
                  {selected.verified_by ? ` · verified by ${AGENT_NAME[selected.verified_by]}` : ""}
                </AiTag>
              </span>
            </CardTitle>
            <div className="flex flex-col gap-1">
              {selected.evidence.map((n, i) => (
                <div key={i}>
                  <span
                    className={`inline-flex w-max items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] ${TONE_STYLE[n.tone]}`}
                  >
                    {KIND_ICON[n.kind]} {n.label}
                  </span>
                  {n.edge && <div className="pl-[18px] font-mono text-[9.5px] text-slate-400">{n.edge}</div>}
                </div>
              ))}
            </div>
            {selected.amount_note && (
              <div className="mt-2 text-[11.5px] text-slate-500">
                Amount basis: {selected.amount_note}
              </div>
            )}
            <div className="mt-2 text-[11px] text-slate-500">
              Every node links to a source row, a document page, or a deterministic calculation. Amounts come from the
              calculation engine, never from the model.
            </div>
          </Card>
        )}
      </div>
    </>
  );
}
