"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AGENT_NAME, AgentAvatar, Pill } from "@/components/ui";
import { CFO_API_URL, intakeApi, isAbort } from "@/lib/api";
import { money } from "@/lib/format";

import { agentOf } from "./agents";
import type { AcceptedClaim, CFORun, RunCalculation } from "./run";

const DISPOSITION: Record<string, { label: string; tone: "red" | "green" | "gray" }> = {
  substantiated: { label: "Needs your attention", tone: "red" },
  cleared: { label: "Checked, nothing wrong", tone: "green" },
  explained: { label: "Explained", tone: "gray" },
};

const CATEGORY: Record<RunCalculation["category"], string> = {
  reclassification: "Money recorded against the wrong pot",
  exposure: "Money at risk",
  potential_recovery: "Money that may be recoverable",
  none: "No exception in the numbers",
};

/**
 * What the run produced: only claims the Internal Auditor accepted, each with
 * its amount, its verdict and the original lines behind it. Everything the
 * Auditor did not accept is listed as unresolved rather than quietly dropped.
 */
export function RunFindings({ ws, run, running }: { ws: string; run: CFORun; running: boolean }) {
  const titles = new Map((run.scope?.sources ?? []).map((source) => [source.id, source.title]));

  return (
    <>
      <p className="max-w-prose text-[15px] leading-relaxed">{run.briefing}</p>

      {running && (
        <p className="mt-3 max-w-prose font-accent text-[13.5px] text-ink-dim">
          The run is still going. A conclusion here can still be withdrawn if a later step replaces it.
        </p>
      )}

      {run.accepted.length > 0 && (
        <div className="mt-6 space-y-5">
          {run.accepted.map((accepted) => (
            <Claim key={accepted.claim.id} ws={ws} accepted={accepted} titles={titles} />
          ))}
        </div>
      )}

      {run.accepted.length === 0 && !running && (
        <p className="mt-6 max-w-prose border border-line bg-surface p-5 text-[14px] leading-relaxed">
          No claim passed the Internal Auditor in this run. That is not a clean bill of health. It means nothing
          survived the re-check, and anything the agents raised is in the open questions below.
        </p>
      )}

      {run.unresolved.length > 0 && (
        <div className="mt-8 border-t border-line pt-8">
          <h3 className="text-[15px] font-semibold tracking-tight">Open questions</h3>
          <p className="mt-1.5 max-w-prose text-[13.5px] leading-relaxed text-ink-dim">
            The Internal Auditor did not accept these. They are questions for a person, not conclusions.
          </p>
          <ul className="mt-4 max-w-3xl">
            {run.unresolved.map((item) => (
              <li key={item} className="border-t border-line py-3 text-[13.5px] leading-relaxed">
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 border-t border-line pt-6 text-[13.5px]">
        {run.report_markdown && (
          <a
            className="underline"
            href={`${CFO_API_URL}/api/cfo/runs/${encodeURIComponent(run.id)}/report`}
            target="_blank"
            rel="noreferrer"
          >
            Open the CFO agent&rsquo;s full write-up
          </a>
        )}
        <Link href="/briefing" className="underline">
          Hand the result to the director
        </Link>
      </div>
    </>
  );
}

function Claim({
  ws,
  accepted,
  titles,
}: {
  ws: string;
  accepted: AcceptedClaim;
  titles: Map<string, string>;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const { claim, review, calculation } = accepted;
  const id = agentOf(accepted.role);
  const disposition = DISPOSITION[claim.disposition];

  return (
    <article className="border border-line bg-surface p-5 md:p-6">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {id && <AgentAvatar id={id} size="lg" />}
        <span className="text-[13.5px] font-medium">{id ? AGENT_NAME[id] : accepted.role}</span>
        {disposition && <Pill tone={disposition.tone}>{disposition.label}</Pill>}
      </div>

      <h3 className="mt-3.5 max-w-prose text-[18px] font-semibold leading-snug tracking-tight">{claim.title}</h3>

      {calculation ? (
        <div className="mt-3.5">
          <p className="font-num text-[28px] font-semibold leading-none tracking-tight tabular-nums">
            {money(calculation.amount_cents)}
          </p>
          <p className="mt-2 max-w-prose font-accent text-[13px] text-ink-dim">
            {CATEGORY[calculation.category]} · {calculation.description}
            {calculation.cash_delta_cents === 0
              ? " · no cash moves"
              : ` · cash impact ${money(calculation.cash_delta_cents)}`}
          </p>
        </div>
      ) : (
        <p className="mt-3.5 max-w-prose text-[13px] leading-relaxed text-ink-dim">
          No amount is confirmed here. The agent explains what it found; no calculation stands behind a figure.
        </p>
      )}

      <p className="mt-3.5 max-w-prose text-[14.5px] leading-relaxed">{claim.conclusion}</p>

      <div className="mt-4 max-w-prose border-t border-line pt-3">
        <h4 className="text-[13px] font-semibold">What the Internal Auditor said</h4>
        <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-dim">{review.rationale}</p>
        {review.required_action && (
          <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-dim">Asked for: {review.required_action}</p>
        )}
      </div>

      <div className="mt-4 max-w-prose border-t border-line pt-3">
        <h4 className="text-[13px] font-semibold">What to do next</h4>
        <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-dim">{claim.proposed_action}</p>
      </div>

      <div className="mt-4 border-t border-line pt-3">
        <h4 className="text-[13px] font-semibold">See it for yourself</h4>
        <div className="mt-2.5 flex flex-wrap gap-2">
          {claim.evidence_ids.map((sourceId) => (
            <button
              key={sourceId}
              type="button"
              aria-expanded={open === sourceId}
              onClick={() => setOpen(open === sourceId ? null : sourceId)}
              className="max-w-full truncate border border-line bg-white px-3 py-2 text-[13px] hover:bg-surface-2"
            >
              {open === sourceId ? "Close " : "Open "}
              {titles.get(sourceId) ?? sourceId}
            </button>
          ))}
        </div>
        {open && <SourceReader ws={ws} sourceId={open} />}
      </div>
    </article>
  );
}

interface SourceView {
  id: string;
  name: string;
  line_count: number;
  lines: { number: number; text: string }[];
}

const PAGE = 20;

/** The original file, straight from the records service. Nothing is re-typed on the way. */
function SourceReader({ ws, sourceId }: { ws: string; sourceId: string }) {
  const [start, setStart] = useState(1);
  const [view, setView] = useState<SourceView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void intakeApi<SourceView>(
      `/api/workspaces/${encodeURIComponent(ws)}/sources/${encodeURIComponent(sourceId)}?start=${start}&limit=${PAGE}`,
      { signal: controller.signal },
    )
      .then((next) => {
        if (controller.signal.aborted) return;
        setView(next);
        setError(null);
      })
      .catch((e) => {
        if (isAbort(e)) return;
        setError(e instanceof Error ? e.message : "This file could not be opened.");
      });
    return () => controller.abort();
  }, [ws, sourceId, start]);

  if (error) {
    return (
      <p role="alert" className="mt-3 text-[13px] text-red-800">
        {error}
      </p>
    );
  }
  if (!view) {
    return <p className="mt-3 text-[13px] text-ink-dim">Opening the file…</p>;
  }

  const last = Math.min(view.line_count, start + PAGE - 1);
  return (
    <section aria-label={`Lines from ${view.name}`} className="mt-3 border border-line bg-surface-2 p-3">
      <p className="break-words text-[13px] font-medium">{view.name}</p>
      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed">
        {view.lines.map((line) => `${line.number}  ${line.text}`).join("\n")}
      </pre>
      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <p className="font-num text-[12px] text-ink-dim">
          Lines {start}–{last} of {view.line_count}
        </p>
        <button
          type="button"
          disabled={start === 1}
          onClick={() => setStart(Math.max(1, start - PAGE))}
          className="ml-auto border border-line bg-white px-3 py-1.5 text-[12.5px] disabled:opacity-40"
        >
          Earlier lines
        </button>
        <button
          type="button"
          disabled={last >= view.line_count}
          onClick={() => setStart(start + PAGE)}
          className="border border-line bg-white px-3 py-1.5 text-[12.5px] disabled:opacity-40"
        >
          Later lines
        </button>
      </div>
    </section>
  );
}
