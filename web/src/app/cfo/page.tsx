"use client";

import { useEffect, useState } from "react";
import { useData } from "@/lib/data";
import { Button, Card, CardTitle, PageHeader, Pill } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_CFO_API_URL ?? process.env.NEXT_PUBLIC_API_URL;
const ACTIVE = new Set(["queued", "planning", "running"]);
type Mode = "scripted" | "model_preview" | "live";
interface CFORun {
  id: string;
  request: { workspace: string; mode: Mode; objective: string };
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

export default function CFOPage() {
  const { ws } = useData();
  const [objective, setObjective] = useState("Review the current close, identify evidence gaps, and prepare a CFO briefing.");
  const [mode, setMode] = useState<Mode>("scripted");
  const [run, setRun] = useState<CFORun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [savedId, setSavedId] = useState("");
  const runId = run?.id;
  const active = !!run && ACTIVE.has(run.status);

  useEffect(() => {
    if (!API || !runId || !active) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await loadRun(runId, controller.signal);
        if (!controller.signal.aborted) { setRun(next); setError(null); }
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Unable to refresh run.");
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, 1500);
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [runId, active]);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      const response = await fetch(`${API}/api/cfo/runs`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace: ws, objective, mode }),
      });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(typeof body.detail === "string" ? body.detail : `Run could not start (${response.status}).`);
      }
      const next: CFORun = await response.json();
      setRun(next);
      setSavedId(next.id);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to start run."); }
    finally { setStarting(false); }
  }

  async function restore() {
    try { setRun(await loadRun(savedId.trim())); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to load run."); }
  }

  return (
    <>
      <PageHeader title="CFO investigation" subtitle="Plan the work, review the evidence, and prepare a report" />
      <Card>
        <CardTitle>Start an investigation · {ws}</CardTitle>
        <label className="block text-xs font-semibold" htmlFor="cfo-objective">What should the CFO investigate?</label>
        <textarea id="cfo-objective" value={objective} onChange={(e) => setObjective(e.target.value)} maxLength={2000}
          className="my-2 min-h-20 w-full rounded-lg border border-line p-2" />
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="cfo-mode">Run mode</label>
          <select id="cfo-mode" value={mode} onChange={(e) => setMode(e.target.value as Mode)} className="rounded border border-line p-2">
            <option value="scripted">Scripted integration demo</option>
            <option value="model_preview">Live CFO + scripted collaborators</option>
            <option value="live">Live connected team</option>
          </select>
          <Button primary disabled={!API || starting || active || !objective.trim()} onClick={() => void start()}>
            {starting ? "Starting…" : active ? "Investigation running" : "Start investigation"}
          </Button>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          {mode === "scripted" ? "A fixed example exercises the orchestration and accounting code without a model call."
            : mode === "model_preview" ? "The CFO plans and writes using a real model. Data, specialists, and auditor are scripted examples."
            : "Uses the connected data source, specialist agents, and independent auditor. Missing integrations are reported explicitly."}
          {" "}All financial changes remain proposals for human review.
        </p>
        {!API && <p className="mt-2 text-amber-800">The CFO service is not connected. Configure its API URL to start an investigation.</p>}
        {error && <p role="alert" className="mt-2 text-red-700">{error}</p>}
        <div className="mt-3 flex gap-2">
          <input aria-label="Saved CFO run ID" value={savedId} onChange={(e) => setSavedId(e.target.value)} placeholder="Saved run ID"
            className="min-w-0 rounded border border-line px-2 py-1" />
          <Button disabled={!API || !savedId.trim() || active} onClick={() => void restore()}>Open saved run</Button>
        </div>
      </Card>
      {run && <>
        <div className="my-3 flex flex-wrap items-center gap-2 text-xs">
          <Pill tone={run.status === "completed" ? "green" : "amber"}>{run.status}</Pill>
          <span>{run.id} · {run.request.workspace} · {run.request.mode} · {run.model_label}</span>
          <span>{run.model_calls} CFO calls · {run.tool_calls} evidence tool calls</span>
        </div>
        <Card><CardTitle>CFO briefing</CardTitle><p>{run.briefing}</p></Card>
        {run.plan && <Card className="mt-3">
          <CardTitle>Investigation plan</CardTitle><p className="mb-2 text-slate-600">{run.plan.rationale}</p>
          {run.tasks.map((task) => <div key={task.spec.id} className="border-t border-line py-2">
            <b>{task.spec.role.toUpperCase()} · {task.spec.id}</b> <span className="text-teal-700">{task.status}</span>
            <p>{task.spec.objective}</p>
            <small className="text-slate-500">Attempts: {task.attempts}; dependencies: {task.spec.depends_on.join(", ") || "none"}</small>
          </div>)}
        </Card>}
        {run.unresolved.length > 0 && <Card className="mt-3"><CardTitle>Unresolved matters</CardTitle>
          <ul className="list-disc space-y-1 pl-5">{run.unresolved.map((item, i) => <li key={i}>{item}</li>)}</ul>
        </Card>}
        {run.report_markdown && <Card className="mt-3"><CardTitle>Review report</CardTitle>
          <a href={`${API}/api/cfo/runs/${run.id}/report`} target="_blank" rel="noreferrer" className="text-teal-700 underline">Open Markdown report</a>
          <pre className="mt-3 whitespace-pre-wrap break-words text-xs leading-relaxed">{run.report_markdown}</pre>
        </Card>}
        <Card className="mt-3"><CardTitle>Activity record</CardTitle>
          {run.events.map((event, i) => <details key={i} className="border-t border-line py-2">
            <summary className="cursor-pointer">{event.actor.toUpperCase()} · {event.action} {event.task_id && `· ${event.task_id}`}</summary>
            <p className="mt-1 text-xs text-slate-500">{event.at}</p>
            <pre className="mt-1 whitespace-pre-wrap break-words text-xs">{event.detail}</pre>
          </details>)}
        </Card>
      </>}
    </>
  );
}
