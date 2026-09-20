"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { API_URL, useData } from "@/lib/data";
import { AGENT_NAME, Card, CardTitle, EmptyState, PageHeader, Pill } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_CFO_API_URL || API_URL;
const ACTIVE = new Set(["queued", "planning", "running"]);

interface CFORun {
  id: string;
  request: { workspace: string; mode: string; objective: string };
  status: string;
  model_label: string;
  model_calls: number;
  tool_calls: number;
  briefing: string;
  report_markdown: string;
  unresolved: string[];
  plan: { rationale: string } | null;
  tasks: { spec: { id: string; role: string; objective: string; depends_on: string[] }; status: string; attempts: number }[];
  events: { at: string; actor: string; action: string; detail: string; task_id: string | null }[];
}

async function loadRun(id: string, signal?: AbortSignal): Promise<CFORun> {
  const response = await fetch(`${API}/api/cfo/runs/${encodeURIComponent(id)}`, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`Could not load run (${response.status}).`);
  return response.json();
}

export default function CFORunPage() {
  return (
    <Suspense fallback={<PageHeader title="Investigation run" />}>
      <RunRoute />
    </Suspense>
  );
}

function RunRoute() {
  const runId = useSearchParams().get("run");
  // Keyed so switching runs remounts rather than leaving the previous run on screen.
  return <RunDetail key={runId ?? "none"} runId={runId} />;
}

/** The detail behind one coordinator run. Runs are started from the Command center. */
function RunDetail({ runId }: { runId: string | null }) {
  const { ws } = useData();
  const [run, setRun] = useState<CFORun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const active = !!run && ACTIVE.has(run.status);

  useEffect(() => {
    if (!API || !runId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await loadRun(runId, controller.signal);
        if (controller.signal.aborted) return;
        setRun(next);
        setError(null);
        // Stop polling once the run reaches a terminal state.
        if (ACTIVE.has(next.status)) timer = setTimeout(poll, 1500);
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Unable to load run.");
      }
    };
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [runId]);

  if (!runId)
    return (
      <>
        <PageHeader title="Investigation run" />
        <EmptyState icon="○" title="No run selected">
          Investigations start in the <Link href="/" className="underline">Command center</Link>. Open one from there
          to see its plan, evidence and report.
        </EmptyState>
      </>
    );

  if (error)
    return (
      <>
        <PageHeader title="Investigation run" subtitle={runId} />
        <Card>
          <p role="alert" className="text-accent-bad">{error}</p>
          <p className="mt-2 text-[13px] text-ink-dim">
            A run belongs to the workspace it was started in. This one may belong to a workspace other than {ws}.
          </p>
        </Card>
      </>
    );

  if (!run)
    return <><PageHeader title="Investigation run" subtitle={runId} /><Card>Loading the run…</Card></>;

  return (
    <>
      <PageHeader title="Investigation run" subtitle={run.request.objective} />

      <div className="mb-4 flex flex-wrap items-center gap-2 text-[13px] text-ink-dim">
        <Pill tone={run.status === "completed" ? "green" : "amber"}>{run.status}</Pill>
        <span className="font-mono">{run.id}</span>
        <span>· {run.request.workspace} · {run.model_label}</span>
        <span className="font-num tabular-nums">
          · {run.model_calls} CFO call(s) · {run.tool_calls} evidence tool call(s)
        </span>
      </div>

      <Card>
        <CardTitle>CFO briefing</CardTitle>
        <p className="text-[14px]">{run.briefing}</p>
      </Card>

      {run.plan && (
        <Card className="mt-4">
          <CardTitle right={`${run.tasks.length} task(s)`}>Investigation plan</CardTitle>
          <p className="mb-2 text-[14px] text-ink-dim">{run.plan.rationale}</p>
          {run.tasks.map((task) => (
            <div key={task.spec.id} className="border-t border-line py-2 first:border-t-0">
              <div className="flex flex-wrap items-center gap-2">
                <b className="text-[13.5px]">{AGENT_NAME[task.spec.role as keyof typeof AGENT_NAME] ?? task.spec.role}</b>
                <span className="font-mono text-[12.5px] text-ink-faint">{task.spec.id}</span>
                <Pill tone={task.status === "done" ? "green" : "amber"}>{task.status}</Pill>
              </div>
              <p className="mt-1 text-[13.5px]">{task.spec.objective}</p>
              <small className="text-[12.5px] text-ink-faint">
                Attempts: {task.attempts}; dependencies: {task.spec.depends_on.join(", ") || "none"}
              </small>
            </div>
          ))}
        </Card>
      )}

      {run.unresolved.length > 0 && (
        <Card className="mt-4">
          <CardTitle right={`${run.unresolved.length}`}>Unresolved matters</CardTitle>
          <ul className="list-inside list-disc space-y-1 text-[13.5px]">
            {run.unresolved.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        </Card>
      )}

      {run.report_markdown && (
        <Card className="mt-4">
          <CardTitle right={<Link href="/reports" className="underline">Reports tab</Link>}>Published report</CardTitle>
          <pre className="whitespace-pre-wrap break-words font-mono text-[12.5px] leading-relaxed">
            {run.report_markdown}
          </pre>
        </Card>
      )}

      <Card className="mt-4">
        <CardTitle right={`${run.events.length} event(s)`}>Activity record</CardTitle>
        <p className="mb-2 text-[13px] text-ink-dim">
          Every step the run took. The decisions drawn from these are in the{" "}
          <Link href="/reasoning" className="underline">Reasoning log</Link>.
        </p>
        {run.events.map((event, i) => (
          <details key={i} className="border-t border-line py-2">
            <summary className="cursor-pointer text-[13.5px]">
              {AGENT_NAME[event.actor as keyof typeof AGENT_NAME] ?? event.actor} · {event.action}
              {event.task_id && ` · ${event.task_id}`}
            </summary>
            <p className="mt-1 font-num text-[12px] tabular-nums text-ink-faint">{event.at}</p>
            <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-[12.5px]">{event.detail}</pre>
          </details>
        ))}
      </Card>

      {active && <p className="mt-3 text-[13px] text-ink-dim">This run is still working; the page refreshes itself.</p>}
    </>
  );
}
