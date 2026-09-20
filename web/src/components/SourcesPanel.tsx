"use client";

import { displayLabel } from "@/lib/format";
import { detectSource } from "@/lib/source-detection";

import { useCallback, useEffect, useRef, useState } from "react";

import type { IntakeUiProgress } from "@/lib/workflow";
import { API_URL, intakeApi, useData } from "@/lib/data";
import type { Coverage, ImportBatch, IntakeWorkspace, SourceDetail, SourceOptions, SourceRole } from "@/lib/types";

// Keyed by string rather than SourceRole: the server owns the role list, and the
// money-in roles are offered here as soon as it accepts them.
const ROLES: Record<string, string> = {
  chart: "Chart of accounts", opening: "Opening trial balance", ledger: "General ledger",
  payroll: "Payroll", grants: "Grant register", budget: "Budget", invoice: "Invoices",
  fees: "Student fees", collections: "Collections (money received)", deposits: "Bank deposits",
  sponsorships: "Sponsorships & pledges",
  policy: "Award terms / policy", service: "Service evidence", document: "Other document",
};
const input = "w-full border border-line bg-white px-2.5 py-2 text-xs";
const button = "border border-line px-3 py-2 text-xs font-semibold hover:bg-surface-2 disabled:opacity-40";
const primary = "bg-ink px-3 py-2 text-xs font-semibold text-white hover:bg-ink-dim disabled:opacity-40";
// Keep essential form geometry on the controls, not dependent on native input
// styling or the order in which global development CSS chunks arrive.
const fieldLayout: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 6, minWidth: 0 };
const fieldControl: React.CSSProperties = { boxSizing: "border-box", width: "100%", minWidth: 0, height: 34, padding: "6px 10px", border: "1px solid #d4d4d8", background: "white", lineHeight: "20px", outlineOffset: -2 };
const defaults = (role: SourceRole = "document"): SourceOptions => ({
  role, source_system: "manual", source_version: 1, external_id: "", applies_to: "",
  mapping: {}, amount_unit: "major", excluded: false, exclusion_reason: "",
});
function Modal({ title, close, children }: { title: string; close: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} onCancel={close} className="m-auto max-h-[85vh] w-[min(920px,95vw)] overflow-auto border border-line bg-white p-5 shadow-xl backdrop:bg-ink/30">
    <div className="mb-4 flex items-center justify-between gap-4"><h2 className="text-base font-semibold">{title}</h2>
      <button type="button" className={button} onClick={close}>Close</button></div>{children}
  </dialog>;
}

/**
 * `onProgressChange` lets the step guide above this panel read where the import
 * actually is. It is reported, never inferred: the guide can only ever say what
 * this panel has already seen.
 */
