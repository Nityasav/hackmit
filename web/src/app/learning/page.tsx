"use client";

import { useData } from "@/lib/data";
import { AGENT_NAME, AgentAvatar, Card, CardTitle, PageHeader, Pill, PlaybookStatusPill } from "@/components/ui";
import { TabGate } from "@/components/shell/TabGate";

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

      <div className="mb-2.5 grid gap-1.5 md:grid-cols-5">
        {LOOP.map((s) => (
          <div key={s.n} className={`rounded-[9px] border p-2 text-[11px] ${s.gate ? "border-teal-400 bg-teal-50" : "border-line bg-white"}`}>
            <span className="text-[10px] font-bold text-teal-700">{s.n}</span>
            <b className="mb-0.5 block text-[11.5px]">{s.title}</b>
            {s.body}
          </div>
        ))}
      </div>

      <div className="grid gap-2.5 min-[900px]:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardTitle right={`${active} active · ${playbooks.length} total`}>Playbooks the agents wrote</CardTitle>
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-[10px] text-slate-500">
                <th className="border-b border-line p-1.5 text-left font-semibold">Playbook</th>
                <th className="border-b border-line p-1.5 text-left font-semibold">Replay gate</th>
                <th className="border-b border-line p-1.5 text-left font-semibold">Used</th>
                <th className="border-b border-line p-1.5 text-left font-semibold">Status</th>
              </tr>
            </thead>
            <tbody>
              {playbooks.map((p) => (
                <tr key={p.id} className="align-top">
                  <td className="border-b border-slate-100 p-1.5">
                    <div className="flex items-center gap-1.5">
                      <AgentAvatar id={p.proposed_by} size="sm" />
                      <b>{p.id}</b> {p.title}
                    </div>
                    <div className="pl-7 text-slate-500">{p.source}</div>
                  </td>
                  <td className={`border-b border-slate-100 p-1.5 ${p.replay.passed ? "" : "text-red-700"}`}>
                    {p.replay.passed ? `✓ 0 new FP` : `✗ ${p.replay.new_false_positives} false clear`}
                    <div className="text-slate-400">{p.replay.months.join(" + ")}</div>
                  </td>
                  <td className="border-b border-slate-100 p-1.5">{p.uses}</td>
                  <td className="border-b border-slate-100 p-1.5">
                    <PlaybookStatusPill status={p.status} note={p.status_note} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 text-[11px] text-slate-500">
            A playbook is reviewed procedural memory. Agents never edit their own prompts and nothing is fine-tuned.
          </div>
        </Card>

        {ablation && (
          <Card>
            <CardTitle>With memory vs without</CardTitle>
            {ablation.rows.map((r) => {
              const max = Math.max(r.with, r.without) || 1;
              return (
                <div key={r.metric} className="grid grid-cols-[120px_1fr_54px] items-center gap-2 py-1 text-[11px]">
                  <span>{r.metric}</span>
                  <span>
                    <div className="h-2 rounded bg-slate-300" style={{ width: `${(r.without / max) * 100}%` }} />
                    <div className="mt-0.5 h-2 rounded bg-teal-500" style={{ width: `${(r.with / max) * 100}%` }} />
                  </span>
                  <b className="text-right tabular-nums">
                    {r.without}→{r.with}
                  </b>
                </div>
              );
            })}
            <div className="mt-1.5 text-[10.5px] text-slate-500">
              <span className="mr-1 inline-block h-2 w-2 rounded-sm bg-slate-300" /> no memory
              <span className="ml-2 mr-1 inline-block h-2 w-2 rounded-sm bg-teal-500" /> with reviewed memory · {ablation.note}
            </div>
          </Card>
        )}
      </div>

      <div className="mt-2.5 text-[11px] text-slate-500">
        Proposed by: {[...new Set(playbooks.map((p) => AGENT_NAME[p.proposed_by]))].join(", ") || "—"}
      </div>
    </TabGate>
  );
}
