"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { intakeApi } from "@/lib/data";

type Changes = { snapshot_id: string | null; previous_snapshot_id: string | null; revision: number; total_records: number; rules_scan_current: boolean;
  added_or_revised: { id: string; role: string; record_key: string; version: number }[]; superseded: { id: string }[];
  recent_reviews: { snapshot_id: string; run_id: string | null }[] };

export function FileUpdates({ ws, revision }: { ws: string; revision?: string | null }) {
  const [changes, setChanges] = useState<Changes | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [live, setLive] = useState(false);
  const [busy, setBusy] = useState(false);
  const base = `/api/workspaces/${ws}/updates`;
  useEffect(() => { let current = true; intakeApi<Changes>(base).then(v => { if (current) { setChanges(v); setError(""); } }).catch(e => { if (current) setError(String(e)); }); return () => { current = false; }; }, [base, revision]);
  async function scan() {
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await intakeApi<{ run_id: string | null; reused?: boolean }>(base + "/scan", { method: "POST", body: JSON.stringify({ snapshot_id: changes!.snapshot_id, live }) });
      setChanges(await intakeApi<Changes>(base));
      setMessage(result.run_id ? `${result.reused ? "Existing" : "New"} five-agent investigation: ${result.run_id}. Open Agent review to follow progress.` : "Rules-based scan updated. Open Findings to review changes.");
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  return <section className="my-4 border border-teal-200 bg-teal-50/50 p-4"><h3 className="text-lg font-semibold">Keep this institution up to date</h3><p className="my-2 text-sm">Add more files below anytime—no new institution needed. For corrected records, keep the same source system and record IDs, and increase the source version. Commit each validated update, then scan the new snapshot.</p>
    <div className="flex flex-wrap gap-4 text-sm"><a className="underline" href="#add-records">Add CSV / text updates</a><Link className="underline" href="/documents">Upload PDFs / images & review extraction</Link><Link className="underline" href="/findings">Findings</Link><Link className="underline" href="/cfo">Agent review</Link></div>
    {changes && <><p className="my-3 text-sm">Revision {changes.revision} · {changes.total_records} active records · {changes.added_or_revised.length} added/revised · {changes.superseded.length} superseded since previous snapshot. {changes.rules_scan_current ? "Rules scan is current." : "New snapshot needs a scan."}</p>
      <details><summary className="text-sm">What changed?</summary><ul className="my-2 list-disc pl-5 text-xs">{changes.added_or_revised.map(r => <li key={r.id}>{r.role}: {r.record_key} · version {r.version}</li>)}</ul></details>
      <label className="my-3 flex items-start gap-2 text-sm"><input type="checkbox" checked={live} onChange={e => setLive(e.target.checked)} />Also run all five live agents. This sends selected records/excerpts to the configured hosted model and can incur API charges.</label>
      <button disabled={busy || !changes.snapshot_id} onClick={scan} className="bg-ink px-4 py-2 text-sm text-white disabled:opacity-40">{busy ? "Starting review…" : live ? "Scan updates + start five-agent review" : "Scan updates (rules only)"}</button></>}
    {error && <p role="alert" className="mt-2 text-red-800">{error}</p>}{message && <p role="status" className="mt-2 text-sm">{message}</p>}
  </section>;
}
