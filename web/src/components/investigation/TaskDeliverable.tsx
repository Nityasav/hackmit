"use client";

import { useEffect, useState } from "react";
import { api, intakeApi } from "@/lib/api";

type Deliverable = {
  id: string; agent_name: string; objective: string | null; created_at: string;
  legacy: boolean; stale: boolean; snapshot_id: string | null; review: string;
  workspace: { currency: string };
  result: { summary: string; rationale: string; disposition: string; proposed_action: string;
    exceptions?: { code: string; detail: string }[]; open_questions?: string[] };
  evidence: { role: string; record_key: string; source_id?: string; source_name?: string; line?: number; note?: string }[];
  calculations: Record<string, unknown>;
  memory_context?: { decision_id: string; from_name: string; kind: string; same_snapshot: boolean; summary: string }[];
};

export function TaskDeliverable({ ws, decision }: { ws: string; decision: string }) {
  const [data, setData] = useState<Deliverable | null>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const path = `/api/workspaces/${encodeURIComponent(ws)}/agents/deliverables/${encodeURIComponent(decision)}`;
  useEffect(() => {
    const controller = new AbortController();
    void intakeApi<Deliverable>(path, { signal: controller.signal }).then(setData).catch(e => {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Output unavailable.");
    });
    return () => controller.abort();
  }, [path]);
  async function download() {
    setDownloading(true); setError("");
    try {
      const response = await api.get(path + "/pdf", { responseType: "blob", timeout: 60000 });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a"); link.href = url; link.download = `sherlock-${decision}.pdf`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setError("PDF could not be downloaded. Your task output is still saved."); }
    finally { setDownloading(false); }
  }
  return <section aria-label="Task deliverable" className="mb-5 space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-lg font-semibold">Task deliverable</h3>
      <button disabled={!data || downloading} onClick={() => void download()} className="bg-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">{downloading ? "Preparing…" : "Download PDF"}</button></div>
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
    {!data && !error && <p className="text-sm text-ink-dim">Loading saved output…</p>}
    {data && <>
      {(data.stale || data.legacy) && <p className="border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed">{data.stale ? "Historical output: the books have changed or its snapshot is unknown. " : ""}{data.legacy ? "Older task: only the previously recorded answer and evidence are available." : ""}</p>}
      <div className="border-l-2 border-ink bg-surface-2 p-4"><h4 className="text-xs font-semibold uppercase tracking-wider text-ink-dim">Your request</h4><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed">{data.objective || "The original request was not saved for this older task."}</p></div>
      <div><span className="inline-block bg-surface-2 px-2 py-1 text-xs">{data.result.disposition.replaceAll("_", " ")}</span><h4 className="mt-3 text-sm font-semibold">Answer</h4><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed">{data.result.summary}</p></div>
      <div><h4 className="text-sm font-semibold">Recommended next step</h4><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-ink-dim">{data.result.proposed_action}</p></div>
      <SavedFigures calculations={data.calculations} currency={data.workspace.currency} />
      {!!data.memory_context?.length && <details className="border border-line p-3"><summary className="cursor-pointer text-sm font-semibold">Agent handoffs & memory ({data.memory_context.length})</summary><ul className="mt-3 space-y-3">{data.memory_context.map(item => <li key={item.decision_id} className="text-xs leading-relaxed"><b>{item.from_name}</b> · {item.kind === "handoff" ? "This run" : "Prior context"}{!item.same_snapshot && " · Earlier snapshot, re-check required"}<p className="mt-1 text-ink-dim">{item.summary}</p></li>)}</ul></details>}
      {!!data.result.exceptions?.length && <details className="border border-line p-3"><summary className="cursor-pointer text-sm font-semibold">Issues ({data.result.exceptions.length})</summary><ul className="mt-3 space-y-3">{data.result.exceptions.map((e, i) => <li key={i} className="text-sm"><b>{e.code.replaceAll("_", " ")}</b><p className="mt-1 leading-relaxed">{e.detail}</p></li>)}</ul></details>}
      <details className="border border-line p-3"><summary className="cursor-pointer text-sm font-semibold">Reasoning and evidence ({data.evidence.length})</summary>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">{data.result.rationale}</p>
        <ul className="mt-3 space-y-2">{data.evidence.map((e, i) => <li key={i} className="break-words border-t border-line pt-2 text-xs leading-relaxed"><b>{e.source_name || e.role.replaceAll("_", " ")}</b> · {e.record_key}{e.line ? ` · line ${e.line}` : ""}{e.note && <p>{e.note}</p>}</li>)}</ul>
        {!data.evidence.length && <p className="mt-2 text-xs text-ink-dim">No source citations were recorded.</p>}
      </details>
      {!!data.result.open_questions?.length && <details className="border border-line p-3"><summary className="cursor-pointer text-sm font-semibold">Open questions ({data.result.open_questions.length})</summary><ul className="mt-3 list-disc space-y-2 pl-4 text-sm">{data.result.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ul></details>}
      {!!Object.keys(data.calculations).length && <details className="border border-line p-3"><summary className="cursor-pointer text-sm font-semibold">Recorded calculations</summary><pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(data.calculations, null, 2)}</pre></details>}
      <p className="break-words text-xs leading-relaxed text-ink-dim">{data.review} Saved {new Date(data.created_at).toLocaleString()}. This is the recorded task output, not a fresh analysis or audit opinion.</p>
    </>}
  </section>;
}

function SavedFigures({ calculations, currency }: { calculations: Record<string, unknown>; currency: string }) {
  const rows: { label: string; value: number }[] = [];
  const aging = calculations.age_receivables as { buckets_cents?: Record<string, number> } | undefined;
  if (aging?.buckets_cents) for (const [label, value] of Object.entries(aging.buckets_cents)) rows.push({ label, value });
  if (!rows.length) for (const [key, value] of Object.entries(calculations)) {
    if (!key.startsWith("variance:")) continue;
    const detail = (value as { detail?: { explained?: { name: string; variance_cents: number | null }[]; name?: string; variance_cents?: number | null } })?.detail;
    const values = detail?.explained || (detail?.name ? [{ name: detail.name, variance_cents: detail.variance_cents }] : []);
    for (const row of values) if (typeof row.variance_cents === "number") rows.push({ label: row.name, value: row.variance_cents });
  }
  if (!rows.length) return null;
  const max = Math.max(1, ...rows.map(r => Math.abs(r.value)));
  return <div className="border border-line bg-surface-2 p-4"><h4 className="mb-3 text-sm font-semibold">{aging ? "Receivables aging" : "Budget variances"} · this task</h4><div className="space-y-3">{rows.map((row, i) => <div key={i}><div className="mb-1 flex justify-between gap-3 text-xs"><span>{row.label}</span><span>{new Intl.NumberFormat("en-US", { style: "currency", currency }).format(row.value / 100)}</span></div><div className="h-2 bg-zinc-200"><div className="h-2 bg-ink" style={{ width: `${Math.abs(row.value) / max * 100}%` }} /></div></div>)}</div></div>;
}
