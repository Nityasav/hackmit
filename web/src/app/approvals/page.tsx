"use client";

import { useState } from "react";
import { useData } from "@/lib/data";
import { money } from "@/lib/format";
import type { Approval } from "@/lib/types";
import { AgentAvatar, Button, Card, CardTitle, EmptyState, PageHeader, Pill, Toast } from "@/components/ui";
import { TabGate } from "@/components/shell/TabGate";

const KIND_LABEL = {
  journal: ["Journal correction", "indigo"],
  payment: ["Payment release", "amber"],
  playbook: ["Learning", "teal"],
  evidence: ["Evidence request", "gray"],
} as const;

export default function ApprovalsPage() {
  const { bundle, decideApproval } = useData();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const decide = (id: string, decision: "approved" | "rejected") => {
    decideApproval(id, decision);
    setToast(
      decision === "approved"
        ? `${id} approved · dependent schedules and the close pack recomputed`
        : `${id} rejected · the agent will be told why`,
    );
  };
  const pending = bundle.approvals.filter((a) => a.status === "pending");
  const decided = bundle.approvals.filter((a) => a.status !== "pending");
  const selected = bundle.approvals.find((a) => a.id === selectedId) ?? pending[0] ?? bundle.approvals[0];

  return (
    <TabGate tab="approvals">
      <PageHeader title="Approvals" subtitle="Agents propose. You decide. Nothing moves without you." />
      <div className="grid gap-2.5 min-[900px]:grid-cols-[1fr_1.1fr]">
        <Card>
          <CardTitle right={`${pending.length} pending`}>Waiting on you</CardTitle>
          {pending.length === 0 && (
            <EmptyState title="All clear">
              Nothing needs you. Agents keep working and will queue the next proposal here.
            </EmptyState>
          )}
          {pending.map((a) => (
            <Row key={a.id} approval={a} active={a.id === selected?.id} onClick={() => setSelectedId(a.id)} />
          ))}
          {decided.length > 0 && (
            <>
              <CardTitle>Decided</CardTitle>
              {decided.map((a) => (
                <Row key={a.id} approval={a} active={a.id === selected?.id} onClick={() => setSelectedId(a.id)} />
              ))}
            </>
          )}
        </Card>

        {selected && (
          <Card>
            <CardTitle>
              <AgentAvatar id={selected.agent} size="sm" />
              {selected.title}
              {selected.verified && (
                <span className="ml-auto">
                  <Pill tone="teal">Auditor verified ✓</Pill>
                </span>
              )}
            </CardTitle>
            <p className="mb-2 text-ink-dim">{selected.summary}</p>

            {selected.journal && (
              <table className="w-full border-collapse">
                <thead>
                  <tr className="text-[10px] text-ink-dim">
                    <th className="border-b border-line p-1.5 text-left font-semibold">Account</th>
                    <th className="border-b border-line p-1.5 text-left font-semibold">Fund</th>
                    <th className="border-b border-line p-1.5 text-right font-semibold">Debit</th>
                    <th className="border-b border-line p-1.5 text-right font-semibold">Credit</th>
                  </tr>
                </thead>
                <tbody>
                  {selected.journal.map((l, i) => (
                    <tr key={i}>
                      <td className="border-b border-line p-1.5">{l.account}</td>
                      <td className="border-b border-line p-1.5">{l.fund}</td>
                      <td className="border-b border-line p-1.5 text-right font-mono">
                        {l.debit_cents ? money(l.debit_cents) : "—"}
                      </td>
                      <td className="border-b border-line p-1.5 text-right font-mono">
                        {l.credit_cents ? money(l.credit_cents) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {selected.effects && (
              <div className="mt-2">
                {selected.effects.map((e) => (
                  <div key={e.label} className="flex justify-between py-0.5 text-[11.5px]">
                    <span>{e.label}</span>
                    <b className={e.tone === "good" ? "text-accent-good" : ""}>{e.value}</b>
                  </div>
                ))}
              </div>
            )}

            {selected.status === "pending" ? (
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                <Button primary onClick={() => decide(selected.id, "approved")}>
                  {selected.kind === "payment" ? "Release (simulated)" : selected.kind === "evidence" ? "Mark provided" : "Approve"}
                </Button>
                <Button onClick={() => decide(selected.id, "rejected")}>Reject</Button>
                <Button disabled title="Wired to the orchestrator in the live build">✦ Ask the agent</Button>
              </div>
            ) : (
              <div className="mt-2.5">
                <Pill tone={selected.status === "approved" ? "green" : "red"}>
                  {selected.status === "approved" ? "Approved by you" : "Rejected by you"}
                </Pill>
                <span className="ml-2 text-[11px] text-ink-dim">
                  Dependent schedules and the close pack recompute from this decision.
                </span>
              </div>
            )}

            <div className="mt-2.5 text-[11px] text-ink-dim">
              Approving applies the change to the synthetic scenario only. The as-reported baseline stays intact, and no
              real payment, payroll change or ERP posting happens.
            </div>
          </Card>
        )}
      </div>
      <Toast message={toast} onDone={() => setToast(null)} />
    </TabGate>
  );
}

function Row({ approval, active, onClick }: { approval: Approval; active: boolean; onClick: () => void }) {
  const [label, tone] = KIND_LABEL[approval.kind];
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full cursor-pointer items-center gap-2 rounded-lg border p-2 text-left ${
        active ? "border-green-300 bg-green-50" : "border-transparent hover:bg-surface-2"
      }`}
    >
      <AgentAvatar id={approval.agent} size="sm" />
      <div className="min-w-0">
        <b className="block truncate">{approval.title}</b>
        <span className="truncate text-ink-dim">{approval.summary}</span>
      </div>
      <span className="ml-auto flex-none">
        <Pill tone={approval.status === "approved" ? "green" : approval.status === "rejected" ? "red" : tone}>
          {approval.status === "pending" ? label : approval.status === "approved" ? "Approved" : "Rejected"}
        </Pill>
      </span>
    </button>
  );
}
