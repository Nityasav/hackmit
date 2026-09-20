"use client";

import { useData } from "@/lib/data";
import { AGENT_NAME, AgentAvatar, Card, CardTitle, PageHeader, Pill, PlaybookStatusPill } from "@/components/ui";
import { TabGate } from "@/components/shell/TabGate";
import { Component as LearningBento } from "@/components/ui/features-card";

const LOOP = [
  { n: "1", title: "Notice a pattern", body: "An agent sees the same case twice across findings" },
  { n: "2", title: "Write a playbook", body: "A rule with scope, validity dates and exclusions" },
  { n: "3 · GATE", title: "Replay past months", body: "Re-run them with the rule. It must add 0 new false positives", gate: true },
  { n: "4 · GATE", title: "You approve", body: "Shows up in Approvals. Agents can never self-activate", gate: true },
  { n: "5", title: "Use and re-check", body: "Applicability is tested on every use. Retired when stale" },
];

export default function LearningPage() {
  const { bundle } = useData();
  const { playbooks, ablation } = bundle;
  const active = playbooks.filter((p) => p.status === "active").length;

  return (
    <TabGate tab="learning">
      <PageHeader
        title="Learning"
        subtitle="How the team improves each month, gated so it can't learn the wrong lesson"
        right={
          ablation?.example ? (
            <Pill tone="amber">Example numbers · real ones come from the evaluator</Pill>
          ) : undefined
        }
      />

      <div className="mb-4 grid gap-2 md:grid-cols-5">
        {LOOP.map((s) => (
          <div key={s.n} className={`rounded-none border p-2 text-[13px] ${s.gate ? "border-ink bg-surface-2" : "border-line bg-surface"}`}>
            <span className="text-[12px] font-bold text-ink">{s.n}</span>
            <b className="mb-0.5 block text-[13.5px]">{s.title}</b>
            {s.body}
          </div>
        ))}
      </div>

      <div className="mb-4">
        <LearningBento />
      </div>

      <div className="grid gap-4 min-[900px]:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardTitle right={`${active} active · ${playbooks.length} total`}>Playbooks the agents wrote</CardTitle>
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-[12px] text-ink-dim">
                <th className="border-b border-line p-1.5 text-left font-semibold">Playbook</th>
                <th className="border-b border-line p-1.5 text-left font-semibold">Replay gate</th>
                <th className="border-b border-line p-1.5 text-left font-semibold">Used</th>
                <th className="border-b border-line p-1.5 text-left font-semibold">Status</th>
              </tr>
            </thead>
            <tbody>
              {playbooks.map((p) => (
                <tr key={p.id} className="align-top">
                  <td className="border-b border-line p-1.5">
                    <div className="flex items-center gap-2">
                      <AgentAvatar id={p.proposed_by} size="sm" />
                      <b>{p.id}</b> {p.title}
                    </div>
                    <div className="pl-7 text-ink-dim">{p.source}</div>
                  </td>
                  <td className={`border-b border-line p-1.5 ${p.replay.passed ? "" : "text-accent-bad"}`}>
                    {p.replay.passed ? `✓ 0 new FP` : `✗ ${p.replay.new_false_positives} false clear`}
                    <div className="text-ink-faint">{p.replay.months.join(" + ")}</div>
                  </td>
                  <td className="border-b border-line p-1.5">{p.uses}</td>
                  <td className="border-b border-line p-1.5">
                    <PlaybookStatusPill status={p.status} note={p.status_note} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 text-[13px] text-ink-dim">
            A playbook is reviewed procedural memory. Agents never edit their own prompts and nothing is fine-tuned.
          </div>
        </Card>

        {ablation && (
          <Card>
            <CardTitle>With memory vs without</CardTitle>
            {ablation.rows.map((r) => {
              const max = Math.max(r.with, r.without) || 1;
              return (
                <div key={r.metric} className="grid grid-cols-[120px_1fr_54px] items-center gap-2 py-1 text-[13px]">
                  <span>{r.metric}</span>
                  <span>
                    <div className="h-2 rounded bg-surface-3" style={{ width: `${(r.without / max) * 100}%` }} />
                    <div className="mt-0.5 h-2 rounded bg-ink" style={{ width: `${(r.with / max) * 100}%` }} />
                  </span>
                  <b className="text-right font-num tabular-nums">
                    {r.without}→{r.with}
                  </b>
                </div>
              );
            })}
            <div className="mt-1.5 text-[12.5px] text-ink-dim">
              <span className="mr-1 inline-block h-2 w-2 rounded-sm bg-surface-3" /> no memory
              <span className="ml-2 mr-1 inline-block h-2 w-2 rounded-sm bg-ink" /> with reviewed memory · {ablation.note}
            </div>
          </Card>
        )}
      </div>

      <div className="mt-4 text-[13px] text-ink-dim">
        Proposed by: {[...new Set(playbooks.map((p) => AGENT_NAME[p.proposed_by]))].join(", ") || "—"}
      </div>
    </TabGate>
  );
}
