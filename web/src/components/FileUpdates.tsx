"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { intakeApi } from "@/lib/data";

type Changes = {
  snapshot_id: string | null;
  previous_snapshot_id: string | null;
  revision: number;
  total_records: number;
  rules_scan_current: boolean;
  added_or_revised: { id: string; role: string; record_key: string; version: number }[];
  superseded: { id: string }[];
  recent_reviews: { snapshot_id: string; run_id: string | null }[];
};

/**
 * What has changed since the last committed snapshot, and the way to re-check it.
 *
 * Records keep arriving after the first commit. Without this, the only signal
 * that a scan is out of date is the date on it.
 */
export function FileUpdates({ ws, revision }: { ws: string; revision?: string | null }) {
  const [changes, setChanges] = useState<Changes | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [live, setLive] = useState(false);
  const [busy, setBusy] = useState(false);
  const base = `/api/workspaces/${ws}/updates`;

  useEffect(() => {
    // Without a workspace the base URL is /api/workspaces//updates, which 404s.
    if (!ws) return;
    let current = true;
    intakeApi<Changes>(base)
      .then((v) => { if (current) { setChanges(v); setError(""); } })
      .catch((e) => { if (current) setError(e instanceof Error ? e.message : String(e)); });
    return () => { current = false; };
  }, [ws, base, revision]);

  async function scan() {
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await intakeApi<{ run_id: string | null; reused?: boolean }>(base + "/scan", {
        method: "POST",
        body: { snapshot_id: changes!.snapshot_id, live },
      });
      setChanges(await intakeApi<Changes>(base));
      setMessage(result.run_id
        ? `${result.reused ? "Existing" : "New"} five-agent investigation: ${result.run_id}. Open Investigation to follow it.`
        : "Record checks complete. Open Briefing for results.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!changes) {
    return error ? <p role="alert" className="my-4 border border-line bg-surface-2 p-4 text-[13px] text-accent-bad">{error}</p> : null;
  }

  return (
    <section className="my-4 border border-line bg-surface-2 p-4">
      <h3 className="text-[15px] font-semibold tracking-tight">File updates</h3>
      <p className="my-2 max-w-prose text-[13px] leading-relaxed text-ink-dim">
        Upload new files to this workspace. For corrections, keep the record ID and source system,
        increase the version, then commit and rescan.
      </p>
      <div className="flex flex-wrap gap-4 text-[13px]">
        <a className="underline" href="#source-records">Add CSV or text records</a>
        <a className="underline" href="#source-documents">Add a PDF or photo</a>
        <Link className="underline" href="/investigation">Investigation</Link>
      </div>

      <p className="my-3 text-[13px]">
        Revision {changes.revision} · {changes.total_records} active records · {changes.added_or_revised.length} added or
        revised · {changes.superseded.length} superseded since the previous commit.{" "}
        {changes.rules_scan_current ? "The last check covers these records." : "These records have not been checked yet."}
      </p>
      {changes.added_or_revised.length > 0 && (
        <details>
          <summary className="cursor-pointer text-[13px]">What changed?</summary>
          <ul className="my-2 list-disc pl-5 text-[12px]">
            {changes.added_or_revised.map((r) => <li key={r.id}>{r.role}: {r.record_key} · version {r.version}</li>)}
          </ul>
        </details>
      )}
      <label className="my-3 flex items-start gap-2 text-[13px]">
        <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
        Include an agent review. Selected records go to the model provider; API charges apply.
      </label>
      <button
        disabled={busy || !changes.snapshot_id}
        onClick={() => void scan()}
        className="bg-ink px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-40"
      >
        {busy ? "Starting…" : live ? "Scan and investigate" : "Run record checks"}
      </button>
      {error && <p role="alert" className="mt-2 text-[13px] text-accent-bad">{error}</p>}
      {message && <p role="status" className="mt-2 text-[13px]">{message}</p>}
    </section>
  );
}
