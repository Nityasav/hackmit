"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { API_URL, intakeApi, useData } from "@/lib/data";
import type { AgentRun, Coverage, ImportBatch, IntakeWorkspace, SourceDetail, SourceOptions, SourceRole } from "@/lib/types";
import type { IntakeUiProgress } from "@/lib/workflow";
import { FileUpdates } from "@/components/FileUpdates";
import sample from "@/fixtures/intake.json";

const ROLES: Record<SourceRole, string> = {
  chart: "Chart of accounts", opening: "Opening trial balance", ledger: "General ledger",
  payroll: "Payroll", grants: "Grant register", budget: "Budget", invoice: "Invoices",
  policy: "Award terms / policy", service: "Service evidence", document: "Other document",
};
const AGENTS = {
  cfo: { label: "CFO Agent", action: "Run CFO triage", focus: "Perform an initial risk triage of the committed snapshot." },
  grants_compliance: { label: "Grants & Compliance agent", action: "Run Grants & Compliance", focus: "Review supplied grant terms, award periods, payroll charges and supporting evidence. Identify bounded risks and missing evidence." },
  internal_auditor: { label: "Internal Auditor agent", action: "Run Internal Auditor", focus: "Independently review the latest preparer findings against original source lines and reperform supporting calculations. Prioritize unsupported conclusions and allocation risks." },
  // The five-agent workflow is a coordinator run, not a single-agent triage, so it
  // starts through a different endpoint. It belongs in the same control regardless:
  // from here it is one more choice of who investigates.
  five_agent: { label: "Five-agent workflow (CFO → AP + Payroll + Grants → Auditor)", action: "Start five-agent workflow", focus: "Review the current close, identify evidence gaps, and prepare a CFO briefing." },
};
type AgentChoice = keyof typeof AGENTS;
const input = "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-xs";
const button = "rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold hover:bg-slate-50 disabled:opacity-40";
const primary = "rounded-lg bg-teal-700 px-3 py-2 text-xs font-semibold text-white hover:bg-teal-800 disabled:opacity-40";
const defaults = (role: SourceRole = "document"): SourceOptions => ({
  role, source_system: "manual", source_version: 1, external_id: "", applies_to: "",
  mapping: {}, amount_unit: "major", excluded: false, exclusion_reason: "",
});
function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function Modal({ title, close, children }: { title: string; close: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} onCancel={close} className="m-auto max-h-[85vh] w-[min(920px,95vw)] overflow-auto rounded-xl border border-slate-200 bg-white p-5 shadow-xl backdrop:bg-slate-900/30">
    <div className="mb-4 flex items-center justify-between gap-4"><h2 className="text-base font-semibold">{title}</h2>
      <button type="button" className={button} onClick={close}>Close</button></div>{children}
  </dialog>;
}

