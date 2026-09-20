"use client";

import { displayLabel } from "@/lib/format";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

import type { IntakeUiProgress } from "@/lib/workflow";
import { DataRequirements } from "@/components/DataRequirements";
import { FileUpdates } from "@/components/FileUpdates";
import { StarterPacks } from "@/components/StarterPacks";
import { AnimatedDisclosure } from "@/components/ui/animated-disclosure";
import { AnimatedDropdown } from "@/components/ui/animated-dropdown";
import { API_URL, intakeApi, useData } from "@/lib/data";
import type { Coverage, ImportBatch, IntakeWorkspace, SourceDetail, SourceOptions, SourceRole } from "@/lib/types";

// Keyed by string rather than SourceRole: the server owns the role list, and the
// money-in roles are offered here as soon as it accepts them.
const ROLES: Record<string, string> = {
  chart: "Chart of accounts", opening: "Opening trial balance", ledger: "General ledger",
  vendors: "Vendors", purchase_orders: "Purchase orders", goods_receipts: "Goods receipts",
  vendor_invoices: "Vendor invoices", payments: "Vendor payments",
  customers: "Customers", customer_invoices: "Customer invoices", remittances: "Customer remittances",
  bank_transactions: "Bank transactions", processor_payouts: "Payment processor payouts",
  payroll: "Payroll", expenses: "Employee expenses",
  budgets: "Approved budget", forecasts: "Forecast", headcount: "Headcount",
  approvals: "Approvals", period_locks: "Period locks", tax_registrations: "Tax registrations",
  contract: "Contracts", policy: "Policies", document: "Other document",
};
//: The same role list the three role dropdowns offer, in the order ROLES declares it.
const ROLE_OPTIONS = Object.entries(ROLES).map(([value, label]) => ({ value, label }));
const input = "w-full border border-line bg-white px-2.5 py-2 text-xs";
const button = "border border-line px-3 py-2 text-xs font-semibold hover:bg-surface-2 disabled:opacity-40";
const primary = "bg-ink px-3 py-2 text-xs font-semibold text-white hover:bg-ink-dim disabled:opacity-40";
const fieldLayout: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 6, minWidth: 0 };
const fieldControl: React.CSSProperties = { boxSizing: "border-box", width: "100%", minWidth: 0, height: 34, padding: "6px 10px", border: "1px solid #d4d4d8", background: "white", lineHeight: "20px", outlineOffset: -2 };
//: Where in this panel an action was taken, so its outcome can be reported
//: beside the control instead of at the top of a long screen.
type Scope = "top" | "import";

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
  const isIntake = Boolean(bundle.workspace.intake);
  const [creating, setCreating] = useState(false);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [history, setHistory] = useState<{ id: string; status: string; created_at: string }[]>([]);
  const [files, setFiles] = useState<{ file: File; options: SourceOptions }[]>([]);
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [scope, setScope] = useState<Scope>("top");
  //: Keyed by source, line and field, so two blanks on one row stay separate.
  const [supply, setSupply] = useState<Record<string, string>>({});
  const [supplyNote, setSupplyNote] = useState("");
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
    // here is meaningful until someone has created a company.
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

  /**
   * Run one action and remember where it was taken.
   *
   * Committing an import is done at the bottom of a long panel while its
   * confirmation rendered at the top, so the most consequential action on this
   * screen appeared to do nothing. `where` puts the outcome beside the button.
   */
  async function act(fn: () => Promise<void>, where: Scope = "top") {
    setBusy(true); setError(""); setMessage(""); setScope(where);
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "Request failed"); }
    finally { setBusy(false); }
  }
  function renderOutcome(at: Scope) {
    if (scope !== at) return null;
    if (error) return <p role="alert" className="mt-3 w-full border border-red-300 bg-red-50 p-3 text-[13px] text-red-800">{error}</p>;
    if (message) return <p role="status" className="mt-3 w-full border-l-4 border-green-700 bg-green-50 p-3 text-[13px] text-green-900"><b>Done.</b> {message}</p>;
    return null;
  }
  function showBatch(b: ImportBatch) { setBatch(b); setDraft(Object.fromEntries(b.files.map((f) => [f.id, f.options]))); }
  function edit(id: string, updates: Partial<SourceOptions>) {
    setDraft((d) => ({ ...d, [id]: { ...d[id], ...updates } }));
  }
  async function viewSource(id: string, line = 1) {
    setSource(await intakeApi<SourceDetail>(`${base}/sources/${id}?start=${line}`));
  }
  const draftChanged = batch && batch.files.some((f) => JSON.stringify(f.options) !== JSON.stringify(draft[f.id]));
  //: The newest import that has been staged but never committed. `/imports`
  //: returns newest first, so the first match is the one to act on.
  const waiting = history.find((h) => h.status !== "committed");

  return <section className="mb-4 border border-line bg-white p-4" aria-label="Sources and coverage">
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
    {message && scope === "top" && <p role="status" className="mt-3 bg-surface-2 p-3 text-ink">{message}</p>}

    {isIntake && <>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-ink-dim">
        <span>{coverage?.workspace.scope || (ws ? "Loading scope…" : "No company yet — create one to add records.")}</span>
        <span>· {coverage?.workspace.currency}</span>
        <button disabled={busy} className={button} onClick={() => act(async () => {
          await refresh();
          if (batch && batch.status !== "committed") {
            setMessage("Sources refreshed. Finish the current import before detecting saved files."); return;
          }
          const result = await intakeApi<{batch: ImportBatch | null; detected: number}>(base + "/sources/detect", {method: "POST"});
          if (result.batch) {
            showBatch(result.batch);
            setMessage(`Detected ${result.detected} saved files. Review and commit the import to update requirements.`);
          } else setMessage("Sources refreshed. Requirements reflect committed records; unmatched or older formats need review.");
        })}>Refresh sources</button>
      </div>
      {coverage && <DataRequirements ws={ws} coverage={coverage} onSaved={refresh} />}
      <p className="mt-2 text-[11px] text-ink-dim">{coverage?.note}</p>

      <div className="mt-5 border border-line bg-surface-2 p-4">
        <h3 className="font-semibold">Running the agents</h3>
        <p className="mt-1 max-w-prose text-xs text-ink-dim">
          Books is where the records go in. The agents are started from Investigation, so
          there is one place a paid run can begin rather than two.
        </p>
        <Link href="/investigation" className="mt-3 inline-block text-sm font-semibold text-ink underline">
          Open the investigation &rarr;
        </Link>
      </div>

      <FileUpdates key={ws} ws={ws} revision={snapshot?.id} />

      <StarterPacks
        period={coverage?.workspace.id === ws ? coverage.workspace : null}
        disabled={busy}
        onLoad={(loaded) => {
          setFiles(loaded.map(({ file, role }) => ({ file, options: defaults(role) })));
          // The chooser holds the browser's own selection, which a pack has not
          // touched; clearing it stops it contradicting the list below.
          if (fileInput.current) fileInput.current.value = "";
          setBatch(null);
          setMessage(`${loaded.length} sample files staged below. Preview the import to check how they were read.`);
        }}
      />
      <div id="source-records" className="mt-5 scroll-mt-4 border-t border-line pt-4">
        <h3 className="font-semibold">1. Add records</h3>
        <p className="my-2 text-xs text-ink-dim">CSV only · 20 files per import · 10 MB each / 50 MB total. Use ISO dates and exact amounts. A document — an invoice, a policy, a contract — goes through <a href="#source-documents" className="underline">Add a document</a> as a PDF instead. Upload only records you are authorized to process.</p>
        <div className="my-3 flex flex-wrap items-center gap-3">
          <button type="button" className={primary} style={{ background: "#09090b", color: "white", border: "1px solid #09090b", padding: "10px 16px" }} disabled={busy} onClick={() => fileInput.current?.click()}>Choose files</button>
          <span className="text-xs text-ink-dim" aria-live="polite">{files.length ? `${files.length} files selected` : "No files selected"}</span>
        </div>
        <input style={{ display: "none" }} ref={fileInput} aria-label="Choose source files" type="file" multiple disabled={busy}
          onChange={(e) => {
            const selected = Array.from(e.target.files || []);
            if (selected.some(file => !/\.csv$/i.test(file.name))) {
              setError("Choose CSV files here. Use Documents for PDFs."); e.target.value = ""; return;
            }
            setError(""); setFiles(selected.map(file => ({ file, options: defaults() })));
          }} />
        {files.map((f, i) => <div key={i} className="mt-2 grid gap-2 border border-line p-2 sm:grid-cols-[1fr_200px_100px]">
          <span className="self-center truncate text-xs">{f.file.name} · {(f.file.size / 1024).toFixed(1)} KB</span>
          <AnimatedDropdown aria-label={`Role for ${f.file.name}`} className="w-full" options={ROLE_OPTIONS} value={f.options.role}
            onChange={(value) => setFiles((all) => all.map((x, n) => n === i ? { ...x, options: { ...x.options, role: value as SourceRole } } : x))} />
          <label className="text-[10px]">Version<input aria-label={`Version for ${f.file.name}`} className={input} type="number" min={1} value={f.options.source_version} onChange={(e) => setFiles((all) => all.map((x, n) => n === i ? { ...x, options: { ...x.options, source_version: Number(e.target.value) } } : x))} /></label>
        </div>)}
        <button disabled={busy || !files.length} className={primary + " mt-3"} onClick={() => act(async () => {
          if (files.length > 20 || files.some((f) => f.file.size > 10 * 1024 * 1024) || files.reduce((n, f) => n + f.file.size, 0) > 50 * 1024 * 1024) throw new Error("Upload exceeds file or batch limits");
          const form = new FormData();
          files.forEach((f) => form.append("files", f.file));
          form.append("metadata", JSON.stringify(files.map((f) => ({ ...f.options, auto_detect: f.options.role === "document" }))));
          showBatch(await intakeApi<ImportBatch>(base + "/imports", { method: "POST", body: form }));
          await refresh();
        })}>{busy ? "Working…" : "Preview import"}</button>
      </div>

      {/* An import staged from the Document lab is created server-side, so this
          panel learns about it from the poll and otherwise said nothing: the
          Document lab told people to "scroll up to the import" and there was
          nothing up here to scroll to. An import waiting to be committed is
          the one thing on this screen that needs attention, so it says so and
          opens itself. */}
      {!batch && waiting && <div className="mt-4 border border-amber-300 bg-amber-50 p-3">
        <b className="text-[13px]">An import is staged and waiting to be committed.</b>
        <p className="my-1 text-[12.5px]">
          {waiting.created_at.slice(0, 19).replace("T", " ")} · nothing is in the books until you
          review and commit it.
        </p>
        <button className={button} disabled={busy}
          onClick={() => act(async () => showBatch(await intakeApi<ImportBatch>(base + "/imports/" + waiting.id)))}>
          Open it to review and commit
        </button>
      </div>}

      {history.length > 0 && <label className="mt-4 block text-xs">Resume an import
        <AnimatedDropdown className="mt-1 w-full" placeholder="Choose saved import…" value={batch?.id || ""} disabled={busy}
          options={history.map((h) => ({ value: h.id, label: `${h.created_at.slice(0, 19)} · ${displayLabel(h.status)} · ${h.id.slice(-6)}` }))}
          onChange={(id) => { if (id) act(async () => showBatch(await intakeApi<ImportBatch>(base + "/imports/" + id))); }} />
      </label>}

      {batch && <div id="source-import" className="mt-4 scroll-mt-4 border border-line p-3">
        <h3 className="font-semibold">2. Review import · {displayLabel(batch.status)}</h3>
        <p className="my-2 text-xs">{batch.counts.parsed} source rows/lines · {batch.counts.valid_records} valid records · {batch.counts.new_records} new · {batch.counts.duplicate_records} duplicates · {batch.counts.issues} issues</p>
        <p className="text-xs">Validated debit total: {(batch.totals.debit_cents / 100).toFixed(2)} · credit: {(batch.totals.credit_cents / 100).toFixed(2)} {coverage?.workspace.currency}</p>
        <p className="mt-1 text-[11px] text-ink-dim">Totals combine opening and activity files for import control only; they are not a financial statement. {batch.coverage_note}</p>
        {batch.files.map((f) => <AnimatedDisclosure key={f.id} className="mt-3 bg-surface-2 p-3" summaryClassName="font-semibold"
          summary={<>{f.name} · {f.row_count} rows/lines {f.duplicate_of ? "· identical bytes already uploaded" : ""}</>}>
          <button className={button + " mt-2"} onClick={() => act(() => viewSource(f.id))}>View original</button>
          {batch.status !== "committed" && draft[f.id] && <>
            <div className="my-2 grid gap-2 sm:grid-cols-3">
              <label className="text-xs">Record type<AnimatedDropdown className="w-full" options={ROLE_OPTIONS} value={draft[f.id].role} onChange={(value) => edit(f.id, { role: value as SourceRole, mapping: {} })} /></label>
              <label className="text-xs">Source system<input className={input} value={draft[f.id].source_system} onChange={(e) => edit(f.id, { source_system: e.target.value })} /></label>
              <label className="text-xs">Source version<input className={input} type="number" min={1} value={draft[f.id].source_version} onChange={(e) => edit(f.id, { source_version: Number(e.target.value) })} /></label>
              <label className="text-xs">Amount units<AnimatedDropdown className="w-full" options={[{ value: "major", label: "Dollars (100.00)" }, { value: "minor", label: "Cents (10000)" }]} value={draft[f.id].amount_unit} onChange={(value) => edit(f.id, { amount_unit: value as "major" | "minor" })} /></label>
              <label className="text-xs">Document ID (for revisions)<input className={input} value={draft[f.id].external_id} onChange={(e) => edit(f.id, { external_id: e.target.value })} placeholder="Stable document identifier" /></label>
              <label className="text-xs">Applies to<input className={input} value={draft[f.id].applies_to} onChange={(e) => edit(f.id, { applies_to: e.target.value })} placeholder="Record or award ID" /></label>
              <label className="text-xs">Expected CSV rows<input className={input} type="number" min={0} value={draft[f.id].expected_rows ?? ""} onChange={(e) => edit(f.id, { expected_rows: e.target.value === "" ? null : Number(e.target.value) })} /></label>
              {(["debit", "credit"] as const).map((side) => <label key={side} className="text-xs">Expected {side} total<input className={input} value={draft[f.id][`expected_${side}`] ?? ""} onChange={(e) => edit(f.id, { [`expected_${side}`]: e.target.value || null })} /></label>)}
            </div>
            <div className="grid gap-2 sm:grid-cols-3">{f.required_fields.map((field) => <label key={field} className="text-xs">{field}
              <AnimatedDropdown className="w-full" placeholder="Select CSV column…" options={f.headers.map((h) => ({ value: h, label: h }))}
                value={draft[f.id].mapping[field] ?? (f.headers.includes(field) ? field : "")}
                onChange={(value) => edit(f.id, { mapping: { ...draft[f.id].mapping, [field]: value } })} /></label>)}</div>
            <label className="mt-3 flex items-center gap-2 text-xs"><input type="checkbox" checked={draft[f.id].excluded} onChange={(e) => edit(f.id, { excluded: e.target.checked })} />Exclude this file from the import</label>
            {draft[f.id].excluded && <input aria-label="Exclusion reason" className={input + " mt-1"} placeholder="Reason required" value={draft[f.id].exclusion_reason} onChange={(e) => edit(f.id, { exclusion_reason: e.target.value })} />}
          </>}
          {f.preview.length > 0 && <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-[11px]">
            <thead><tr><th className="p-1">Source line</th><th className="p-1">Normalized record (amounts in cents)</th></tr></thead>
            <tbody>{f.preview.map((row, i) => <tr key={i}><td className="p-1 align-top"><button className="text-ink underline" onClick={() => act(() => viewSource(f.id, row.locator))}>{row.locator}</button></td><td className="p-1"><pre className="max-w-[650px] whitespace-pre-wrap break-all">{JSON.stringify(row.payload, null, 2)}</pre></td></tr>)}</tbody>
          </table></div>}
        </AnimatedDisclosure>)}
        {batch.issues.length > 0 && <ul className="mt-3 space-y-1" aria-label="Validation issues">{batch.issues.map((i, n) => <li key={n} className="bg-red-50 p-2 text-xs text-accent-bad">
          <b>{i.code}</b>: {i.message} {i.field && `(${i.field})`}
          {i.source_id !== "batch" && <button className="ml-2 underline" onClick={() => act(() => viewSource(i.source_id, i.locator || 1))}>Open source {i.locator ? `line ${i.locator}` : ""}</button>}
          {/* A value the document never stated has to come from somewhere, and
              there was nowhere to put it. Offered only for a blank the source
              left empty: a value the source does state is evidence, and the
              API refuses to overwrite it. */}
          {i.code === "required_field" && i.field && i.locator && i.source_id !== "batch" &&
            <span className="ml-2 inline-flex flex-wrap items-center gap-1">
              <input aria-label={`Supply ${i.field} for line ${i.locator}`} className="border border-line px-2 py-1 text-xs"
                placeholder={`Supply ${i.field}`} value={supply[`${i.source_id}:${i.locator}:${i.field}`] || ""}
                onChange={(e) => setSupply((v) => ({ ...v, [`${i.source_id}:${i.locator}:${i.field}`]: e.target.value }))} />
              <button className="underline" disabled={busy || !(supply[`${i.source_id}:${i.locator}:${i.field}`] || "").trim()}
                onClick={() => act(async () => {
                  const key = `${i.source_id}:${i.locator}:${i.field}`;
                  showBatch(await intakeApi<ImportBatch>(base + "/imports/" + batch.id + "/values", {
                    method: "POST",
                    body: { expected_version: batch.version, source_id: i.source_id, note: supplyNote.trim() || "Supplied by the reviewer; the source did not state it.",
                            edits: [{ locator: i.locator, field: i.field, value: supply[key].trim() }] },
                  }));
                  setSupply((v) => ({ ...v, [key]: "" }));
                  setMessage(`Supplied ${i.field} on line ${i.locator}. It is recorded against you as a value the source did not state, and the import was revalidated.`);
                }, "import")}>Save value</button>
            </span>}
        </li>)}
        <li className="p-2 text-xs text-ink-dim">
          <label>Why these values are being supplied
            <input className="ml-2 w-96 max-w-full border border-line px-2 py-1" value={supplyNote}
              onChange={(e) => setSupplyNote(e.target.value)}
              placeholder="e.g. matched by vendor name against the vendor register" />
          </label>
        </li></ul>}
        {batch.issues_truncated && <p className="text-xs">Showing the first 500 issues; resolve these and revalidate.</p>}
        {batch.changes.length > 0 && <AnimatedDisclosure className="my-2" summaryClassName="font-semibold" summary={<>Review {batch.changes.length} superseding record changes</>}><pre className="overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(batch.changes, null, 2)}</pre></AnimatedDisclosure>}
        {batch.status !== "committed" ? <div className="mt-3 flex flex-wrap gap-2">
          <button disabled={busy} className={button} onClick={() => act(async () => showBatch(await intakeApi<ImportBatch>(base + "/imports/" + batch.id + "/mapping", {
            method: "PATCH", body: { expected_version: batch.version, files: draft },
          })), "import") }>Save mappings & revalidate</button>
          <button disabled={busy || batch.status !== "ready_to_commit" || Boolean(draftChanged)} className={primary} onClick={() => act(async () => {
            showBatch(await intakeApi<ImportBatch>(base + "/imports/" + batch.id + "/commit", {
              method: "POST", body: { expected_version: batch.version, idempotency_key: batch.id + ":" + batch.version },
            }));
            setFiles([]); if (fileInput.current) fileInput.current.value = "";
            await Promise.all([refresh(), refreshBundle()]);
            setMessage("Records committed. The originals and this snapshot are saved locally, and the agents can now read these records. No accounting correction was made and no investigation was run.");
          }, "import")}>Confirm & commit records</button>
          <span className="self-center text-[11px] text-ink-dim">Local reviewer · commits validated records, not accounting adjustments</span>
          {/* A commit button that greys out and says nothing is the commonest
              way a working feature reads as a broken one. Both conditions that
              hold it closed are ordinary and recoverable, so both say so. */}
          {renderOutcome("import")}
          {(batch.status !== "ready_to_commit" || draftChanged) &&
            <p className="w-full text-[12.5px] text-amber-800">
              {draftChanged
                ? "Save mappings & revalidate first — the column mapping has unsaved changes, and committing would import the rows as they were last validated rather than as they now read."
                : batch.counts.issues
                  ? `This import cannot be committed while ${batch.counts.issues} issue(s) remain. Each one is listed above with the source line it came from; fix them at source and upload again, or remove the file from this import.`
                  : `This import is ${displayLabel(batch.status).toLowerCase()} and not yet ready to commit. Save mappings & revalidate to re-check it.`}
            </p>}
        </div> : <p className="mt-3 font-mono text-xs text-ink">Saved snapshot: {batch.snapshot_id}</p>}
      </div>}

      <div className="mt-5 space-y-3">
        <AnimatedDisclosure className="border border-line p-3" summaryClassName="font-semibold" summary={<>Committed sources ({coverage?.sources.length || 0})</>}>
          {!coverage?.sources.length && <p className="mt-2 text-xs text-ink-dim">No committed sources yet.</p>}
          {coverage?.sources.map((s) => <button key={s.id} className="mt-2 flex w-full justify-between gap-2 border border-line p-2 text-left text-xs hover:bg-surface-2" onClick={() => act(() => viewSource(s.id))}>
            <span>{s.name}<small className="block text-ink-faint">{ROLES[s.role]}</small></span><span>{s.active ? "Active" : "Historical / duplicate"} ↗</span>
          </button>)}
        </AnimatedDisclosure>
        <AnimatedDisclosure className="border border-line p-3" summaryClassName="font-semibold" summary={<>Evidence requests ({coverage?.requests.length || 0})</>}>
          <p className="my-2 text-[11px] text-ink-dim">Request missing evidence and link supporting files.</p>
          <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); const form = e.currentTarget; const d = new FormData(form);
            act(async () => { setCoverage(await intakeApi<Coverage>(base + "/evidence-requests", { method: "POST", body: { title: d.get("title"), role: d.get("role") } })); form.reset(); }); }}>
            <input required name="title" aria-label="Evidence request" placeholder="What evidence is missing?" className={input} />
            <AnimatedDropdown name="role" defaultValue="chart" aria-label="Requested evidence role" className="w-full" options={ROLE_OPTIONS} />
            <button disabled={busy} className={button}>Add request</button>
          </form>
          {coverage?.requests.map((r) => <div key={r.id} className="mt-3 border border-line p-3">
            <b>{r.title}</b><span className="ml-2 text-xs text-ink-dim">{displayLabel(r.status)}</span>
            <AnimatedDropdown aria-label={`Attach evidence for ${r.title}`} disabled={busy} className="mt-2 w-full" value=""
              placeholder={`Attach a committed ${(ROLES[r.role] ?? r.role).toLowerCase()} source…`}
              options={coverage.sources.filter((s) => s.active && s.role === r.role).map((s) => ({ value: s.id, label: s.name }))}
              onChange={(id) => {
                if (!id) return;
                act(async () => { setCoverage(await intakeApi<Coverage>(base + "/evidence-requests/" + r.id + "/responses", {
                  method: "POST", body: { source_id: id, expected_version: r.version },
                })); setMessage("Evidence linked. A resumption event is saved for the future agent runtime; review is still required."); });
              }} />
            {r.source_id && <button className="mt-1 text-xs text-ink underline" onClick={() => act(() => viewSource(r.source_id!))}>View attached evidence</button>}
          </div>)}
        </AnimatedDisclosure>
      </div>
    </>}

    {creating && <Modal title="Create an institution workspace" close={() => !busy && setCreating(false)}>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); const d = Object.fromEntries(new FormData(e.currentTarget));
        act(async () => { const w = await intakeApi<IntakeWorkspace>("/api/workspaces", { method: "POST", body: d });
          await refreshWorkspaces(); setCreating(false); setWs(w.id); }); }}>
        <label style={fieldLayout} className="text-xs">Institution name<input style={fieldControl} name="name" required maxLength={120} placeholder="Institution name" className={input} /></label>
        {/* A native select submits its first option when nothing is chosen, so each of
            these carries that first option as `defaultValue` and the form posts what it
            always posted. */}
        <label style={fieldLayout} className="text-xs">Entity type<AnimatedDropdown name="entity_type" defaultValue="company" className="w-full" options={["company", "subsidiary", "group"].map((v) => ({ value: v, label: displayLabel(v) }))} /></label>
        <label style={fieldLayout} className="text-xs">Data origin<AnimatedDropdown name="kind" defaultValue="synthetic" className="w-full" options={[{ value: "synthetic", label: "Synthetic records" }, { value: "open_data", label: "Published open data" }, { value: "public", label: "Public documents only" }]} /></label>
        <label style={fieldLayout} className="text-xs">Currency<AnimatedDropdown name="currency" defaultValue="USD" className="w-full" options={["USD", "CAD", "EUR", "GBP"].map((v) => ({ value: v, label: displayLabel(v) }))} /></label>
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
