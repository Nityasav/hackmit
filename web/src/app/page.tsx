"use client";

import Link from "next/link";
import { useState } from "react";
import { useData } from "@/lib/data";
import { SourcesPanel } from "@/components/SourcesPanel";
import { TAB_HREF } from "@/lib/tabs";
import { highlights } from "@/lib/format";
import {
  AgentAvatar,
  Button,
  EmptyState,
  Figure,
  PageHeader,
  ProgressBar,
  Pulse,
  Section,
  Toast,
} from "@/components/ui";

export default function CommandCenter() {
  const { bundle, decideApproval } = useData();
  const [toast, setToast] = useState<string | null>(null);
  const { workspace, agents, briefing, kpis, workflows, tasks, approvals, findings, decisions } = bundle;
  const done = tasks.filter((t) => t.column === "done").length;
  const pendingApprovals = approvals.filter((a) => a.status === "pending");
  const pending = pendingApprovals.length;

  if (workspace.intake) return <><PageHeader title={`${workspace.name} · ${workspace.period}`} /><SourcesPanel key={workspace.id} /></>;

  return (
    <div className="mx-auto max-w-[1180px]">
      {/* The briefing is the one thing on this page that gets to be loud. */}
      <Section first>
        <div className="flex items-center gap-2">
          <b className="text-[14px]">CFO Agent</b>
        </div>
        <p className="mt-4 max-w-[68ch] text-[17px] leading-[1.6]">
          {highlights(briefing.text).map(([part, strong], i) =>
            strong ? (
              // A filled block per phrase breaks the line into patches; weight plus a
              // hairline under the words marks them without chopping up the paragraph.
              <b key={i} className="font-semibold decoration-ink/30 underline decoration-1 underline-offset-[5px]">
                {part}
              </b>
            ) : (
              <span key={i}>{part}</span>
            ),
          )}
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          {briefing.actions.map((a) => (
            <Link key={a.label} href={TAB_HREF[a.href]}>
              <Button primary={a.primary}>{a.label}</Button>
            </Link>
          ))}
        </div>
      </Section>

      {/* The numbers, as one strip divided by hairlines rather than five boxes. */}
      <Section>
        <div className="grid grid-cols-2 gap-y-6 sm:grid-cols-3 lg:grid-cols-5 lg:divide-x lg:divide-line">
          {kpis.map((k) => (
            <Figure key={k.label} label={k.label} value={k.value} note={k.note} tone={k.tone === "warn" ? "warn" : "good"} />
          ))}
          <Figure
            label="Tasks done"
            value={`${done} / ${tasks.length}`}
            note={`${findings.length} findings · ${pending} waiting on you`}
          />
        </div>
      </Section>

      <div className="mt-8 grid gap-8 border-t border-line pt-8 min-[980px]:grid-cols-2">
        <section>
          <div className="mb-4 flex items-baseline gap-3">
            <h2 className="text-[15px] font-semibold tracking-tight">Waiting on you</h2>
            <Link href="/approvals" className="ml-auto font-accent text-[13px] text-ink-dim hover:text-ink">
              all
            </Link>
          </div>
          {pendingApprovals.length === 0 ? (
            <EmptyState title={workspace.kind === "public" ? "Nothing to approve" : "You're all caught up"}>
              {workspace.kind === "public"
                ? "Public reports are read-only, so there is nothing to decide here."
                : "Every proposal has a decision. The agents will queue the next one."}
            </EmptyState>
          ) : (
            pendingApprovals.slice(0, 4).map((a) => (
              <div key={a.id} className="flex items-center gap-3 border-t border-line py-4 first:border-t-0 first:pt-0">
                <AgentAvatar id={a.agent} size="sm" />
                <div className="min-w-0 flex-1">
                  <Link href="/approvals" className="block truncate text-[14px] font-semibold hover:underline">
                    {a.title}
                  </Link>
                  <span className="mt-0.5 block truncate font-accent text-[13px] text-ink-dim">{a.summary}</span>
                </div>
                <Button
                  onClick={() => {
                    decideApproval(a.id, "approved");
                    setToast(`${a.id} approved · dependent reports recomputed`);
                  }}
                >
                  {a.kind === "payment" ? "Release" : a.kind === "evidence" ? "Provide" : "Approve"}
                </Button>
              </div>
            ))
          )}
        </section>

        <section>
          <div className="mb-4 flex items-baseline gap-3">
            <h2 className="text-[15px] font-semibold tracking-tight">Latest reasoning</h2>
            <Link href="/reasoning" className="ml-auto font-accent text-[13px] text-ink-dim hover:text-ink">
              all
            </Link>
          </div>
          {decisions.slice(0, 4).map((d) => (
            <Link
              key={d.id}
              href={`/reasoning?q=${encodeURIComponent(d.id)}`}
              className="flex items-start gap-3 border-t border-line py-4 first:border-t-0 first:pt-0 hover:bg-surface-2"
            >
              <span className="pt-0.5 font-num text-[12.5px] tabular-nums text-ink-faint">{d.time}</span>
              <AgentAvatar id={d.agent} size="sm" />
              <span className="min-w-0 flex-1">
                <b className="block truncate text-[14px]">{d.action}</b>
                <span className="mt-0.5 block truncate font-accent text-[13px] text-ink-dim">{d.summary}</span>
              </span>
            </Link>
          ))}
        </section>
      </div>

      {workflows.length > 0 ? (
        <Section title="This close" right={<Link href="/workflows" className="hover:text-ink">open</Link>}>
          {workflows.map((w) => (
            <div
              key={w.id}
              className="grid grid-cols-[minmax(0,240px)_1fr_52px] items-center gap-4 border-t border-line py-3 text-[14px] first:border-t-0 first:pt-0"
            >
              <span className="truncate">{w.name}</span>
              <ProgressBar value={w.progress} />
              <b className="text-right font-num tabular-nums">{w.progress}%</b>
            </div>
          ))}
        </Section>
      ) : (
        <Section title="Source" right={<Link href="/findings" className="hover:text-ink">evidence</Link>}>
          <p className="max-w-[68ch] text-[14px]">
            <b>MIT FY2025 Uniform Guidance report</b> · year ended June 30, 2025 · independent auditor PwC.
          </p>
          <p className="mt-2 max-w-[68ch] font-accent text-[13.5px] text-ink-dim">
            Agents read this published PDF only. They have no access to MIT&apos;s internal ledger, and nothing here is
            a claim about MIT beyond what the report states.
          </p>
          {workspace.source_url && (
            <a
              href={workspace.source_url}
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-block text-[14px] font-semibold underline"
            >
              Open the report
            </a>
          )}
        </Section>
      )}

      {/* The team, kept quiet: it is context for the work above, not the work itself. */}
      <Section title="The team">
        <div className="grid grid-cols-1 gap-y-4 sm:grid-cols-2 lg:grid-cols-3 lg:divide-x lg:divide-line xl:grid-cols-5">
          {agents.map((a) => (
            <div key={a.id} className="px-5 first:pl-0 last:pr-0">
              <div className="flex items-center gap-2 text-[13.5px] font-semibold">
                <AgentAvatar id={a.id} size="sm" />
                <span className="truncate">{a.name}</span>
                {a.status === "working" && <Pulse className="ml-auto" />}
              </div>
              <div className={`mt-2 font-accent text-[13px] ${a.status === "working" ? "shimmer-text" : "text-ink-dim"}`}>
                {a.doing}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Where the records come from. Below the close, since a demo workspace is already loaded. */}
      <Section>
        <SourcesPanel key={workspace.id} />
      </Section>

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