export function SourcesPanel({ onProgressChange }: { onProgressChange?: (progress: IntakeUiProgress) => void }) {
  const { ws, bundle, setWs, refreshWorkspaces, refreshBundle, apiError } = useData();
  const isIntake = Boolean(bundle.workspace.intake);
  const [creating, setCreating] = useState(false);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [history, setHistory] = useState<{ id: string; status: string; created_at: string }[]>([]);
  const [files, setFiles] = useState<{ file: File; options: SourceOptions }[]>([]);
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [draft, setDraft] = useState<Record<string, SourceOptions>>({});
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [allAgentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<AgentChoice>("cfo");
  const [startedRun, setStartedRun] = useState<string | null>(null);
  const coordinator = selectedAgent === "five_agent";
  const agentRuns = coordinator ? [] : allAgentRuns.filter((run) => run.workspace_id === ws && run.agent === selectedAgent);
  const agentRunning = allAgentRuns.some((run) => run.workspace_id === ws && run.status === "running");
  const completedRunCount = allAgentRuns.filter((run) => run.workspace_id === ws && run.status === "completed" && run.result.analysis).length;
  const snapshot = coverage?.workspace.id === ws ? coverage.snapshot : null;
  const [agentFocus, setAgentFocus] = useState("Perform an initial risk triage of the committed snapshot.");
  const [agentBusy, setAgentBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const base = `/api/workspaces/${encodeURIComponent(ws)}`;
  const refresh = useCallback(async () => {
    const [cov, imports, runs] = await Promise.all([
      intakeApi<Coverage>(base + "/coverage"),
      intakeApi<typeof history>(base + "/imports"),
      intakeApi<AgentRun[]>(base + "/agent-runs"),
    ]);
    setCoverage(cov); setHistory(imports); setAgentRuns(runs);
  }, [base]);
  useEffect(() => {
    if (!isIntake) return;
    let mounted = true;
    const load = () => Promise.all([intakeApi<Coverage>(base + "/coverage"), intakeApi<typeof history>(base + "/imports"), intakeApi<AgentRun[]>(base + "/agent-runs")])
      .then(([c, h, r]) => { if (mounted) { setCoverage(c); setHistory(h); setAgentRuns(r); } })
      .catch(() => { /* The shared API status shows outages; retry without discarding the last snapshot. */ });
    void load();
    const interval = setInterval(load, 10000);
    return () => { mounted = false; clearInterval(interval); };
  }, [base, isIntake]);
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
    if (!isIntake || !onProgressChange) return;
    onProgressChange({
      loaded: coverage !== null,
      selectedFileCount: files.length,
      batchStatus: batch?.status ?? null,
      batchIssues: batch?.counts.issues ?? 0,
      hasSnapshot: Boolean(snapshot),
      completedRunCount,
      runRunning: agentRunning,
    });
  }, [agentRunning, batch?.counts.issues, batch?.status, completedRunCount, coverage, files.length, isIntake, onProgressChange, snapshot]);

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

  return <section id="sources" className="mb-4 border border-line bg-surface p-4" aria-label="Records and investigation">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h2 className="text-base font-semibold">Records &amp; investigation</h2>
        <p className="mt-1 text-xs text-slate-500">Add and validate records first, then run an investigation from a committed snapshot.</p></div>
      <button className={button} onClick={() => setCreating(true)}>New institution</button>
    </div>
    {!isIntake && <p className="mt-3 text-xs text-slate-600">This workspace is a fixed demo. Create an institution to upload your own synthetic records or public documents. The local API must be running.</p>}
    {(error || apiError) && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-red-800">{error || apiError}. Check that the API is running on {API_URL}.</p>}
    {message && <p role="status" className="mt-3 rounded-lg bg-teal-50 p-3 text-teal-800">{message}</p>}

    {isIntake && <>
      <FileUpdates key={ws} ws={ws} revision={snapshot?.id} />
      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span>{coverage?.workspace.scope || "Loading scope…"}</span>
        <span>· {coverage?.workspace.currency}</span><span>· {coverage?.workspace.profile}</span>
        <button disabled={busy} className={button} onClick={() => act(refresh)}>Refresh sources</button>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {coverage?.capabilities.map((c) => <div key={c.id} className="rounded-lg border border-slate-200 p-3">
          <div className="font-semibold">{c.label}</div>
          <span className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[10px] ${c.status === "ready_for_scope" ? "bg-teal-50 text-teal-800" : "bg-amber-50 text-amber-800"}`}>{c.status.replaceAll("_", " ")}</span>
          {c.missing.length > 0 && <p className="mt-1 text-xs">Missing: {c.missing.map((r) => ROLES[r as SourceRole] || r).join(", ")}</p>}
          <p className="mt-1 text-[11px] text-slate-500">{c.note}</p>
        </div>)}
      </div>
      <p className="mt-2 text-[11px] text-slate-500">{coverage?.note} {agentRuns.length ? "The latest agent run remains a candidate triage, not an audit conclusion." : "Sources are available for review; no agent investigation has run."}</p>

      <div id="source-records" className="mt-5 scroll-mt-4 border-t border-line pt-4">
        <h3 className="font-semibold">1. Add records</h3>
        <p className="my-2 text-xs text-slate-500">CSV, TXT or Markdown · 20 files per import · 10 MB each / 50 MB total. Use ISO dates and exact amounts. No real private institutional data in this local demo.</p>
        <input ref={fileInput} aria-label="Choose source files" type="file" multiple accept=".csv,.txt,.md" disabled={busy}
          onChange={(e) => setFiles(Array.from(e.target.files || []).map((file) => ({ file, options: defaults() })))} />
        <div className="mt-3 border-l-2 border-ink bg-surface-2 p-3">
          <p className="text-xs font-semibold">Fastest safe test: fictional September starter pack</p>
          <p className="my-2 text-xs text-ink-dim">Stages seven synthetic files for a USD workspace dated September 1–30, 2026. You can inspect them before previewing, and nothing is committed automatically.</p>
          <div className="flex flex-wrap gap-2">
            <button disabled={busy || coverage?.workspace.kind === "public"} className={primary} onClick={() => setFiles(sample.files.filter((f) => !f.later).map((f) => ({
              file: new File([f.content], f.name, { type: f.name.endsWith(".csv") ? "text/csv" : "text/plain" }),
              options: defaults(f.role as SourceRole),
            })))}>Use fictional starter pack</button>
          </div>
          <details className="mt-3 text-xs"><summary className="cursor-pointer font-semibold">Later evidence and individual downloads</summary><div className="mt-2 flex flex-wrap gap-2">
            <button disabled={busy} className={button} onClick={() => setFiles(sample.files.filter((f) => f.later).map((f) => ({ file: new File([f.content], f.name, { type: "text/plain" }), options: defaults(f.role as SourceRole) })))}>Stage service evidence</button>
            {sample.files.map((f) => <button key={f.name} className={button} onClick={() => download(f.name, f.content)}>↓ {f.name}</button>)}
          </div></details>
        </div>
        {files.map((f, i) => <div key={i} className="mt-2 grid gap-2 rounded-lg border border-slate-200 p-2 sm:grid-cols-[1fr_200px_100px]">
          <span className="self-center truncate text-xs">{f.file.name} · {(f.file.size / 1024).toFixed(1)} KB</span>
          <select aria-label={`Role for ${f.file.name}`} className={input} value={f.options.role} onChange={(e) => setFiles((all) => all.map((x, n) => n === i ? { ...x, options: { ...x.options, role: e.target.value as SourceRole } } : x))}>
            {Object.entries(ROLES).map(([r, label]) => <option key={r} value={r}>{label}</option>)}
          </select>
          <label className="text-[10px]">Version<input aria-label={`Version for ${f.file.name}`} className={input} type="number" min={1} value={f.options.source_version} onChange={(e) => setFiles((all) => all.map((x, n) => n === i ? { ...x, options: { ...x.options, source_version: Number(e.target.value) } } : x))} /></label>
        </div>)}
        <button disabled={busy || !files.length} className={primary + " mt-3"} onClick={() => act(async () => {
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
          {history.map((h) => <option key={h.id} value={h.id}>{h.created_at.slice(0, 19)} · {h.status} · {h.id.slice(-6)}</option>)}
        </select>
      </label>}

      {batch && <div id="source-import" className="mt-4 scroll-mt-4 border border-line p-3">
        <h3 className="font-semibold">2. Validate and commit · {batch.status.replaceAll("_", " ")}</h3>
        <p className="my-2 text-xs">{batch.counts.parsed} source rows/lines · {batch.counts.valid_records} valid records · {batch.counts.new_records} new · {batch.counts.duplicate_records} duplicates · {batch.counts.issues} issues</p>
        <p className="text-xs">Validated debit total: {(batch.totals.debit_cents / 100).toFixed(2)} · credit: {(batch.totals.credit_cents / 100).toFixed(2)} {coverage?.workspace.currency}</p>
        <p className="mt-1 text-[11px] text-slate-500">Totals combine opening and activity files for import control only; they are not a financial statement. {batch.coverage_note}</p>
        {batch.files.map((f) => <details key={f.id} className="mt-3 bg-surface-2 p-3">
          <summary className="cursor-pointer font-semibold">{f.name} · {f.row_count} rows/lines {f.duplicate_of ? "· identical bytes already uploaded" : ""} · mapping and preview</summary>
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
            <tbody>{f.preview.map((row, i) => <tr key={i}><td className="p-1 align-top"><button className="text-teal-700 underline" onClick={() => act(() => viewSource(f.id, row.locator))}>{row.locator}</button></td><td className="p-1"><pre className="max-w-[650px] whitespace-pre-wrap break-all">{JSON.stringify(row.payload, null, 2)}</pre></td></tr>)}</tbody>
          </table></div>}
        </details>)}
        {batch.issues.length > 0 && <ul className="mt-3 space-y-1" aria-label="Validation issues">{batch.issues.map((i, n) => <li key={n} className="rounded bg-red-50 p-2 text-xs text-red-800">
          <b>{i.code}</b>: {i.message} {i.field && `(${i.field})`}
          {i.source_id !== "batch" && <button className="ml-2 underline" onClick={() => act(() => viewSource(i.source_id, i.locator || 1))}>Open source {i.locator ? `line ${i.locator}` : ""}</button>}
        </li>)}</ul>}
        {batch.issues_truncated && <p className="text-xs">Showing the first 500 issues; resolve these and revalidate.</p>}
        {batch.changes.length > 0 && <details className="my-2"><summary className="font-semibold">Review {batch.changes.length} superseding record changes</summary><pre className="overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(batch.changes, null, 2)}</pre></details>}
        {batch.status !== "committed" ? <div className="mt-3 flex flex-wrap gap-2">
          <button disabled={busy} className={button} onClick={() => act(async () => showBatch(await intakeApi<ImportBatch>(base + "/imports/" + batch.id + "/mapping", {
            method: "PATCH", body: JSON.stringify({ expected_version: batch.version, files: draft }),
          }))) }>Save mappings & revalidate</button>
          <button disabled={busy || batch.status !== "ready_to_commit" || Boolean(draftChanged)} className={primary} onClick={() => act(async () => {
            showBatch(await intakeApi<ImportBatch>(base + "/imports/" + batch.id + "/commit", {
              method: "POST", body: JSON.stringify({ expected_version: batch.version, idempotency_key: batch.id + ":" + batch.version }),
            }));
            setFiles([]); if (fileInput.current) fileInput.current.value = "";
            await Promise.all([refresh(), refreshBundle()]);
            setMessage("Records committed. Originals and the snapshot are saved locally. No financial correction or agent investigation was performed.");
          })}>Confirm & commit records</button>
          <span className="self-center text-[11px] text-slate-500">Local reviewer · commits validated records, not accounting adjustments</span>
        </div> : <p className="mt-3 font-mono text-xs text-teal-700">Saved snapshot: {batch.snapshot_id}</p>}
      </div>}

      <div id="source-agent" className="mt-5 scroll-mt-4 border border-line bg-surface-2 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h3 className="font-semibold">3. Run an investigation · {AGENTS[selectedAgent].label} <span className="bg-surface-3 px-1.5 py-0.5 text-[10px] text-ink-dim">MODEL CALL ON START</span></h3>
            <p className="mt-1 max-w-3xl text-xs text-ink-dim">Reviews the committed snapshot and returns cited observations and suggested next steps. The API must have a model provider configured. Selected records and source excerpts are sent only when you press Run.</p></div>
          {agentRuns[0] && <span className="text-[11px] text-slate-500">Latest: {agentRuns[0].status} · {agentRuns[0].model}{agentRuns[0].current_snapshot ? "" : " · stale snapshot"}</span>}
        </div>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <select aria-label="Investigation agent" className={input} disabled={agentBusy || agentRunning} value={selectedAgent} onChange={(e) => {
            const agent = e.target.value as AgentChoice;
            setSelectedAgent(agent); setAgentFocus(AGENTS[agent].focus); setError(""); setMessage(""); setStartedRun(null);
          }}>{Object.entries(AGENTS).map(([id, agent]) => <option key={id} value={id}>{agent.label}</option>)}</select>
          <input aria-label="Agent focus" className={input} value={agentFocus} maxLength={500} onChange={(e) => setAgentFocus(e.target.value)} />
          <button disabled={busy || agentBusy || agentRunning || !snapshot || !agentFocus.trim()} className={primary + " whitespace-nowrap"} onClick={async () => {
            setAgentBusy(true); setError(""); setMessage("");
            try {
              if (coordinator) {
                // The coordinator runs in the background and reports through the bundle.
                const started = await intakeApi<{ id: string }>("/api/cfo/runs", { method: "POST", body: JSON.stringify({
                  workspace: ws, mode: "live", workflow: "five_agent", objective: agentFocus,
                }) });
                setStartedRun(started.id);
                setMessage("Five-agent workflow started. Findings and proposals appear as the run progresses.");
              } else {
                const run = await intakeApi<AgentRun>(base + "/agent-runs", { method: "POST", body: JSON.stringify({
                  agent: selectedAgent, focus: agentFocus, snapshot_id: snapshot!.id, request_id: crypto.randomUUID(),
                }) });
                setAgentRuns((runs) => [run, ...runs.filter((r) => r.id !== run.id)]);
                setMessage(`${AGENTS[selectedAgent].label} review saved. Review the candidate findings and suggested evidence below.`);
              }
              await refreshBundle();
            } catch (e) { setError(e instanceof Error ? e.message : "Agent request failed"); }
            finally { setAgentBusy(false); void refresh().catch(() => {}); }
          }}>{agentBusy || agentRunning ? "Agent working…" : AGENTS[selectedAgent].action}</button>
        </div>
        {startedRun && (
          <p className="mt-2 text-xs">
            <Link href="/cfo" className="font-semibold text-teal-700 underline">
              Follow run {startedRun} →
            </Link>
          </p>
        )}
        {coordinator && <p className="mt-2 text-xs text-slate-500">The CFO plans, AP &amp; Payments, Payroll &amp; Budget and Grants &amp; Compliance investigate in parallel, and the Internal Auditor re-reads the sources and redoes the math before anything is reported. Uses this workspace&rsquo;s committed snapshot and paid API calls.</p>}
        {!snapshot && <p className="mt-2 text-xs text-amber-700">Commit at least one valid source snapshot before running the agent.</p>}
        {selectedAgent === "grants_compliance" && <p className="mt-2 text-xs text-slate-500">Checks supplied award terms and payroll service periods. Payroll totals are not complete grant expenditure. Findings remain unreviewed; no compliance certification is issued.</p>}
        {selectedAgent === "internal_auditor" && <p className="mt-2 text-xs text-slate-500">Run CFO or Grants first. Reviews up to four findings per run using fresh source reads and calculation checks. Accept means the limited claim is supported—not approval of a transaction or an audit opinion.</p>}
        {agentRuns[0]?.review_targets_current === false && <p className="mt-2 text-xs text-amber-700">A preparer reran or the snapshot changed. These historical verdicts do not cover all current findings; rerun the Auditor.</p>}
        {agentRuns[0]?.error && <p className="mt-3 rounded bg-red-50 p-2 text-xs text-red-800">{agentRuns[0].error}</p>}
        {agentRuns[0]?.result.analysis && <div className="mt-4 border-t border-violet-100 pt-3">
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
            <span>snapshot {agentRuns[0].snapshot_id}</span><span>{agentRuns[0].result.tool_calls?.length || 0} logged tool calls</span>
            <span>{agentRuns[0].result.usage?.total_tokens || 0} tokens</span>
          </div>
          <p className="mt-2 text-sm"><b>Briefing:</b> {agentRuns[0].result.analysis.executive_briefing}</p>
          <p className="mt-1 text-xs text-slate-500">Scope: {agentRuns[0].result.analysis.scope_assessed}</p>
          {agentRuns[0].result.review_scope && <p className="mt-2 text-xs">Reviewed {agentRuns[0].result.review_scope.reviewed_count} of {agentRuns[0].result.review_scope.candidate_count} candidate findings in this run. Remaining findings are unreviewed.</p>}
          {agentRuns[0].result.analysis.reviews?.map((review) => <div key={review.finding_id} className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
            <b>Auditor verdict: {review.verdict.replaceAll("_", " ")}</b>
            <p className="break-all font-mono text-[10px] text-slate-500">{review.finding_id}</p>
            <p className="mt-1 text-xs">{review.rationale}</p>
            <p className="mt-1 text-xs">Required action: {review.required_action || "No further action proposed within this limited review."}</p>
            <div className="mt-2 flex flex-wrap gap-2">{review.citations.map((citation, index) => <button key={index} className="text-xs text-teal-700 underline" onClick={() => act(() => viewSource(citation.source_id, citation.line))}>
              Source line {citation.line}: “{citation.quote}”
            </button>)}</div>
          </div>)}
          {agentRuns[0].result.analysis.findings.map((finding, index) => <div key={index} className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
            <div className="flex flex-wrap items-center gap-2"><b>{finding.title}</b><span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-800">{finding.status === "cleared" ? "proposed clearance · unreviewed" : finding.status.replaceAll("_", " ")}</span></div>
            <p className="mt-1 text-xs">{finding.summary}</p>
            <div className="mt-2 flex flex-wrap gap-2">{finding.citations.map((citation) => <button key={`${citation.source_id}:${citation.line}`} className="text-xs text-teal-700 underline" onClick={() => act(() => viewSource(citation.source_id, citation.line))}>
              Source line {citation.line}: “{citation.quote}”
            </button>)}</div>
            {finding.limitations.length > 0 && <p className="mt-2 text-[11px] text-slate-500">Limits: {finding.limitations.join("; ")}</p>}
          </div>)}
          {agentRuns[0].result.analysis.next_tasks.length > 0 && <div className="mt-3"><b className="text-xs">Proposed specialist work</b><ul className="mt-1 list-disc pl-5 text-xs">
            {agentRuns[0].result.analysis.next_tasks.map((task, index) => <li key={index}><b>{task.title}</b> · {task.objective}</li>)}
          </ul></div>}
          {agentRuns[0].result.analysis.evidence_requests.map((request, index) => <div key={index} className="mt-3 rounded border border-amber-200 bg-white p-3 text-xs">
            <b>Suggested evidence: {request.title}</b><p className="my-1">{request.reason}</p>
            <button className={button} disabled={busy || !agentRuns[0].current_snapshot || Boolean(coverage?.requests.some((r) => r.task_id === agentRuns[0].id && r.title === request.title))}
              onClick={() => act(async () => {
                setCoverage(await intakeApi<Coverage>(base + "/evidence-requests", { method: "POST", body: JSON.stringify({
                  title: request.title, role: request.role, task_id: agentRuns[0].id,
                }) }));
              })}>Add evidence request</button>
          </div>)}
          {agentRuns[0].result.analysis.limitations.length > 0 && <p className="mt-3 text-xs text-slate-500"><b>Run limitations:</b> {agentRuns[0].result.analysis.limitations.join("; ")}</p>}
        </div>}
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div><h3 className="font-semibold">Committed sources</h3>
          {!coverage?.sources.length && <p className="mt-2 text-xs text-slate-500">No committed sources yet.</p>}
          {coverage?.sources.map((s) => <button key={s.id} className="mt-2 flex w-full justify-between gap-2 rounded-lg border border-slate-200 p-2 text-left text-xs hover:bg-slate-50" onClick={() => act(() => viewSource(s.id))}>
            <span>{s.name}<small className="block text-slate-400">{ROLES[s.role]}</small></span><span>{s.active ? "Active" : "Historical / duplicate"} ↗</span>
          </button>)}
        </div>
        <div><h3 className="font-semibold">Missing evidence requests</h3>
          <p className="my-2 text-[11px] text-slate-500">Track evidence for later review. Attaching a document does not mean an auditor verified it.</p>
          <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); const form = e.currentTarget; const d = new FormData(form);
            act(async () => { setCoverage(await intakeApi<Coverage>(base + "/evidence-requests", { method: "POST", body: JSON.stringify({ title: d.get("title"), role: d.get("role") }) })); form.reset(); }); }}>
            <input required name="title" aria-label="Evidence request" placeholder="What evidence is missing?" className={input} />
            <select name="role" defaultValue="service" aria-label="Requested evidence role" className={input}>{Object.entries(ROLES).map(([r, label]) => <option key={r} value={r}>{label}</option>)}</select>
            <button disabled={busy} className={button}>Add request</button>
          </form>
          {coverage?.requests.map((r) => <div key={r.id} className="mt-3 rounded-lg border border-slate-200 p-3">
            <b>{r.title}</b><span className="ml-2 text-xs text-slate-500">{r.status.replaceAll("_", " ")}</span>
            <select aria-label={`Attach evidence for ${r.title}`} disabled={busy} className={input + " mt-2"} value="" onChange={(e) => {
              const id = e.target.value; if (!id) return;
              act(async () => { setCoverage(await intakeApi<Coverage>(base + "/evidence-requests/" + r.id + "/responses", {
                method: "POST", body: JSON.stringify({ source_id: id, expected_version: r.version }),
              })); setMessage("Evidence linked. A resumption event is saved for the future agent runtime; review is still required."); });
            }}><option value="">Attach a committed {ROLES[r.role].toLowerCase()} source…</option>
              {coverage.sources.filter((s) => s.active && s.role === r.role).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            {r.source_id && <button className="mt-1 text-xs text-teal-700 underline" onClick={() => act(() => viewSource(r.source_id!))}>View attached evidence</button>}
          </div>)}
        </div>
      </div>
    </>}

    {creating && <Modal title="Create an institution workspace" close={() => !busy && setCreating(false)}>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); const d = Object.fromEntries(new FormData(e.currentTarget));
        act(async () => { const w = await intakeApi<IntakeWorkspace>("/api/workspaces", { method: "POST", body: JSON.stringify(d) });
          await refreshWorkspaces(); setCreating(false); setWs(w.id); }); }}>
        <label className="text-xs">Institution name<input name="name" required maxLength={120} placeholder="Your fictional school or public-report institution" className={input} /></label>
        <label className="text-xs">Institution type<select name="entity_type" className={input}>{["school", "district", "board", "university"].map((v) => <option key={v}>{v}</option>)}</select></label>
        <label className="text-xs">Data origin<select name="kind" className={input}><option value="synthetic">Synthetic records</option><option value="public">Public documents only</option></select></label>
        <label className="text-xs">Currency<select name="currency" className={input}>{["USD", "CAD", "EUR", "GBP"].map((v) => <option key={v}>{v}</option>)}</select></label>
        <label className="text-xs">Period start<input type="date" name="start" required defaultValue="2026-09-01" className={input} /></label>
        <label className="text-xs">Period end<input type="date" name="end" required defaultValue="2026-09-30" className={input} /></label>
        <label className="text-xs">Jurisdiction<input name="jurisdiction" required defaultValue="Demo" className={input} /></label>
        <label className="text-xs">Scope<input name="scope" required placeholder="e.g. September payroll and grant allocation" className={input} /></label>
        <p className="text-xs text-slate-500 sm:col-span-2">Synthetic accounting uses the USD demo management profile. Other currencies are available for public-document exploration. This local build is for synthetic and public data.</p>
        {error && <p role="alert" className="text-red-700 sm:col-span-2">{error}</p>}
        <button disabled={busy} className={primary}>{busy ? "Creating…" : "Create workspace"}</button>
      </form>
    </Modal>}
    {source && <Modal title={source.name} close={() => setSource(null)}>
      <p className="break-all font-mono text-[10px] text-slate-400">SHA-256 {source.sha256}</p>
      <p className="my-2 text-xs">{source.extraction_origin ? "Human-reviewed extraction (derived from the original below)" : source.committed ? "Committed original" : "Staged original — not authoritative"} · {source.line_count} lines · version {source.options.source_version}</p>
      <a className="text-xs text-teal-700 underline" href={API_URL + base + "/sources/" + source.id + "/download"}>{source.extraction_origin ? "Download reviewed extraction" : "Download unchanged original"}</a>
      {source.extraction_origin && <div className="my-2 text-xs">
        <p>This record was extracted and reviewed. The original document remains preserved separately.</p>
        <a className="text-teal-700 underline" href={`${API_URL}${base}/extraction/documents/${source.extraction_origin.document_id}/original`}>Download original: {source.extraction_origin.name}</a>
        {source.extraction_origin.has_images && source.extraction_origin.pages.map((page) => <a key={page} target="_blank" rel="noreferrer" className="ml-3 text-teal-700 underline" href={`${API_URL}${base}/extraction/documents/${source.extraction_origin!.document_id}/pages/${page}`}>Original page {page}</a>)}
      </div>}
      <div className="my-3 max-h-[50vh] overflow-auto rounded border border-slate-200 bg-slate-50 p-3">
        {source.lines.map((l) => <div key={l.number} className="flex gap-3 font-mono text-xs"><span className="w-10 flex-none select-none text-right text-slate-400">{l.number}</span><pre className="whitespace-pre-wrap break-all">{l.text || " "}</pre></div>)}
      </div>
      <div className="flex gap-2">
        <button className={button} disabled={busy || (source.lines[0]?.number || 1) <= 1} onClick={() => act(() => viewSource(source.id, Math.max(1, source.lines[0].number - 100)))}>Previous lines</button>
        <button className={button} disabled={busy || (source.lines.at(-1)?.number || 0) >= source.line_count} onClick={() => act(() => viewSource(source.id, (source.lines.at(-1)?.number || 0) + 1))}>Next lines</button>
      </div>
    </Modal>}
  </section>;
}
