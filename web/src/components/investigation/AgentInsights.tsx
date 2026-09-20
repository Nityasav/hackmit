"use client";
import { useState } from "react";
import { intakeApi } from "@/lib/api";
type Insight = { snapshot_id: string; currency: string; data: {
  buckets_cents?: Record<string, number>; outstanding_cents?: number;
  explained?: { account: string; name: string; actual_cents: number; planned_cents: number | null;
    variance_cents: number; drivers: { event_ref?: string; amount_cents: number; evidence: { source_id: string; line: number }[] }[] }[];
} };
export function AgentInsights({ ws, agent }: { ws: string; agent: string }) {
  const [data, setData] = useState<Insight | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true); setError("");
    try { setData(await intakeApi(`/api/workspaces/${ws}/agents/${agent}/insights`)); }
    catch (e) { setError(e instanceof Error ? e.message : "Figures unavailable"); }
    finally { setBusy(false); }
  }
  const money = (n: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: data?.currency || "USD" }).format(n / 100);
  const rows = data?.data.buckets_cents ? Object.entries(data.data.buckets_cents).map(([name, amount]) => ({ name, amount })) :
    (data?.data.explained || []).map(row => ({ name: row.name, amount: row.variance_cents }));
  const max = Math.max(1, ...rows.map(row => Math.abs(row.amount)));
  return <div className="mt-3">
    <button className="border border-line px-3 py-2 text-xs font-semibold" disabled={busy} onClick={() => void load()}>
      {busy ? "Calculating…" : agent === "A2" ? "View receivables aging" : "View budget variance"}
    </button>
    {error && <p role="alert" className="mt-2 text-xs text-red-800">{error}</p>}
    {data && <div className="mt-3 border border-line bg-zinc-50 p-4">
      <h5 className="text-sm font-semibold">{agent === "A2" ? "Outstanding receivables by age" : "Largest budget variances"}</h5>
      <div className="mt-4 space-y-3">{rows.map(row => <div key={row.name}>
        <div className="mb-1 flex justify-between gap-3 text-xs"><span>{row.name}</span><span className="tabular-nums">{money(row.amount)}</span></div>
        <div className="h-2 bg-zinc-200"><div className={`h-full ${row.amount < 0 ? "bg-zinc-400" : "bg-ink"}`} style={{ width: `${Math.abs(row.amount) / max * 100}%` }} /></div>
      </div>)}</div>
      {!rows.length && <p className="mt-3 text-sm">No nonzero differences in the supplied comparison.</p>}
      {(data.data.explained || []).map(row => <details key={row.account} className="mt-3 border-t border-line pt-2">
        <summary className="cursor-pointer text-xs">{row.name} · supporting transactions</summary>
        <p className="mt-2 text-xs">Actual: {money(row.actual_cents)} · Budget: {row.planned_cents === null ? "Not supplied" : money(row.planned_cents)}</p>
        {row.drivers.map((driver, i) => <p key={i} className="mt-2 break-all text-xs">{driver.event_ref || "Grouped / unattributed"} · {money(driver.amount_cents)}<br/>{driver.evidence.map(e => `${e.source_id}, line ${e.line}`).join("; ")}</p>)}
      </details>)}
      <p className="mt-3 break-all text-[11px] text-ink-dim">Current supplied-record calculation · Snapshot {data.snapshot_id}. Refresh after changing records. Not a model conclusion.</p>
    </div>}
  </div>;
}
