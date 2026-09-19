"use client";

import { useState } from "react";
import type { EvidenceNode, Finding } from "@/lib/types";
import { AGENT_NAME, AgentAvatar, AiTag } from "@/components/ui";

const KIND_ICON: Record<EvidenceNode["kind"], string> = {
  record: "💵",
  award: "🎓",
  doc: "📄",
  calc: "🧮",
  page: "📑",
};

const TONE_STYLE: Record<EvidenceNode["tone"], string> = {
  neutral: "border-line bg-white hover:border-slate-300",
  bad: "border-red-200 bg-red-50 hover:border-red-300",
  good: "border-teal-200 bg-teal-50 hover:border-teal-400",
};

const TONE_DOT: Record<EvidenceNode["tone"], string> = {
  neutral: "bg-slate-300",
  bad: "bg-red-400",
  good: "bg-teal-500",
};

export function EvidenceTrail({ finding }: { finding: Finding }) {
  // The parent remounts this with key={finding.id}, so the open source resets per finding.
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const open = openIndex == null ? null : finding.evidence[openIndex];

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[12.5px] font-semibold">
        Evidence trail · {finding.id}
        <AiTag>
          found by {AGENT_NAME[finding.agent]}
          {finding.verified_by ? ` · verified by ${AGENT_NAME[finding.verified_by]}` : ""}
        </AiTag>
      </div>

      <ol className="relative">
        {finding.evidence.map((n, i) => {
          const isOpen = i === openIndex;
          const hasSource = Boolean(n.source_preview || n.locator);
          return (
            <li key={i} className="relative pl-5">
              {/* connector line down the trail */}
              {i < finding.evidence.length - 1 && (
                <span className="absolute left-[5px] top-3 h-[calc(100%-4px)] w-px bg-slate-200" aria-hidden />
              )}
              <span className={`absolute left-0 top-2.5 h-[11px] w-[11px] rounded-full ring-4 ring-white ${TONE_DOT[n.tone]}`} aria-hidden />

              <button
                type="button"
                disabled={!hasSource}
                aria-expanded={isOpen}
                onClick={() => setOpenIndex(isOpen ? null : i)}
                className={`mb-0.5 flex w-full items-center gap-1.5 rounded-md border px-2 py-1.5 text-left text-[11px] transition disabled:cursor-default ${TONE_STYLE[n.tone]} ${
                  isOpen ? "ring-2 ring-teal-200" : ""
                }`}
              >
                <span aria-hidden>{KIND_ICON[n.kind]}</span>
                <span className="min-w-0 flex-1">{n.label}</span>
                {hasSource && <span className="flex-none text-[9.5px] text-slate-400">{isOpen ? "hide source" : "open source"}</span>}
              </button>

              {isOpen && open && (
                <div className="mb-1.5 animate-fade-in rounded-md border border-slate-200 bg-slate-900 px-2.5 py-2 font-mono text-[10.5px] leading-relaxed text-slate-100">
                  <div className="mb-1 text-[9.5px] uppercase tracking-wider text-teal-300">{open.locator ?? "source"}</div>
                  {open.source_preview ?? "No excerpt stored for this node yet."}
                </div>
              )}

              {n.edge && <div className="pb-1 pl-1 font-mono text-[9.5px] text-slate-400">↓ {n.edge}</div>}
            </li>
          );
        })}
      </ol>

      <div className="mt-2 flex items-center gap-1.5 border-t border-slate-100 pt-2">
        <AgentAvatar id={finding.verified_by ?? finding.agent} size="sm" />
        <span className="text-[11px] text-slate-500">
          {finding.amount_note ? `Amount basis: ${finding.amount_note}. ` : ""}
          Amounts come from the calculation engine, never from the model.
        </span>
      </div>
    </div>
  );
}
