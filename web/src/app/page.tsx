"use client";

import Link from "next/link";
import { useData } from "@/lib/data";
import { SourcesPanel } from "@/components/SourcesPanel";
import { TAB_HREF } from "@/lib/tabs";
import { highlights } from "@/lib/format";
import { AgentAvatar, AiTag, Button, Card, CardTitle, PageHeader, ProgressBar, Pulse } from "@/components/ui";

export default function CommandCenter() {
  const { bundle } = useData();
  const { workspace, agents, briefing, kpis, workflows, tasks, approvals, findings } = bundle;
  const done = tasks.filter((t) => t.column === "done").length;
  const pending = approvals.filter((a) => a.status === "pending").length;

  if (workspace.intake) return <><PageHeader title={`${workspace.name} · ${workspace.period}`} subtitle={`snapshot ${workspace.snapshot_id}`} /><SourcesPanel key={workspace.id} /></>;

  return (
    <>
      <PageHeader
        title={`${workspace.name} · ${workspace.period}`}
        subtitle={`snapshot ${workspace.snapshot_id}`}
      />
      <SourcesPanel key={workspace.id} />

      {/* CFO agent briefing */}
      <div className="mb-2.5 rounded-xl border border-teal-200 bg-gradient-to-b from-teal-50 to-white p-3.5">
        <div className="flex items-center gap-2">
          <AgentAvatar id="cfo" />
          <b>CFO Agent</b>
          <AiTag>AI briefing</AiTag>
          <span className="ml-auto text-[11px] text-slate-500">generated {briefing.generated_at}</span>
        </div>
        <p className="my-2.5 text-[13.5px]">
          {highlights(briefing.text).map(([part, strong], i) =>
            strong ? (
              <b key={i} className="rounded-[3px] bg-yellow-100 px-0.5 font-semibold">
                {part}
              </b>
            ) : (
              <span key={i}>{part}</span>
            ),
          )}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {briefing.actions.map((a) => (
            <Link key={a.label} href={TAB_HREF[a.href]}>
              <Button primary={a.primary}>{a.label}</Button>
            </Link>
          ))}
        </div>
      </div>

      {/* The team */}
      <div className="mb-2.5 grid gap-2 md:grid-cols-5">
        {agents.map((a) => (
          <Card key={a.id} className="p-2.5">
            <div className="flex items-center gap-1.5 text-[11.5px] font-semibold">
              <AgentAvatar id={a.id} size="sm" />
              {a.name}
              {a.status === "working" && <Pulse className="ml-auto" />}
            </div>
            <div className={`mt-1.5 min-h-[30px] text-[11px] ${a.status === "working" ? "shimmer-text" : "text-slate-500"}`}>
              {a.doing}
            </div>
          </Card>
        ))}
      </div>

      <div className="grid gap-2.5 lg:grid-cols-[1.4fr_1fr]">
        {workflows.length > 0 ? (
          <Card>
            <CardTitle right={<Link href="/workflows">open →</Link>}>Financial workflows this close</CardTitle>
            {workflows.map((w) => (
              <div key={w.id} className="grid grid-cols-[160px_1fr_34px] items-center gap-2 py-1 text-[11.5px]">
                <span className="truncate">{w.name}</span>
                <ProgressBar value={w.progress} />
                <b className="text-right tabular-nums">{w.progress}%</b>
              </div>
            ))}
          </Card>
        ) : (
          <Card>
            <CardTitle right={<Link href="/findings">evidence →</Link>}>Source</CardTitle>
            <div className="text-[12.5px]">
              <b>MIT FY2025 Uniform Guidance report</b> · year ended June 30, 2025 · independent auditor PwC.
              <div className="mt-1 text-slate-500">
                Agents read this published PDF only. They have no access to MIT&apos;s internal ledger, and nothing
                here is a claim about MIT beyond what the report states.
              </div>
              {workspace.source_url && (
                <a
                  href={workspace.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block font-semibold text-teal-700 underline"
                >
                  Open the report ↗
                </a>
              )}
            </div>
          </Card>
        )}

        <div className="grid grid-cols-2 gap-2.5">
          {kpis.map((k) => (
            <Card key={k.label}>
              <small className="block text-[10.5px] text-slate-500">{k.label}</small>
              <b className="text-xl font-bold tracking-tight">{k.value}</b>
              <em className={`block text-[10.5px] not-italic ${k.tone === "warn" ? "text-amber-700" : "text-teal-700"}`}>
                {k.note}
              </em>
            </Card>
          ))}
          <Card>
            <small className="block text-[10.5px] text-slate-500">Tasks done</small>
            <b className="text-xl font-bold tracking-tight tabular-nums">
              {done} / {tasks.length}
            </b>
            <em className="block text-[10.5px] not-italic text-slate-500">
              {findings.length} findings · {pending} waiting on you
            </em>
          </Card>
        </div>
      </div>
    </>
  );
}
