"use client";

import { displayLabel } from "@/lib/format";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatedDropdown } from "@/components/ui/animated-dropdown";
import { FileCard } from "@/components/ui/file-card-collections";
import { fileFormat } from "@/lib/fileFormat";
import { API_URL, intakeApi, useData } from "@/lib/data";
import { sampleInvoicePdf } from "@/lib/samplePdf";
import { periodDay } from "@/lib/starterPacks";

type Observation = { status: "present" | "missing" | "ambiguous" | "unreadable"; value: string | null; page: number | null; start: number | null; end: number | null };
type Output = { schema_version: string; records: Record<string, Observation>[] };
type Doc = { id: string; name: string; role: string; sha256: string; text_sha256: string; suffix: string; version: number; lineage_id: string; pages: { page: number; text: string; method: string; warnings: string[] }[] };
type Model = { id: string; name: string; note: string };
type Correction = { id: string; document_id: string; output: Output; group: string; training_authorized: boolean; text_sha256: string };
// Only the parts of the extraction service this screen renders. The service
// also carries a model-evaluation lifecycle; none of it belongs on Books, so
// none of it is declared here.
type State = { documents: Doc[]; model: Model[]; prediction: { id: string; document_id: string; output: Output | null; error: string | null }[];
  correction: Correction[]; retirement: { model_id: string }[];
  active: { model_id: string; version: number } | null; schemas: Record<string, string[]>; schema_version: string };
//: Where in this screen an action was taken, so its outcome can be reported
//: beside the control rather than only at the top of the page.
type Scope = "top" | "review" | "combine";

const button = "min-h-11 border border-line px-3 py-2 text-sm disabled:opacity-40";
const input = "w-full border border-line bg-white p-2 text-sm";
const uploadField: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 6, minWidth: 0 };
const uploadControl: React.CSSProperties = { boxSizing: "border-box", height: 40, minHeight: 40, width: "100%", minWidth: 0, border: "1px solid #d4d4d8", padding: "8px 12px", outlineOffset: -2 };

/**
 * Which agents may read a document of each kind, from the `roles` on their
 * specs in api/app/agents/registry.py.
 *
 * Getting this wrong is silent and expensive: a document staged under a kind
 * no agent reads is preserved, hashed and citable by a person, and invisible
 * to every agent — so the work of extracting and checking it buys nothing.
 * The kinds absent here have no reader at all, which is worth saying on the
 * screen where the choice is made rather than leaving someone to discover it.
 */
const READERS: Record<string, string> = {
  invoice: "Accounts Payable and Audit",
  service: "Accounts Payable and Audit",
  policy: "Accounts Payable and Controls Testing",
  grants: "Accruals & Adjustments and Audit, as a funding contract",
  budget: "Budgeting and Variance Analysis",
};

