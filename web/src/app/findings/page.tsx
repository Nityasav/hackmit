"use client";

import Link from "next/link";
import { useState } from "react";
import { useData } from "@/lib/data";
import { money } from "@/lib/format";
import { AgentAvatar, Card, EmptyState, FindingStatusPill, PageHeader } from "@/components/ui";
import { EvidenceTrail } from "@/components/findings/EvidenceTrail";

export default function FindingsPage() {
  const { bundle } = useData();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = bundle.findings.find((f) => f.id === selectedId) ?? bundle.findings[0];
  // Approvals link to their finding; the reverse link is derived from the same
  // field rather than added to the contract, so navigation works both ways.
  const proposal = selected && bundle.approvals.find((a) => a.finding_id === selected.id);
  const approvalsOff = bundle.workspace.disabled_tabs.includes("approvals");

  return (
    <>
      <PageHeader title="Findings" subtitle="What the agents found, and the evidence behind it" />
      <div className="grid gap-4 min-[900px]:grid-cols-[1.4fr_1fr] [&>*]:min-w-0">
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
                f.id === selected?.id ? "border-ink bg-surface-2" : "border-transparent hover:bg-surface-2"
              }`}
            >
              <AgentAvatar id={f.agent} size="sm" />
              <div className="min-w-0">
                <b className="block truncate">{f.title}</b>
                <span className="text-ink-dim">{f.summary}</span>
              </div>
              <span className="ml-auto flex flex-none items-center gap-2">
                {f.amount_cents != null && <b className="font-num tabular-nums">{money(f.amount_cents)}</b>}
                <FindingStatusPill status={f.status} />
              </span>
            </button>
          ))}
        </Card>

        {selected && (
          <Card>
            <EvidenceTrail key={selected.id} finding={selected} />
            {proposal && !approvalsOff && (
              <div className="mt-2 border-t border-line pt-2 text-[13px]">
                <Link href="/approvals" className="text-ink underline">
                  {proposal.status === "pending"
                    ? `${proposal.id} is waiting on your decision →`
                    : `${proposal.id} was ${proposal.status} by you →`}
                </Link>
              </div>
            )}
          </Card>
        )}
      </div>
    </>
  );
}
