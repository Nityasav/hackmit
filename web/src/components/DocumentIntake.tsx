"use client";

import { displayLabel } from "@/lib/format";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL, intakeApi, useData } from "@/lib/data";

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
const button = "min-h-11 border border-line px-3 py-2 text-sm disabled:opacity-40";
const input = "w-full border border-line bg-white p-2 text-sm";

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
        <div className="mt-1 grid grid-cols-4 gap-1"><select aria-label={`Record ${index + 1} ${field} status`} className={input} value={value.status} onChange={e => update(index, field, e.target.value === "present" ? { ...value, status: "present" } : { status: e.target.value as Observation["status"], value: null, page: null, start: null, end: null })}>{["present", "missing", "ambiguous", "unreadable"].map(s => <option key={s} value={s}>{displayLabel(s)}</option>)}</select>
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
 * A scan or a photo needs character recognition, which is not installed here,
 * so those are refused at upload rather than guessed at.
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
  const [model, setModel] = useState("");
  const [combine, setCombine] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const refresh = useCallback(async () => { const next = await intakeApi<State>(base); setState(next); return next; }, [base]);
  useEffect(() => { let active = true; intakeApi<State>(base).then(s => { if (active) setState(s); }).catch(e => { if (active) setError(e instanceof Error ? e.message : String(e)); }); return () => { active = false; }; }, [base]);
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
  async function act(action: () => Promise<unknown>, success: string) {
    setBusy(true); setError(""); setMessage("");
    try { await action(); await refresh(); setMessage(success); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  const post = (path: string, body: unknown) => intakeApi(base + path, { method: "POST", body });
  function choose(d: Doc) {
    setSelected(d.id);
    const saved = state?.correction.filter(c => c.document_id === d.id).at(-1);
    const predicted = state?.prediction.filter(p => p.document_id === d.id && p.output).at(-1);
    const blank = { schema_version: state?.schema_version, records: [Object.fromEntries((state?.schemas[d.role] || []).map(k => [k, { status: "missing", value: null, page: null, start: null, end: null }]))] };
    setEditor(JSON.stringify(saved?.output || predicted?.output || blank, null, 2));
    setTranscript(JSON.stringify(d.pages.map(p => p.text), null, 2));
    setGroup(saved?.group || ""); setConsent(saved?.training_authorized || false); setIncludeRecords(false); setNote(""); setAuthorization("");
  }
  const availableModels = state?.model.filter(m => !state.retirement.some(r => r.model_id === m.id)) || [];
  return <div className="space-y-4">
    {error && <p role="alert" className="border border-line bg-red-50 p-3 text-[13px] text-accent-bad">{error}</p>}
    {message && <p role="status" className="border border-line bg-surface-2 p-3 text-[13px]">{message}</p>}
    {!state ? <p className="text-[13px] text-ink-dim">Opening this workspace&rsquo;s documents…</p> : <>
      <section className="border border-line p-5"><h3 className="text-[15px] font-semibold tracking-tight">Add a document</h3><p className="my-2 max-w-prose text-[13px] leading-relaxed text-ink-dim">PDF only, up to 10 MB and 20 pages. The text is read straight out of the file, so a PDF you can select text in will work. A scan or a photo of a document needs character recognition, which is not installed on this server, and will be rejected rather than guessed at.</p>
        <p className="mb-4 text-[13px] text-ink-dim">For CSV files, <a href="#source-records" className="font-semibold text-ink underline">use Add records above</a> to preview columns and import rows.</p>
        {READERS[role] ? <p className="mt-2 text-[12.5px] text-ink-dim">Once you have checked it and staged it, {READERS[role]} can read this as evidence and cite it.</p> : <p className="mt-2 text-[12.5px] text-amber-800">No agent reads this kind yet. It will be preserved, citable by a person, and invisible to every agent — pick the kind that matches what the document actually is.</p>}
        <div className="grid items-end gap-4 text-[13px] sm:grid-cols-2"><label>Kind of document<select className={input} value={role} onChange={e => setRole(e.target.value)}>{Object.keys(state.schemas).map(r => <option key={r} value={r}>{displayLabel(r)}</option>)}</select></label>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
            <span>Choose document</span>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className={`${button} font-semibold`} style={{ background: "#09090b", color: "white", border: "1px solid #09090b", padding: "10px 16px" }} disabled={busy} onClick={() => fileInput.current?.click()}>Choose document</button>
              <span className="min-w-0 break-all text-xs text-ink-dim" aria-live="polite">{file?.name || "No document selected"}</span>
            </div>
            <input ref={fileInput} style={{ display: "none" }} aria-label="Select document file" type="file" accept=".pdf" disabled={busy} onChange={e => setFile(e.target.files?.[0] || null)} />
          </div>
          <label>New file or a replacement<select className={input} value={replaces} onChange={e => setReplaces(e.target.value)}><option value="">New document</option>{state.documents.filter(d => d.role === role).map(d => <option key={d.id} value={d.id}>Replaces {d.name} v{d.version}</option>)}</select></label>
          <button className={button} disabled={busy || !file} onClick={() => act(async () => { const form = new FormData(); form.append("file", file!); form.append("role", role); if (replaces) form.append("replaces_id", replaces); const d = await intakeApi<Doc>(base + "/documents", { method: "POST", body: form }); choose(d); }, "Document saved and read. Check any warnings before using the text.")}>Upload &amp; read</button></div>
        <div className="mt-3 flex flex-wrap gap-2">{state.documents.map(d => <button className={button} key={d.id} onClick={() => choose(d)}>{d.name} · {d.role} · v{d.version}</button>)}</div>
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
            "Combined into one import. Scroll up to the import, check it, then commit it.")}>
          {combine.length < 2 ? "Select at least two" : `Combine ${combine.length} into one import`}
        </button>
      </section>}
      {doc && <section className="border border-line p-5"><h3 className="text-[15px] font-semibold tracking-tight">Check {doc.name} against its pages</h3><p className="break-all font-mono text-[11px] text-ink-faint">SHA-256 {doc.sha256}</p><a className="text-[13px] underline" href={`${API_URL}${base}/documents/${doc.id}/original`}>Download the preserved original</a>
        <div className="my-3 flex flex-wrap gap-2"><select aria-label="Extraction model" className={button} value={model} onChange={e => setModel(e.target.value)}><option value="">Active model {state.active ? `(${state.active.model_id})` : "— none configured"}</option>{availableModels.map(m => <option value={m.id} key={m.id}>{m.name}</option>)}</select>
          {/* The local model takes roughly half a minute per document, so this
              one request opts out of the client's short default deadline. At 20s
              the browser gave up on work the model went on to finish, and the
              screen simply stayed blank. */}
          <button className={button} disabled={busy || (!model && !state.active)} onClick={() => act(async () => { const p = await intakeApi<{ output: Output | null; error: string | null }>(base + "/predict", { method: "POST", body: { document_id: doc.id, model_id: model || null }, timeout: 180_000 }); if (p.error) throw new Error(p.error); setEditor(JSON.stringify(p.output, null, 2)); }, "A first pass is ready for you to check. Nothing has been accepted.")}>Read it with the configured model</button></div>
        <div className="grid gap-4 lg:grid-cols-2"><div className="max-h-[650px] overflow-auto">{doc.pages.map(p => <article className="mb-4 border border-line p-3" key={p.page}><h4 className="text-[13px] font-semibold">Page {p.page} · {p.method}</h4>{p.warnings.map(w => <p className="text-[12px] text-amber-800" key={w}>{w}</p>)}{![".txt", ".md"].includes(doc.suffix) && <a target="_blank" rel="noreferrer" className="text-[13px] underline" href={`${API_URL}${base}/documents/${doc.id}/pages/${p.page}`}>View the original page image</a>}<pre className="whitespace-pre-wrap text-xs">{p.text}</pre></article>)}</div>
          <div><p className="mb-2 text-[13px]">Check each value against the source. Citation offsets start at zero; the end position is excluded.</p><FieldEditor text={editor} doc={doc} fields={state.schemas[doc.role]} change={setEditor} /><details className="mt-3"><summary className="text-[13px]">Edit the raw extraction JSON</summary><label>Extraction JSON<textarea aria-label="Extraction JSON" spellCheck={false} className={`${input} h-96 font-mono text-xs`} value={editor} onChange={e => setEditor(e.target.value)} /></label></details></div></div>
        <details className="my-3"><summary className="cursor-pointer text-[13px]">The page text itself is wrong</summary><p className="my-2 text-[13px]">Compare each page image first. Saving this creates a new text revision and invalidates the values already placed against the old one. The original file is never overwritten.</p><textarea aria-label="Page transcription JSON array" className={`${input} h-40 font-mono`} value={transcript} onChange={e => setTranscript(e.target.value)} /><button disabled={busy || !note.trim()} className={button} onClick={() => act(() => post(`/documents/${doc.id}/transcription`, { expected_text_sha256: doc.text_sha256, pages: JSON.parse(transcript), note }), "New text revision saved. Re-open the document and check every value again.")}>Save a corrected transcription</button></details>
        <div className="grid gap-3 text-[13px] md:grid-cols-2"><label>Institution, supplier or template<input className={input} value={group} onChange={e => setGroup(e.target.value)} placeholder="Keeps related documents together" /></label><label>Review note<input className={input} value={note} onChange={e => setNote(e.target.value)} /></label><label>Data authorization<input className={input} value={authorization} onChange={e => setAuthorization(e.target.value)} placeholder="Synthetic data I own, or the restriction that applies" /></label><label className="flex items-center gap-2"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />I am allowed to keep this document for evaluation</label></div>
        <div className="mt-3 flex flex-wrap items-center gap-2"><button className={button} disabled={busy || !group.trim() || !note.trim() || !authorization.trim()} onClick={() => act(() => post("/corrections", { document_id: doc.id, prediction_id: prediction?.id || null, expected_previous: correction?.id || null, text_sha256: doc.text_sha256, output: JSON.parse(editor), group, note, training_authorized: consent, authorization_note: authorization }), "Accepted. Nothing has been posted to the books.")}>Accept what I checked</button>
          <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={includeRecords} onChange={e => setIncludeRecords(e.target.checked)} />Stage new records for import. Leave unchecked if these records are already imported.</label>
          <button className={button} disabled={busy || !correction || correction.text_sha256 !== doc.text_sha256} onClick={() => act(() => post("/stage", { correction_id: correction!.id, include_records: includeRecords }), "Staged for import. Scroll up to the import, check it, then commit it.")}>Stage it for import</button></div>
      </section>}
    </>}
    {busy && <p role="status" className="text-[13px]">Working… keep this open. Reading a document with the model takes about half a minute. The original is safe; do not repeat the action.</p>}
  </div>;
}