function FieldEditor({ text, doc, fields, change }: { text: string; doc: Doc; fields: string[]; change: (text: string) => void }) {
  let output: Output;
  try {
    output = JSON.parse(text);
    if (!Array.isArray(output.records) || !output.records.every(r => r && typeof r === "object" && Object.values(r).every(v => v && typeof v === "object" && "status" in v))) return null;
  } catch { return <p className="text-sm text-amber-800">Fix the advanced JSON syntax to restore the field editor.</p>; }
  function update(index: number, field: string, next: Observation) {
    const records = output.records.map((r, i) => i === index ? { ...r, [field]: next } : r);
    change(JSON.stringify({ ...output, records }, null, 2));
  }
  function locate(value: string): Observation {
    const matches: { page: number; start: number; end: number }[] = [];
    if (value) for (const p of doc.pages) {
      let at = p.text.indexOf(value);
      while (at >= 0 && matches.length < 2) {
        const start = Array.from(p.text.slice(0, at)).length;
        matches.push({ page: p.page, start, end: start + Array.from(value).length });
        at = p.text.indexOf(value, at + Math.max(1, value.length));
      }
    }
    return { status: value ? "present" : "missing", value: value || null, page: null, start: null, end: null, ...(matches.length === 1 ? matches[0] : {}) };
  }
  return <div className="space-y-3"><p className="text-sm">Copy a value from the page text. A unique match fills its citation automatically. Repeated values require you to choose the exact page and character span.</p>
    {output.records.map((record, index) => <details key={index} open={index === 0} className="border border-line p-2"><summary>Record {index + 1}</summary><div className="max-h-[500px] overflow-auto">{fields.map(field => {
      const value = record[field] || { status: "missing", value: null, page: null, start: null, end: null };
      return <div className="my-3 border-b border-line pb-2" key={field}><label className="text-sm font-semibold">{displayLabel(field)}<input aria-label={`Record ${index + 1} ${field} value`} className={input} value={value.value || ""} onChange={e => update(index, field, locate(e.target.value))} /></label>
        <div className="mt-1 grid grid-cols-4 gap-1"><AnimatedDropdown aria-label={`Record ${index + 1} ${field} status`} className="w-full" options={["present", "missing", "ambiguous", "unreadable"].map(s => ({ value: s, label: displayLabel(s) }))} value={value.status} onChange={next => update(index, field, next === "present" ? { ...value, status: "present" } : { status: next as Observation["status"], value: null, page: null, start: null, end: null })} />
          {(["page", "start", "end"] as const).map(locator => <label key={locator} className="text-xs">{displayLabel(locator)}<input aria-label={`Record ${index + 1} ${field} ${locator}`} type="number" min={locator === "page" ? 1 : 0} disabled={value.status !== "present"} className={input} value={value[locator] ?? ""} onChange={e => update(index, field, { ...value, [locator]: e.target.value === "" ? null : Number(e.target.value) })} /></label>)}</div>
        {value.status === "present" && value.page === null && <p className="text-xs text-amber-800">No unique source match. Check the value and specify the correct citation before approval.</p>}
      </div>;
    })}</div></details>)}
    <button className={button} type="button" onClick={() => change(JSON.stringify({ ...output, records: [...output.records, Object.fromEntries(fields.map(f => [f, { status: "missing", value: null, page: null, start: null, end: null }]))] }, null, 2))}>Add another source record</button>
  </div>;
}

/**
 * Getting a PDF into the books.
 *
 * A scanned PDF carrying no text layer is read by character recognition
 * instead, and the page records that it was, so a reviewer checking the values
 * knows the text is a reading of the page rather than the page itself.
 *
 * A document is preserved byte for byte, read into page text, and then a person
 * checks every extracted value against the page it came from before any of it
 * is staged for import. Nothing here is committed: staging hands the records to
 * the import on Books, which is still where a person commits them.
 */
export function DocumentIntake() {
  const { ws } = useData();
  if (!ws) {
    return <p className="border border-line bg-surface p-5 text-[13px] text-ink-dim">Create an institution before uploading documents.</p>;
  }
  return <Lab key={ws} ws={ws} />;
}

