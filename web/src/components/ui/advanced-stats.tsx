"use client";

import { useMemo, useRef } from "react";

import { cn } from "@/lib/utils";
import { useData } from "@/lib/data";
import { money } from "@/lib/format";
import {
  ClippedAreaChart,
  type ClippedAreaPoint,
} from "@/components/ui/advanced-stats-utils/charts";
import { TimelineAnimation } from "@/components/ui/advanced-stats-utils/timeline-animation";

/** A finding is settled when nothing further is owed on it. */
const SETTLED = new Set(["cleared", "explained", "ties", "none_reported"]);

export default function AdvancedStats() {
  const timelineRef = useRef<HTMLDivElement>(null);
  const { bundle } = useData();
  const { kpis, findings, workflows, tasks, approvals } = bundle;

  // Cumulative walk over the real findings: what each one added to the pile,
  // and how much of that pile is already accounted for.
  const series = useMemo<ClippedAreaPoint[]>(
    () =>
      findings
        .filter((f) => f.amount_cents != null)
        .reduce<ClippedAreaPoint[]>((acc, f) => {
          const prev = acc.at(-1);
          const amount = Math.abs(f.amount_cents ?? 0);
          const settled = SETTLED.has(f.status);
          acc.push({
            label: f.id,
            open_cents: (prev?.open_cents ?? 0) + (settled ? 0 : amount),
            cleared_cents: (prev?.cleared_cents ?? 0) + (settled ? amount : 0),
          });
          return acc;
        }, []),
    [findings],
  );

  const exposure = series.at(-1);
  const total = (exposure?.open_cents ?? 0) + (exposure?.cleared_cents ?? 0);
  const settledPct = total === 0 ? 100 : Math.round(((exposure?.cleared_cents ?? 0) / total) * 100);

  const closeProgress = workflows.length
    ? Math.round(workflows.reduce((sum, w) => sum + w.progress, 0) / workflows.length)
    : Math.round((tasks.filter((t) => t.column === "done").length / Math.max(tasks.length, 1)) * 100);

  const openCount = findings.filter((f) => !SETTLED.has(f.status)).length;
  const verified = findings.filter((f) => f.verified_by).length;

  if (series.length === 0) return null;

  return (
    <section ref={timelineRef} className="flex flex-col gap-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <TimelineAnimation
          animationNum={1}
          timelineRef={timelineRef}
          className="rounded-[10px] border border-line bg-surface p-3 lg:col-span-2"
        >
          <div className="mb-2 flex items-baseline gap-2">
            <h2 className="text-[14px] font-semibold">Exposure across the close</h2>
            <span className="text-[13px] text-ink-dim">
              cumulative, in order the agents filed
            </span>
          </div>
          <ClippedAreaChart data={series} />
        </TimelineAnimation>

        <div className="flex flex-col gap-4">
          <TimelineAnimation
            animationNum={2}
            timelineRef={timelineRef}
            className="flex h-full flex-col justify-between rounded-[10px] border border-ink bg-surface-2 p-3"
          >
            <div>
              <div className="text-[13px] text-ink-dim">Money accounted for</div>
              <h3 className="mt-0.5 text-[14px] font-semibold">
                {money(exposure?.cleared_cents ?? 0)} of {money(total)}
              </h3>
            </div>
            <div className="mt-4">
              <div className="mb-1.5 flex items-end justify-between">
                <span className="text-2xl font-bold tabular-nums">
                  {settledPct}%
                </span>
                <span className="mb-1 text-[13px] text-ink-dim">
                  {openCount} still open
                </span>
              </div>
              <div
                role="progressbar"
                aria-valuenow={settledPct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Share of flagged money that is accounted for"
                className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3"
              >
                <div
                  className="h-full rounded-full bg-ink transition-[width] duration-700"
                  style={{ width: `${settledPct}%` }}
                />
              </div>
            </div>
          </TimelineAnimation>

          <TimelineAnimation
            animationNum={3}
            timelineRef={timelineRef}
            className="h-full rounded-[10px] border border-line bg-surface p-3"
          >
            <h3 className="text-[14px] font-semibold">Auditor check</h3>
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-dim">
              The Internal Auditor re-read the sources and redid the math on{" "}
              <span className="font-semibold text-ink">
                {verified} of {findings.length}
              </span>{" "}
              findings. Workflows are {closeProgress}% through the close.
            </p>
          </TimelineAnimation>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {kpis.map((kpi, i) => (
          <TimelineAnimation
            key={kpi.label}
            animationNum={4 + i}
            timelineRef={timelineRef}
            className={cn(
              "rounded-[10px] border border-line bg-surface p-3 transition-colors",
              kpi.tone === "warn" ? "hover:border-ink-faint" : "hover:border-ink",
            )}
          >
            <p className="mb-1.5 text-[12.5px] text-ink-dim">{kpi.label}</p>
            <div className="flex items-baseline justify-between gap-2">
              <p className="text-xl font-bold tabular-nums">{kpi.value}</p>
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-[12.5px] font-semibold",
                  kpi.tone === "warn"
                    ? "bg-surface-2 text-ink-dim"
                    : "bg-surface-2 text-ink",
                )}
              >
                {kpi.note}
              </span>
            </div>
          </TimelineAnimation>
        ))}
        <TimelineAnimation
          animationNum={4 + kpis.length}
          timelineRef={timelineRef}
          className="rounded-[10px] border border-line bg-surface p-3 transition-colors hover:border-ink"
        >
          <p className="mb-1.5 text-[12.5px] text-ink-dim">Waiting on you</p>
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-xl font-bold tabular-nums">
              {approvals.filter((a) => a.status === "pending").length}
            </p>
            <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[12.5px] font-semibold text-ink-dim">
              of {approvals.length}
            </span>
          </div>
        </TimelineAnimation>
      </div>
    </section>
  );
}
