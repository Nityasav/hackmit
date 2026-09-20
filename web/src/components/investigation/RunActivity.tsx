"use client";
import { useEffect, useState } from "react";
import { intakeApi } from "@/lib/api";

type Event = { id: string; at: string; agent: string; status: string; detail: string };
const domains = [{ id: "A", name: "Treasurer", count: 4 }, { id: "B", name: "Controller", count: 4 },
  { id: "C", name: "FP&A", count: 5 }, { id: "D", name: "Audit & Controls", count: 4 }];

export function RunActivity({ ws, thread, running }: { ws: string; thread: string; running: boolean }) {
  const [events, setEvents] = useState<Event[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const result = await intakeApi<{ events: Event[] }>(`/api/workspaces/${ws}/agents/activity?thread_id=${encodeURIComponent(thread)}`);
        if (active) { setEvents(result.events); setError(""); }
      } catch { if (active) setError("Live activity unavailable. No execution status is assumed."); }
    };
    if (thread) void load();
    const timer = thread && running ? setInterval(load, 2000) : undefined;
    return () => { active = false; clearInterval(timer); };
  }, [ws, thread, running]);
  const latest = Object.fromEntries(events.filter(e => !["tool", "handoff", "historical_context"].includes(e.status)).map(e => [e.agent, e]));
  return <section aria-label="Live agent activity" className="border-t border-line bg-zinc-50 p-5">
    <div className="mb-4 flex items-center justify-between gap-3"><h3 className="font-semibold">Agent activity</h3><span className="text-xs text-ink-dim">{running ? "Live · updates every 2 seconds" : "Recorded execution"}</span></div>
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{domains.map(domain => <div key={domain.id} className="border border-line bg-white p-3">
      <h4 className="text-sm font-semibold">{domain.name}</h4>
      <div className="mt-3 flex flex-wrap gap-2">{Array.from({ length: domain.count }, (_, i) => {
        const id = domain.id + (i + 1); const status = latest[id]?.status;
        return <button key={id} title={status || "No recorded activity"} onClick={() => setSelected(selected === id ? "" : id)}
          aria-pressed={selected === id}
          className={`h-10 w-10 border text-xs font-semibold ${status === "started" ? "animate-pulse border-ink bg-ink text-white" : status === "completed" ? "border-emerald-600 bg-emerald-50" : status ? "border-amber-500 bg-amber-50" : "border-line text-ink-dim"} ${selected === id ? "ring-2 ring-ink ring-offset-2" : ""}`}>{id}</button>;
      })}</div>
    </div>)}</div>
    <p className="mt-3 text-xs text-ink-dim">Select an agent to inspect its work, handoffs and memory reads. Black: started · Green: completed · Amber: blocked, failed or needs review · Gray: no event.</p>
    {error && <p role="alert" className="mt-3 text-sm text-red-800">{error}</p>}
    <ol className="mt-4 max-h-64 space-y-3 overflow-y-auto border-l border-line pl-4" aria-label="Execution timeline">
      {events.filter(e => !selected || e.agent === selected).map(e => <li key={e.id} className="text-sm">
        <div className="flex flex-wrap gap-2"><time className="font-mono text-xs text-ink-dim" dateTime={e.at}>{new Date(e.at).toLocaleTimeString()}</time><b>{e.agent}</b><span>{e.status.replaceAll("_", " ")}</span></div>
        <p className="mt-1 break-words text-xs text-ink-dim">{e.detail.replaceAll("_", " ")}</p>
      </li>)}
      {!events.length && <li className="text-sm text-ink-dim">No execution events recorded for this run.</li>}
    </ol>
  </section>;
}
