"use client";

import Link from "next/link";
import { useState } from "react";
import { useData } from "@/lib/data";
import { SourcesPanel } from "@/components/SourcesPanel";
import { TAB_HREF } from "@/lib/tabs";
import { highlights } from "@/lib/format";
import {
  AgentAvatar,
  AiTag,
  Button,
  Card,
  CardTitle,
  EmptyState,
  PageHeader,
  ProgressBar,
  Pulse,
  Toast,
} from "@/components/ui";

export default function CommandCenter() {
  const { bundle, decideApproval } = useData();
  const [toast, setToast] = useState<string | null>(null);
  const { workspace, agents, briefing, kpis, workflows, tasks, approvals, findings, decisions } = bundle;
  const done = tasks.filter((t) => t.column === "done").length;
  const pendingApprovals = approvals.filter((a) => a.status === "pending");
  const pending = pendingApprovals.length;

  if (workspace.intake) return <><PageHeader title={`${workspace.name} · ${workspace.period}`} subtitle={`snapshot ${workspace.snapshot_id}`} /><SourcesPanel key={workspace.id} /></>;

  return (
    <>
      <PageHeader
        title={`${workspace.name} · ${workspace.period}`}
        subtitle={`snapshot ${workspace.snapshot_id}`}
      />
      <SourcesPanel key={workspace.id} />

      {/* CFO agent briefing */}
      <div className="mb-2.5 rounded-xl border border-green-300 bg-gradient-to-b from-green-50 to-transparent p-3.5">
        <div className="flex items-center gap-2">
          <AgentAvatar id="cfo" />
          <b>CFO Agent</b>
          <AiTag>AI briefing</AiTag>
          <span className="ml-auto text-[11px] text-ink-dim">generated {briefing.generated_at}</span>
        </div>
        <p className="my-2.5 text-[13.5px]">
          {highlights(briefing.text).map(([part, strong], i) =>
            strong ? (
              <b key={i} className="rounded-[3px] bg-surface-3 px-0.5 font-semibold">
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

      {/* The team: one card, divided, so it stays one object at any width */}
      <Card className="mb-2.5 grid grid-cols-1 divide-y divide-line p-0 sm:grid-cols-2 sm:divide-x lg:grid-cols-3 xl:grid-cols-5 xl:divide-y-0">
        {agents.map((a) => (
          <div key={a.id} className="p-2.5">
            <div className="flex items-center gap-1.5 text-[11.5px] font-semibold">
              <AgentAvatar id={a.id} size="sm" />
              {a.name}
              {a.status === "working" && <Pulse className="ml-auto" />}
            </div>
            <div className={`mt-1.5 text-[11px] ${a.status === "working" ? "shimmer-text" : "text-ink-dim"}`}>
              {a.doing}
            </div>
          </div>
        ))}
      </Card>

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
              <div className="mt-1 text-ink-dim">
                Agents read this published PDF only. They have no access to MIT&apos;s internal ledger, and nothing
                here is a claim about MIT beyond what the report states.
              </div>
              {workspace.source_url && (
                <a
                  href={workspace.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block font-semibold text-accent-good underline"
                >
                  Open the report ↗
                </a>
              )}
            </div>
          </Card>
        )}

        <Card className="grid grid-cols-2 divide-x divide-y divide-line p-0">
          {kpis.map((k) => (
            <div key={k.label} className="p-3">
              <small className="block text-[10.5px] text-ink-dim">{k.label}</small>
              <b className="font-display text-xl font-bold">{k.value}</b>
              <em className={`block text-[10.5px] not-italic ${k.tone === "warn" ? "text-ink-dim" : "text-accent-good"}`}>
                {k.note}
              </em>
            </div>
          ))}
          <div className="p-3">
            <small className="block text-[10.5px] text-ink-dim">Tasks done</small>
            <b className="font-display text-xl font-bold">
              {done} / {tasks.length}
            </b>
            <em className="block text-[10.5px] not-italic text-ink-dim">
              {findings.length} findings · {pending} waiting on you
            </em>
          </div>
        </Card>
      </div>

      <div className="mt-2.5 grid gap-2.5 min-[900px]:grid-cols-2">
        <Card>
          <CardTitle right={<Link href="/approvals">all →</Link>}>Waiting on you</CardTitle>
          {pendingApprovals.length === 0 ? (
            <EmptyState title={workspace.kind === "public" ? "Nothing to approve" : "You're all caught up"}>
              {workspace.kind === "public"
                ? "Public reports are read-only, so there is nothing to decide here."
                : "Every proposal has a decision. The agents will queue the next one."}
            </EmptyState>
          ) : (
            pendingApprovals.slice(0, 4).map((a) => (
              <div key={a.id} className="flex items-center gap-2 border-t border-line py-1.5 first:border-t-0">
                <AgentAvatar id={a.agent} size="sm" />
                <div className="min-w-0">
                  <Link href="/approvals" className="block truncate font-semibold hover:text-accent-good">
                    {a.title}
                  </Link>
                  <span className="block truncate text-[11px] text-ink-dim">{a.summary}</span>
                </div>
                <span className="ml-auto flex-none">
                  <Button
                    onClick={() => {
                      decideApproval(a.id, "approved");
                      setToast(`${a.id} approved · dependent reports recomputed`);
                    }}
                  >
                    {a.kind === "payment" ? "Release" : a.kind === "evidence" ? "Provide" : "Approve"}
                  </Button>
                </span>
              </div>
            ))
          )}
        </Card>

        <Card>
          <CardTitle right={<Link href="/reasoning">all →</Link>}>Latest reasoning</CardTitle>
          {decisions.slice(0, 4).map((d) => (
            <Link
              key={d.id}
              href={`/reasoning?q=${encodeURIComponent(d.id)}`}
              className="flex items-start gap-2 border-t border-line py-1.5 first:border-t-0 hover:bg-surface-2"
            >
              <span className="pt-0.5 font-mono text-[10px] text-ink-faint">{d.time}</span>
              <AgentAvatar id={d.agent} size="sm" />
              <span className="min-w-0">
                <b className="block truncate">{d.action}</b>
                <span className="block truncate text-[11px] text-ink-dim">{d.summary}</span>
              </span>
            </Link>
          ))}
        </Card>
      </div>

      <Toast message={toast} onDone={() => setToast(null)} />
    </>
  );
}