function Lab({ ws }: { ws: string }) {
  const base = `/api/workspaces/${ws}/extraction`;
  // Only for dating the sample invoice: staged extraction is validated against
  // the review period like any other record, so a sample dated outside it would
  // be refused at import.
  const [period, setPeriod] = useState<{ start: string; end: string } | null>(null);
  const [state, setState] = useState<State | null>(null);
  const [selected, setSelected] = useState("");
  const [role, setRole] = useState("invoice");
  const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [replaces, setReplaces] = useState("");
  const [editor, setEditor] = useState("");
  const [transcript, setTranscript] = useState("");
  const [group, setGroup] = useState("");
  const [consent, setConsent] = useState(false);
  const [includeRecords, setIncludeRecords] = useState(false);
  const [note, setNote] = useState("");
  const [authorization, setAuthorization] = useState("");
  const [selectedModel, setModel] = useState("");
  const [combine, setCombine] = useState<string[]>([]);
  const [reshaped, setReshaped] = useState(false);
  const [scope, setScope] = useState<Scope>("top");
  const [errorScope, setErrorScope] = useState<Scope>("top");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const refresh = useCallback(async () => { const next = await intakeApi<State>(base); setState(next); return next; }, [base]);
  useEffect(() => { let active = true; intakeApi<State>(base).then(s => { if (active) setState(s); }).catch(e => { if (active) setError(e instanceof Error ? e.message : String(e)); }); return () => { active = false; }; }, [base]);
  // Preselect when there is exactly one model to choose. The picker opened on
  // "Active model — none configured", which is not a model, so the read button
  // stayed disabled until someone noticed they had to choose — and a disabled
  // button reads as a broken feature. With two or more, the choice is real and
  // is left to the person.
  const onlyModel = state?.model.filter(m => !state.retirement.some(r => r.model_id === m.id)) || [];
  const model = selectedModel || (!state?.active && onlyModel.length === 1 ? onlyModel[0].id : "");
  useEffect(() => { let active = true; intakeApi<{ workspace: { start: string; end: string } }>(`/api/workspaces/${ws}/coverage`).then(c => { if (active) setPeriod(c.workspace); }).catch(() => { /* The sample invoice falls back to today's date; the lab itself does not need the period. */ }); return () => { active = false; }; }, [ws]);
  const doc = state?.documents.find(d => d.id === selected);
  const correction = state?.correction.filter(c => c.document_id === selected).at(-1);
  const prediction = state?.prediction.filter(p => p.document_id === selected).at(-1);
  // The newest correction per document, kept only where it still matches the
  // document's current page text — a superseded one describes text that has
  // since been re-read, and the API refuses it. Restricted to the kind now
  // selected, because each kind extracts different columns and one register
  // cannot hold two of them.
  const sameKind = (state?.documents || []).filter(d => d.role === role);
  const readyToCombine = Object.values(
    (state?.correction || []).reduce<Record<string, Correction>>((acc, c) => ({ ...acc, [c.document_id]: c }), {}),
  ).filter(c => {
    const named = state?.documents.find(d => d.id === c.document_id);
    return !!named && named.role === role && named.text_sha256 === c.text_sha256;
  });
  /**
   * Run one action and report where it was taken.
   *
   * `where` matters: the outcome used to render once, near the top of a long
   * page, while the button that caused it sat far below. A person clicked
   * Accept, it succeeded, and nothing they could see changed — which is how a
   * working control comes to look broken.
   */
  async function act(action: () => Promise<unknown>, success: string, where: Scope = "top") {
    setBusy(true); setError(""); setErrorScope(where); setMessage(""); setScope(where);
    try { await action(); await refresh(); setMessage(success); setScope(where); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); setErrorScope(where); }
    finally { setBusy(false); }
  }

  /** A confirmation rendered where the action was taken, stated plainly. */
  function renderDone(at: Scope) {
    if (!message || scope !== at) return null;
    return <p role="status" className="mt-2 border-l-4 border-green-700 bg-green-50 p-3 text-[13px] text-green-900">
      <b>Done.</b> {message}
    </p>;
  }
  const post = (path: string, body: unknown) => intakeApi(base + path, { method: "POST", body });
  // A field marked present must carry an exact page span: the API rejects the
  // whole submission otherwise, and the rejection used to arrive as a wall of
  // validator output at the top of a long page, far from the button that
  // caused it. Naming the fields here stops the submission being made at all.
  const uncited: string[] = (() => {
    try {
      const parsed = JSON.parse(editor) as Output;
      return (parsed.records || []).flatMap((record, index) =>
        Object.entries(record)
          .filter(([, v]) => v && v.status === "present" &&
            (v.page === null || v.start === null || v.end === null))
          .map(([field]) => `record ${index + 1} · ${displayLabel(field)}`));
    } catch { return ["the advanced JSON is not valid"]; }
  })();
  /**
   * A stored record, reshaped to the field set this document type has now.
   *
   * The fields a document type extracts are not frozen: the agent rework
   * changed the vocabulary, and predictions saved before it kept the shape
   * they were made with — school-era `student_ref` and `fund` where the books
   * now want `customer_id` and `entity`. Loading one verbatim produced an
   * editor whose every submission the API refused, with nothing on screen
   * explaining why.
   *
   * Values for fields that still exist are kept, because a person checked
   * them. Fields that no longer exist are dropped, and fields that did not
   * exist then are added as abstentions — never as guesses.
   */
  function reshape(output: Output | null | undefined, fields: string[]): Output | undefined {
    if (!output?.records?.length) return undefined;
    return {
      schema_version: state?.schema_version || output.schema_version,
      records: output.records.map(record => Object.fromEntries(fields.map(field => [
        field,
        record[field] || { status: "missing", value: null, page: null, start: null, end: null },
      ])) as Record<string, Observation>),
    };
  }

  const sampleDate = period ? periodDay(period, 10) : new Date().toISOString().slice(0, 10);
  function choose(d: Doc) {
    setSelected(d.id);
    const fields = state?.schemas[d.role] || [];
    const saved = state?.correction.filter(c => c.document_id === d.id).at(-1);
    const predicted = state?.prediction.filter(p => p.document_id === d.id && p.output).at(-1);
    const blank: Output = { schema_version: state?.schema_version || "", records: [Object.fromEntries(fields.map(k => [k, { status: "missing", value: null, page: null, start: null, end: null }])) as Record<string, Observation>] };
    const loaded = reshape(saved?.output, fields) || reshape(predicted?.output, fields) || blank;
    const source = saved?.output || predicted?.output;
    setReshaped(!!source && JSON.stringify(Object.keys(source.records[0] || {}).sort()) !== JSON.stringify([...fields].sort()));
    setEditor(JSON.stringify(loaded, null, 2));
    setTranscript(JSON.stringify(d.pages.map(p => p.text), null, 2));
    setGroup(saved?.group || ""); setConsent(saved?.training_authorized || false); setIncludeRecords(false); setNote(""); setAuthorization("");
  }
  const availableModels = state?.model.filter(m => !state.retirement.some(r => r.model_id === m.id)) || [];
  return <div className="space-y-4">
    {error && <p role="alert" className="border border-line bg-red-50 p-3 text-[13px] text-accent-bad">{error}</p>}
    {message && scope === "top" && <p role="status" className="border border-line bg-surface-2 p-3 text-[13px]">{message}</p>}
    {!state ? <p className="text-[13px] text-ink-dim">Opening this workspace&rsquo;s documents…</p> : <>
      <section className="border border-line p-5"><h3 className="text-[15px] font-semibold tracking-tight">Add a document</h3><p className="mt-2 text-[13px] leading-relaxed text-ink-dim">Text-based PDF · Up to 10 MB and 20 pages. Scans and photos aren’t supported.</p>
        <p className="mt-1 text-[13px] text-ink-dim">For CSV files, <a href="#source-records" className="font-semibold text-ink underline">use Add records above</a> to preview columns and import rows.</p>
        {READERS[role] ? <p className="mt-1 text-[12.5px] text-ink-dim">After review and staging: available to {READERS[role]}.</p> : <p className="mt-1 text-[12.5px] text-amber-800">Saved as reference only; no agent uses this document type yet.</p>}
        <div className="mt-4 grid items-end gap-4 text-[13px] sm:grid-cols-2"><label style={uploadField}>Document type<AnimatedDropdown className="w-full" options={Object.keys(state.schemas).map(r => ({ value: r, label: displayLabel(r) }))} value={role} onChange={setRole} /></label>
          <div style={uploadField}>
            <span>PDF file</span>
            <div className="flex min-w-0 items-center gap-3">
              <button type="button" className="shrink-0 text-sm font-semibold disabled:opacity-40" style={{ height: 40, background: "#09090b", color: "white", border: "1px solid #09090b", padding: "8px 12px" }} disabled={busy} onClick={() => fileInput.current?.click()}>Choose document</button>
              {/* Not uploaded yet, so the kind is read from the name — the only thing
                  known about the file before the server has seen it. */}
              {file && <span className="shrink-0 pr-2"><FileCard formatFile={fileFormat(file.name)} /></span>}
              <span className="min-w-0 truncate text-xs text-ink-dim" title={file?.name} aria-live="polite">{file?.name || "No document selected"}</span>
            </div>
            <input ref={fileInput} style={{ display: "none" }} aria-label="Select document file" type="file" accept=".pdf" disabled={busy} onChange={e => setFile(e.target.files?.[0] || null)} />
          </div>
          <label style={uploadField}>Save as<AnimatedDropdown className="w-full" placeholder="New document" options={state.documents.filter(d => d.role === role).map(d => ({ value: d.id, label: `Replaces ${d.name} v${d.version}` }))} value={replaces} onChange={setReplaces} /></label>
          <button style={uploadControl} className={button} disabled={busy || !file} onClick={() => act(async () => { const form = new FormData(); form.append("file", file!); form.append("role", role); if (replaces) form.append("replaces_id", replaces); const d = await intakeApi<Doc>(base + "/documents", { method: "POST", body: form }); choose(d); }, "Document saved and read. Check any warnings before using the text.")}>Upload &amp; read</button></div>
        {/* Nothing to scan yet: a fictional supplier invoice, the same purchase
            INV-003 of the full-close starter pack records. */}
        <div className="mt-3 flex flex-wrap items-center gap-3 text-[13px]">
          <button className={button} disabled={busy} onClick={() => { setFile(sampleInvoicePdf(sampleDate)); setError(""); setMessage("Sample invoice ready. Choose its kind of document, then upload and read it."); }}>Use a sample invoice (PDF)</button>
        </div>
        {/* The card face is drawn from the extension and carries no information
            the text below it does not also say, so it is aria-hidden and the
            name, kind and version remain the accessible label. */}
        <div className="mt-6 border-t border-line pt-5">
          <h4 className="text-[13px] font-semibold tracking-tight">Documents in this workspace</h4>
          {state.documents.length === 0
            ? <p className="mt-2 text-[13px] text-ink-dim">None yet. Choose a document above, or start from the sample invoice.</p>
            : <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-6">{state.documents.map(d => <li key={d.id}>
                <button type="button" onClick={() => choose(d)} aria-pressed={d.id === selected} title={d.name}
                  className={`flex w-28 flex-col items-center gap-2 rounded-md border p-3 text-center transition-colors hover:bg-surface-2 ${d.id === selected ? "border-ink bg-surface-2" : "border-transparent"}`}>
                  <FileCard formatFile={fileFormat(d.suffix || d.name)} />
                  <span className="mt-1 w-full truncate text-[12px] font-medium text-ink">{d.name}</span>
                  <span className="text-[11px] text-ink-dim">{displayLabel(d.role)} · v{d.version}</span>
                </button>
              </li>)}</ul>}
        </div>
      </section>
      {sameKind.length > 1 && <section className="border border-line p-5">
        <h3 className="text-[15px] font-semibold tracking-tight">Combine several into one register</h3>
        <p className="my-2 max-w-prose text-[13px] leading-relaxed text-ink-dim">
          Staging one at a time makes one import per document. These have all been checked and are
          the same kind, so their rows can go into a single spreadsheet you review and commit once.
          Each document still keeps its own evidence file, so every value stays traceable to the
          page it came from.
        </p>
        <ul className="my-3 space-y-1">{sameKind.map(d => {
          const ready = readyToCombine.find(c => c.document_id === d.id);
          return <li key={d.id} className="text-[13px]"><label className={`flex items-center gap-2 ${ready ? "" : "text-ink-dim"}`}>
            <input type="checkbox" checked={!!ready && combine.includes(ready.id)} disabled={busy || !ready}
              onChange={e => ready && setCombine(prev => e.target.checked ? [...prev, ready.id] : prev.filter(x => x !== ready.id))} />
            {d.name}
            {!ready && <span className="text-[12px]">· check its values and accept them first</span>}
          </label></li>;
        })}</ul>
        <button className={button} disabled={busy || combine.length < 2}
          onClick={() => act(async () => { await post("/stage-set", { correction_ids: combine, include_records: true }); setCombine([]); },
            "One import now holds every row from the documents you selected, plus each document\u2019s own evidence file. It is waiting under \u201cAdd records\u201d at the top of this page. Review it there and commit it; until you do, none of this is in the books.", "combine")}>
          {combine.length < 2 ? "Select at least two" : `Combine ${combine.length} into one import`}
        </button>
        {renderDone("combine")}
      </section>}
      {doc && <section className="border border-line p-5"><h3 className="text-[15px] font-semibold tracking-tight">Check {doc.name} against its pages</h3><p className="break-all font-mono text-[11px] text-ink-faint">SHA-256 {doc.sha256}</p><a className="text-[13px] underline" href={`${API_URL}${base}/documents/${doc.id}/original`}>Download the preserved original</a>
        {!state.model.length && <p className="my-2 max-w-prose text-[12.5px] text-amber-800">
          No extraction model is registered for this company, so the values cannot be read
          automatically — a model is registered per company, and a new one starts without. You can
          still check every value against the pages yourself below, which is the same review a
          model&rsquo;s output would need anyway.
        </p>}
        <div className="my-3 flex flex-wrap gap-2"><AnimatedDropdown aria-label="Extraction model" buttonClassName="min-h-11" placeholder={`Active model ${state.active ? `(${state.active.model_id})` : "— none configured"}`} options={availableModels.map(m => ({ value: m.id, label: m.name }))} value={model} onChange={setModel} />
          {/* The local model takes roughly half a minute per document, so this
              one request opts out of the client's short default deadline. At 20s
              the browser gave up on work the model went on to finish, and the
              screen simply stayed blank. */}
          <button className={button} disabled={busy || (!model && !state.active)} onClick={() => act(async () => { const p = await intakeApi<{ output: Output | null; error: string | null }>(base + "/predict", { method: "POST", body: { document_id: doc.id, model_id: model || null }, timeout: 180_000 }); if (p.error) throw new Error(p.error); setEditor(JSON.stringify(p.output, null, 2)); }, "A first pass is ready for you to check. Nothing has been accepted.")}>Read it with the configured model</button></div>
        <div className="grid gap-4 lg:grid-cols-2"><div className="max-h-[650px] overflow-auto">{doc.pages.map(p => <article className="mb-4 border border-line p-3" key={p.page}><h4 className="text-[13px] font-semibold">Page {p.page} · {p.method}</h4>{p.warnings.map(w => <p className="text-[12px] text-amber-800" key={w}>{w}</p>)}{![".txt", ".md"].includes(doc.suffix) && <a target="_blank" rel="noreferrer" className="text-[13px] underline" href={`${API_URL}${base}/documents/${doc.id}/pages/${p.page}`}>View the original page image</a>}<pre className="whitespace-pre-wrap text-xs">{p.text}</pre></article>)}</div>
          <div><p className="mb-2 text-[13px]">Check each value against the source. Citation offsets start at zero; the end position is excluded.</p><FieldEditor text={editor} doc={doc} fields={state.schemas[doc.role]} change={setEditor} /><details className="mt-3"><summary className="text-[13px]">Edit the raw extraction JSON</summary><label>Extraction JSON<textarea aria-label="Extraction JSON" spellCheck={false} className={`${input} h-96 font-mono text-xs`} value={editor} onChange={e => setEditor(e.target.value)} /></label></details></div></div>
        <details className="my-3"><summary className="cursor-pointer text-[13px]">The page text itself is wrong</summary><p className="my-2 text-[13px]">Compare each page image first. Saving this creates a new text revision and invalidates the values already placed against the old one. The original file is never overwritten.</p><textarea aria-label="Page transcription JSON array" className={`${input} h-40 font-mono`} value={transcript} onChange={e => setTranscript(e.target.value)} /><button disabled={busy || !note.trim()} className={button} onClick={() => act(() => post(`/documents/${doc.id}/transcription`, { expected_text_sha256: doc.text_sha256, pages: JSON.parse(transcript), note }), "New text revision saved. Re-open the document and check every value again.")}>Save a corrected transcription</button></details>
        <div className="grid gap-3 text-[13px] md:grid-cols-2"><label>Institution, supplier or template <span className="text-amber-800">(required)</span><input className={input} value={group} onChange={e => setGroup(e.target.value)} placeholder="Keeps related documents together" /></label><label>Review note <span className="text-amber-800">(required)</span><input className={input} value={note} onChange={e => setNote(e.target.value)} /></label><label>Data authorization <span className="text-amber-800">(required)</span><input className={input} value={authorization} onChange={e => setAuthorization(e.target.value)} placeholder="Synthetic data I own, or the restriction that applies" /></label><label className="flex items-center gap-2"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />I am allowed to keep this document for evaluation</label></div>
        <div className="mt-3 flex flex-wrap items-center gap-2"><button className={button} disabled={busy || !group.trim() || !note.trim() || !authorization.trim() || uncited.length > 0} onClick={() => act(() => post("/corrections", { document_id: doc.id, prediction_id: prediction?.id || null, expected_previous: correction?.id || null, text_sha256: doc.text_sha256, output: JSON.parse(editor), group, note, training_authorized: consent, authorization_note: authorization }), "Your checked values are saved against this document, with every citation you confirmed. Nothing has been posted to the books yet — use \u201cStage it for import\u201d next to send them to an import.", "review")}>Accept what I checked</button>
          <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={includeRecords} onChange={e => setIncludeRecords(e.target.checked)} />Stage new records for import. Leave unchecked if these records are already imported.</label>
          <button className={button} disabled={busy || !correction || correction.text_sha256 !== doc.text_sha256} onClick={() => act(() => post("/stage", { correction_id: correction!.id, include_records: includeRecords }), "An import has been created and is waiting under \u201cAdd records\u201d at the top of this page, where a banner offers to open it. Review it there and commit it; until you do, none of this is in the books.", "review")}>Stage it for import</button></div>
        {/* A disabled control that does not say why reads as a broken one. */}
        {reshaped &&
          <p className="mt-2 text-[12.5px] text-amber-800">
            These values were saved when this document type extracted a different set of fields,
            so they have been fitted to the current one: anything still extracted was kept, fields
            that no longer exist were dropped, and new ones start blank rather than guessed. Check
            them against the pages before accepting.
          </p>}
        {uncited.length > 0 &&
          <p className="mt-2 text-[12.5px] text-amber-800">
            These are marked present but have no exact page span, which the books will not accept:{" "}
            {uncited.join("; ")}. Either set the page and character positions, or change the status
            to ambiguous or unreadable — a value nobody can point at on the page is not evidence.
          </p>}
        {renderDone("review")}
        {error && errorScope === "review" && <p role="alert" className="mt-2 border border-red-300 bg-red-50 p-2 text-[12.5px] text-red-800">{error}</p>}
        {(!group.trim() || !note.trim() || !authorization.trim()) &&
          <p className="mt-2 text-[12.5px] text-amber-800">Before you can accept: fill in{" "}
            {[!group.trim() && "the institution, supplier or template", !note.trim() && "a review note",
              !authorization.trim() && "what authorizes you to hold this document"].filter(Boolean).join(", ")}.
          </p>}
        {!correction &&
          <p className="mt-1 text-[12.5px] text-ink-dim">Staging becomes available once you have accepted the values above. Nothing is imported until you commit the staged batch on Books.</p>}
        {correction && correction.text_sha256 !== doc.text_sha256 &&
          <p className="mt-1 text-[12.5px] text-amber-800">The page text was re-read after these values were accepted, so they describe text that has changed. Check them against the pages again and accept once more before staging.</p>}
      </section>}
    </>}
    {busy && <p role="status" className="text-[13px]">Working… keep this open. Reading a document with the model takes about half a minute. The original is safe; do not repeat the action.</p>}
  </div>;
}