export function SourcesPanel({ onProgressChange }: { onProgressChange?: (progress: IntakeUiProgress) => void }) {
  const { ws, bundle, setWs, refreshWorkspaces, refreshBundle, apiError } = useData();
  const isIntake = Boolean(ws && bundle.workspace.intake);
  const [creating, setCreating] = useState(false);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [history, setHistory] = useState<{ id: string; status: string; created_at: string }[]>([]);
  const [files, setFiles] = useState<{ file: File; options: SourceOptions; note: string }[]>([]);
  const [detecting, setDetecting] = useState(false);
  const selection = useRef(0);
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [draft, setDraft] = useState<Record<string, SourceOptions>>({});
  const [source, setSource] = useState<SourceDetail | null>(null);
  const snapshot = coverage?.workspace.id === ws ? coverage.snapshot : null;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const base = `/api/workspaces/${encodeURIComponent(ws)}`;
  const refresh = useCallback(async () => {
    const [cov, imports] = await Promise.all([
      intakeApi<Coverage>(base + "/coverage"),
      intakeApi<typeof history>(base + "/imports"),
    ]);
    setCoverage(cov); setHistory(imports);
  }, [base]);
  useEffect(() => {
    // Without a workspace the base URL is /api/workspaces/, which 404s. Nothing
    // here is meaningful until someone has created a school.
    if (!isIntake || !ws) return;
    let mounted = true;
    const load = () => Promise.all([intakeApi<Coverage>(base + "/coverage"), intakeApi<typeof history>(base + "/imports")])
      .then(([c, h]) => { if (mounted) { setCoverage(c); setHistory(h); } })
      .catch(() => { /* The shared API status shows outages; retry without discarding the last snapshot. */ });
    void load();
    const interval = setInterval(load, 10000);
    return () => { mounted = false; clearInterval(interval); };
  }, [base, isIntake, ws]);

  // The step guide and the sidebar both ask for the creator by name rather than
  // reaching into this component's state.
  useEffect(() => {
    const openCreator = () => setCreating(true);
    const openFromHash = () => { if (window.location.hash === "#new-institution") openCreator(); };
    openFromHash();
    window.addEventListener("schooltrace:new-institution", openCreator);
    window.addEventListener("hashchange", openFromHash);
    return () => {
      window.removeEventListener("schooltrace:new-institution", openCreator);
      window.removeEventListener("hashchange", openFromHash);
    };
  }, []);

  useEffect(() => {
    if (!onProgressChange) return;
    onProgressChange({
      loaded: coverage !== null,
      selectedFileCount: files.length,
      batchStatus: batch?.status ?? null,
      batchIssues: batch?.counts.issues ?? 0,
      hasSnapshot: Boolean(snapshot),
      runRunning: false,
    });
  }, [batch?.counts.issues, batch?.status, coverage, files.length, onProgressChange, snapshot]);

  async function act(fn: () => Promise<void>) {
    setBusy(true); setError(""); setMessage("");
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "Request failed"); }
    finally { setBusy(false); }
  }
  function showBatch(b: ImportBatch) { setBatch(b); setDraft(Object.fromEntries(b.files.map((f) => [f.id, f.options]))); }
  function edit(id: string, updates: Partial<SourceOptions>) {
    setDraft((d) => ({ ...d, [id]: { ...d[id], ...updates } }));
  }
  async function viewSource(id: string, line = 1) {
    setSource(await intakeApi<SourceDetail>(`${base}/sources/${id}?start=${line}`));
  }
  const draftChanged = batch && batch.files.some((f) => JSON.stringify(f.options) !== JSON.stringify(draft[f.id]));

  return <section className="min-w-0 border border-line bg-white p-5" aria-label="Upload records">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h2 className="text-base font-semibold">Sources & coverage</h2>
        <p className="mt-1 text-xs text-ink-dim">Upload records and check their coverage.</p></div>
      <button className={button} onClick={() => setCreating(true)}>New institution</button>
    </div>
    {(error || apiError) && (() => {
      const text = error || apiError || "";
      // Only a reachability failure should send someone to check the server.
      // Appending it to every error sent people hunting a live API over a 404.
      const unreachable = /not reachable|timed out/i.test(text);
      return <p role="alert" className="mt-3 bg-red-50 p-3 text-accent-bad">
        {text}{unreachable ? ` Check that the API is running on ${API_URL}.` : ""}
      </p>;
    })()}
    {message && <p role="status" className="mt-3 bg-surface-2 p-3 text-ink">{message}</p>}
    {!isIntake && <p className="mt-5 text-sm text-ink-dim">Create an institution to upload its records.</p>}

    {isIntake && <>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-ink-dim">
        <span>{coverage?.workspace.scope || (ws ? "Loading scope…" : "No school yet — create one to add records.")}</span>
        {coverage && <span>· {coverage.workspace.currency}</span>}
        <button disabled={busy} className={button} onClick={() => act(async () => {
          await refresh();
          if (batch && batch.status !== "committed") {
            setMessage("Sources refreshed. Finish or review the current import before detecting saved files.");
            return;
          }
          const result = await intakeApi<{ batch: ImportBatch | null; detected: number }>(base + "/sources/detect", { method: "POST" });
          if (result.batch) {
            showBatch(result.batch);
            setMessage(`Detected types for ${result.detected} saved files. Review the import below and confirm to update coverage.`);
          } else setMessage("Sources refreshed. No additional structured file types detected. Missing items need supporting records.");
        })}>Refresh sources</button>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {coverage?.capabilities.map((c) => <div key={c.id} className="border border-line p-3">
          <div className="font-semibold">{c.label}</div>
          <span className={`mt-1 inline-block px-1.5 py-0.5 text-[10px] ${c.status === "ready_for_scope" ? "bg-surface-2 text-ink" : "bg-amber-50 text-amber-800"}`}>{displayLabel(c.status)}</span>
          {c.missing.length > 0 && <p className="mt-1 text-xs">Missing: {c.missing.map((r) => ROLES[r as SourceRole] || r).join(", ")}</p>}
          <p className="mt-1 text-[11px] text-ink-dim">{c.note}</p>
          {c.runnable && <button className={`${button} mt-3`} disabled={busy} onClick={() => act(async () => {
            await intakeApi(base + "/review/scans", { method: "POST" });
            await refresh();
            await refreshBundle();
            setMessage("Record checks completed. Expand results below. No model calls were made.");
          })}>{busy ? "Working…" : c.results?.length ? "Run checks again" : "Run checks"}</button>}
          {!!c.results?.length && <details className="mt-3 text-xs"><summary className="cursor-pointer font-semibold">View results ({c.results.length})</summary>
            <div className="mt-2 space-y-3">{c.results.map((r) => <div key={r.id} className="border-t border-line pt-2">
              <p className="font-semibold">{r.title} · {displayLabel(r.status)}</p>
              {r.amount_cents !== null && <p className="mt-1 tabular-nums">{new Intl.NumberFormat("en-US", { style: "currency", currency: coverage.workspace.currency }).format(r.amount_cents / 100)}</p>}
              <p className="mt-1 text-ink-dim">{r.explanation}</p><p className="mt-1">{r.action}</p>
              <div className="mt-1 flex flex-wrap gap-2">{r.evidence.map((e) => <button key={`${e.source_id}:${e.line}`} className="underline" onClick={() => act(() => viewSource(e.source_id, e.line))}>{coverage.sources.find((s) => s.id === e.source_id)?.name || "Source"} · line {e.line}</button>)}</div>
            </div>)}</div>
          </details>}
        </div>)}
      </div>
      <p className="mt-2 text-[11px] text-ink-dim">{coverage?.note}</p>



      <div id="source-records" className="mt-5 scroll-mt-4 border-t border-line pt-4">
        <h3 className="font-semibold">1. Add records</h3>
        <p className="my-2 text-xs text-ink-dim">CSV, TXT or Markdown · 20 files per import · 10 MB each / 50 MB total. Use ISO dates and exact amounts. Upload only records you are authorized to process.</p>
        {/* macOS file-type associations can incorrectly disable CSVs when an
            accept filter is present. Validate names here; the API independently
            validates extensions, UTF-8 content, sizes and record schemas. */}
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button type="button" className={primary} style={{ background: "#09090b", color: "white", border: "1px solid #09090b", padding: "10px 16px" }} disabled={busy || detecting || !coverage} onClick={() => fileInput.current?.click()}>Choose files</button>
          <span className="text-xs text-ink-dim" aria-live="polite">{files.length ? `${files.length} file${files.length === 1 ? "" : "s"} selected` : "No files selected"}</span>
        </div>
        <input style={{ display: "none" }} ref={fileInput} aria-label="Choose CSV, TXT or Markdown files" type="file" multiple disabled={busy || detecting || !coverage}
          onChange={async (e) => {
            const selected = Array.from(e.target.files || []);
            const unsupported = selected.filter((file) => !/\.(csv|txt|md)$/i.test(file.name));
            if (unsupported.length) {
              setError(`Choose CSV, TXT or Markdown files. Unsupported: ${unsupported.map((file) => file.name).join(", ")}`);
              e.target.value = "";
              return;
            }
            if (selected.length > 20 || selected.some(f => f.size > 10 * 1024 * 1024) || selected.reduce((sum, f) => sum + f.size, 0) > 50 * 1024 * 1024) {
              setError("Upload exceeds file or batch limits"); e.target.value = ""; return;
            }
            setError("");
            setDetecting(true);
            const id = ++selection.current;
            try {
              const detected = await Promise.all(selected.map(async file => {
                const result = detectSource(file.name, await file.slice(0, 65536).text(), coverage?.workspace.kind === "public");
                return { file, options: { ...defaults(result.role), mapping: result.mapping }, note: result.note };
              }));
              if (selection.current === id) setFiles(detected);
            } catch { setError("Could not read the selected files. Please select them again."); }
            finally { if (selection.current === id) setDetecting(false); }
          }} />
        {detecting && <p role="status" className="mt-2 text-xs">Detecting file types…</p>}
        {files.map((f, i) => <div key={i} className="mt-3 grid items-end gap-3 border border-line p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,180px)_80px]">
          <span className="min-w-0 self-center break-words text-xs">{f.file.name} · {(f.file.size / 1024).toFixed(1)} KB<small className="mt-1 block text-ink-dim">{f.note}</small></span>
          <select aria-label={`Role for ${f.file.name}`} className={input} value={f.options.role} onChange={(e) => setFiles((all) => all.map((x, n) => n === i ? { ...x, note: "Manually selected", options: { ...x.options, mapping: {}, role: e.target.value as SourceRole } } : x))}>
            {Object.entries(ROLES).map(([r, label]) => <option key={r} value={r}>{label}</option>)}
          </select>
          <label className="text-[10px]">Version<input aria-label={`Version for ${f.file.name}`} className={input} type="number" min={1} value={f.options.source_version} onChange={(e) => setFiles((all) => all.map((x, n) => n === i ? { ...x, options: { ...x.options, source_version: Number(e.target.value) } } : x))} /></label>
        </div>)}
        <button disabled={busy || detecting || !files.length} className={primary + " mt-3"} onClick={() => act(async () => {
          if (files.length > 20 || files.some((f) => f.file.size > 10 * 1024 * 1024) || files.reduce((n, f) => n + f.file.size, 0) > 50 * 1024 * 1024) throw new Error("Upload exceeds file or batch limits");
          const form = new FormData();
          files.forEach((f) => form.append("files", f.file));
          form.append("metadata", JSON.stringify(files.map((f) => f.options)));
          showBatch(await intakeApi<ImportBatch>(base + "/imports", { method: "POST", body: form }));
          await refresh();
        })}>{busy ? "Working…" : "Preview import"}</button>
      </div>

      {history.length > 0 && <label className="mt-4 block text-xs">Resume an import
        <select className={input + " mt-1"} value={batch?.id || ""} disabled={busy} onChange={(e) => { const id = e.target.value; if (id) act(async () => showBatch(await intakeApi<ImportBatch>(base + "/imports/" + id))); }}>
          <option value="">Choose saved import…</option>
          {history.map((h) => <option key={h.id} value={h.id}>{h.created_at.slice(0, 19)} · {displayLabel(h.status)} · {h.id.slice(-6)}</option>)}
        </select>
      </label>}

      {batch && <div id="source-import" className="mt-4 scroll-mt-4 border border-line p-3">
        <h3 className="font-semibold">2. Review import · {displayLabel(batch.status)}</h3>
        <p className="my-2 text-xs">{batch.counts.parsed} source rows/lines · {batch.counts.valid_records} valid records · {batch.counts.new_records} new · {batch.counts.duplicate_records} duplicates · {batch.counts.issues} issues</p>
        <p className="text-xs">Validated debit total: {(batch.totals.debit_cents / 100).toFixed(2)} · credit: {(batch.totals.credit_cents / 100).toFixed(2)} {coverage?.workspace.currency}</p>
        <p className="mt-1 text-[11px] text-ink-dim">Totals combine opening and activity files for import control only; they are not a financial statement. {batch.coverage_note}</p>
        {batch.files.map((f) => <details key={f.id} className="mt-3 bg-surface-2 p-3">
          <summary className="cursor-pointer font-semibold">{f.name} · {f.row_count} rows/lines {f.duplicate_of ? "· identical bytes already uploaded" : ""}</summary>
          <button className={button + " mt-2"} onClick={() => act(() => viewSource(f.id))}>View original</button>
          {batch.status !== "committed" && draft[f.id] && <>
            <div className="my-2 grid gap-2 sm:grid-cols-3">
              <label className="text-xs">Record type<select className={input} value={draft[f.id].role} onChange={(e) => edit(f.id, { role: e.target.value as SourceRole, mapping: {} })}>{Object.entries(ROLES).map(([role, label]) => <option key={role} value={role}>{label}</option>)}</select></label>
              <label className="text-xs">Source system<input className={input} value={draft[f.id].source_system} onChange={(e) => edit(f.id, { source_system: e.target.value })} /></label>
              <label className="text-xs">Source version<input className={input} type="number" min={1} value={draft[f.id].source_version} onChange={(e) => edit(f.id, { source_version: Number(e.target.value) })} /></label>
              <label className="text-xs">Amount units<select className={input} value={draft[f.id].amount_unit} onChange={(e) => edit(f.id, { amount_unit: e.target.value as "major" | "minor" })}><option value="major">Dollars (100.00)</option><option value="minor">Cents (10000)</option></select></label>
              <label className="text-xs">Document ID (for revisions)<input className={input} value={draft[f.id].external_id} onChange={(e) => edit(f.id, { external_id: e.target.value })} placeholder="Stable document identifier" /></label>
              <label className="text-xs">Applies to<input className={input} value={draft[f.id].applies_to} onChange={(e) => edit(f.id, { applies_to: e.target.value })} placeholder="Record or award ID" /></label>
              <label className="text-xs">Expected CSV rows<input className={input} type="number" min={0} value={draft[f.id].expected_rows ?? ""} onChange={(e) => edit(f.id, { expected_rows: e.target.value === "" ? null : Number(e.target.value) })} /></label>
              {(["debit", "credit"] as const).map((side) => <label key={side} className="text-xs">Expected {side} total<input className={input} value={draft[f.id][`expected_${side}`] ?? ""} onChange={(e) => edit(f.id, { [`expected_${side}`]: e.target.value || null })} /></label>)}
            </div>
            <div className="grid gap-2 sm:grid-cols-3">{f.required_fields.map((field) => <label key={field} className="text-xs">{field}
              <select className={input} value={draft[f.id].mapping[field] ?? (f.headers.includes(field) ? field : "")} onChange={(e) => edit(f.id, { mapping: { ...draft[f.id].mapping, [field]: e.target.value } })}>
                <option value="">Select CSV column…</option>{f.headers.map((h) => <option key={h}>{h}</option>)}
              </select></label>)}</div>
            <label className="mt-3 flex items-center gap-2 text-xs"><input type="checkbox" checked={draft[f.id].excluded} onChange={(e) => edit(f.id, { excluded: e.target.checked })} />Exclude this file from the import</label>
            {draft[f.id].excluded && <input aria-label="Exclusion reason" className={input + " mt-1"} placeholder="Reason required" value={draft[f.id].exclusion_reason} onChange={(e) => edit(f.id, { exclusion_reason: e.target.value })} />}
          </>}
          {f.preview.length > 0 && <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-[11px]">
            <thead><tr><th className="p-1">Source line</th><th className="p-1">Normalized record (amounts in cents)</th></tr></thead>
            <tbody>{f.preview.map((row, i) => <tr key={i}><td className="p-1 align-top"><button className="text-ink underline" onClick={() => act(() => viewSource(f.id, row.locator))}>{row.locator}</button></td><td className="p-1"><pre className="max-w-[650px] whitespace-pre-wrap break-all">{JSON.stringify(row.payload, null, 2)}</pre></td></tr>)}</tbody>
          </table></div>}
        </details>)}
        {batch.issues.length > 0 && <ul className="mt-3 space-y-1" aria-label="Validation issues">{batch.issues.map((i, n) => <li key={n} className="bg-red-50 p-2 text-xs text-accent-bad">
          <b>{i.code}</b>: {i.message} {i.field && `(${i.field})`}
          {i.source_id !== "batch" && <button className="ml-2 underline" onClick={() => act(() => viewSource(i.source_id, i.locator || 1))}>Open source {i.locator ? `line ${i.locator}` : ""}</button>}
        </li>)}</ul>}
        {batch.issues_truncated && <p className="text-xs">Showing the first 500 issues; resolve these and revalidate.</p>}
        {batch.changes.length > 0 && <details className="my-2"><summary className="font-semibold">Review {batch.changes.length} superseding record changes</summary><pre className="overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(batch.changes, null, 2)}</pre></details>}
        {batch.status !== "committed" ? <div className="mt-3 flex flex-wrap gap-2">
          <button disabled={busy} className={button} onClick={() => act(async () => showBatch(await intakeApi<ImportBatch>(base + "/imports/" + batch.id + "/mapping", {
            method: "PATCH", body: { expected_version: batch.version, files: draft },
          }))) }>Save mappings & revalidate</button>
          <button disabled={busy || batch.status !== "ready_to_commit" || Boolean(draftChanged)} className={primary} onClick={() => act(async () => {
            showBatch(await intakeApi<ImportBatch>(base + "/imports/" + batch.id + "/commit", {
              method: "POST", body: { expected_version: batch.version, idempotency_key: batch.id + ":" + batch.version },
            }));
            setFiles([]); if (fileInput.current) fileInput.current.value = "";
            await Promise.all([refresh(), refreshBundle()]);
            setMessage("Records committed. Originals and the snapshot are saved locally. No financial correction or agent investigation was performed.");
          })}>Confirm & commit records</button>
          <span className="self-center text-[11px] text-ink-dim">Local reviewer · commits validated records, not accounting adjustments</span>
        </div> : <p className="mt-3 font-mono text-xs text-ink">Saved snapshot: {batch.snapshot_id}</p>}
      </div>}

      <div className="mt-6 border-t border-line pt-5">
        <div><h3 className="font-semibold">Committed sources</h3>
          {!coverage?.sources.length && <p className="mt-2 text-xs text-ink-dim">No committed sources yet.</p>}
          {coverage?.sources.map((s) => <button key={s.id} className="mt-2 flex w-full justify-between gap-2 border border-line p-2 text-left text-xs hover:bg-surface-2" onClick={() => act(() => viewSource(s.id))}>
            <span>{s.name}<small className="block text-ink-faint">{ROLES[s.role]}</small></span><span>{s.active ? "Active" : "Historical / duplicate"} ↗</span>
          </button>)}
        </div>
      </div>
    </>}

    {creating && <Modal title="Create an institution workspace" close={() => !busy && setCreating(false)}>
      <form className="institution-form grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); const d = Object.fromEntries(new FormData(e.currentTarget));
        act(async () => { const w = await intakeApi<IntakeWorkspace>("/api/workspaces", { method: "POST", body: d });
          await refreshWorkspaces(); setCreating(false); setWs(w.id); }); }}>
        <label style={fieldLayout} className="text-xs">Institution name<input style={fieldControl} name="name" required maxLength={120} placeholder="Institution name" className={input} /></label>
        <label style={fieldLayout} className="text-xs">Institution type<select style={fieldControl} name="entity_type" className={input}>{["school", "district", "board", "university"].map((v) => <option key={v} value={v}>{displayLabel(v)}</option>)}</select></label>
        <label style={fieldLayout} className="text-xs">Data origin<select style={fieldControl} name="kind" className={input}><option value="synthetic">Synthetic records</option><option value="public">Public documents only</option></select></label>
        <label style={fieldLayout} className="text-xs">Currency<select style={fieldControl} name="currency" className={input}>{["USD", "CAD", "EUR", "GBP"].map((v) => <option key={v} value={v}>{displayLabel(v)}</option>)}</select></label>
        <label style={fieldLayout} className="text-xs">Period start<input style={fieldControl} type="date" name="start" required defaultValue="2026-09-01" className={input} /></label>
        <label style={fieldLayout} className="text-xs">Period end<input style={fieldControl} type="date" name="end" required defaultValue="2026-09-30" className={input} /></label>
        <label style={fieldLayout} className="text-xs">Jurisdiction<input style={fieldControl} name="jurisdiction" required placeholder="Province, state or region" className={input} /></label>
        <label style={fieldLayout} className="text-xs">Scope<input style={fieldControl} name="scope" required placeholder="e.g. September payroll and grant allocation" className={input} /></label>
        <p className="text-xs text-ink-dim sm:col-span-2">The current accounting checks use the USD management profile. Other currencies are available for public-document exploration.</p>
        {error && <p role="alert" className="text-red-700 sm:col-span-2">{error}</p>}
        <button disabled={busy} className={primary}>{busy ? "Creating…" : "Create workspace"}</button>
      </form>
    </Modal>}
    {source && <Modal title={source.name} close={() => setSource(null)}>
      <p className="break-all font-mono text-[10px] text-ink-faint">SHA-256 {source.sha256}</p>
      <p className="my-2 text-xs">{source.extraction_origin ? "Reviewed extraction — derived from the document below" : source.committed ? "Committed original" : "Staged original — not authoritative"} · {source.line_count} lines · version {source.options.source_version}</p>
      <a className="text-xs text-ink underline" href={API_URL + base + "/sources/" + source.id + "/download"}>{source.extraction_origin ? "Download the reviewed extraction" : "Download unchanged original"}</a>
      {source.extraction_origin && <div className="my-2 text-xs">
        <p>Reviewed extraction. The original document is preserved.</p>
        <a className="text-ink underline" href={`${API_URL}${base}/extraction/documents/${source.extraction_origin.document_id}/original`}>Download the original: {source.extraction_origin.name}</a>
        {source.extraction_origin.has_images && source.extraction_origin.pages.map((page) => <a key={page} target="_blank" rel="noreferrer" className="ml-3 text-ink underline" href={`${API_URL}${base}/extraction/documents/${source.extraction_origin!.document_id}/pages/${page}`}>Original page {page}</a>)}
      </div>}
      <div className="my-3 max-h-[50vh] overflow-auto border border-line bg-surface-2 p-3">
        {source.lines.map((l) => <div key={l.number} className="flex gap-3 font-mono text-xs"><span className="w-10 flex-none select-none text-right text-ink-faint">{l.number}</span><pre className="whitespace-pre-wrap break-all">{l.text || " "}</pre></div>)}
      </div>
      <div className="flex gap-2">
        <button className={button} disabled={busy || (source.lines[0]?.number || 1) <= 1} onClick={() => act(() => viewSource(source.id, Math.max(1, source.lines[0].number - 100)))}>Previous lines</button>
        <button className={button} disabled={busy || (source.lines.at(-1)?.number || 0) >= source.line_count} onClick={() => act(() => viewSource(source.id, (source.lines.at(-1)?.number || 0) + 1))}>Next lines</button>
      </div>
    </Modal>}
  </section>;
}
