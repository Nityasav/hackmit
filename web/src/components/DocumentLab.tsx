"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { API_URL, intakeApi, useData } from "@/lib/data";

type Observation = { status: "present" | "missing" | "ambiguous" | "unreadable"; value: string | null; page: number | null; start: number | null; end: number | null };
type Output = { schema_version: string; records: Record<string, Observation>[] };
type Doc = { id: string; name: string; role: string; sha256: string; text_sha256: string; suffix: string; version: number; lineage_id: string; pages: { page: number; text: string; method: string; warnings: string[] }[] };
type Model = { id: string; name: string; note: string };
type Correction = { id: string; document_id: string; output: Output; group: string; training_authorized: boolean; text_sha256: string };
type Evaluation = { id: string; passed: boolean; failures: string[]; candidate_id: string; baseline_id: string; runs: Record<string, { metrics: Record<string, unknown> }> };
type State = { documents: Doc[]; model: Model[]; prediction: { id: string; document_id: string; output: Output | null; error: string | null }[];
  benchmark_job: { id: string; status: string; error?: string; evaluation_id?: string }[];
  correction: Correction[]; dataset: { id: string; name: string; purpose: string; sha256: string; groups: string[] }[];
  evaluation: Evaluation[]; release: { id: string; model_id: string; version: number }[]; retirement: { model_id: string }[];
  active: { model_id: string; version: number } | null; schemas: Record<string, string[]>; schema_version: string; policy: Record<string, number> };
const button = "border border-line px-3 py-2 text-sm disabled:opacity-40";
const input = "w-full border border-line bg-white p-2 text-sm";

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
      return <div className="my-3 border-b border-line pb-2" key={field}><label className="text-sm font-semibold">{field.replaceAll("_", " ")}<input aria-label={`Record ${index + 1} ${field} value`} className={input} value={value.value || ""} onChange={e => update(index, field, locate(e.target.value))} /></label>
        <div className="mt-1 grid grid-cols-4 gap-1"><select aria-label={`Record ${index + 1} ${field} status`} className={input} value={value.status} onChange={e => update(index, field, e.target.value === "present" ? { ...value, status: "present" } : { status: e.target.value as Observation["status"], value: null, page: null, start: null, end: null })}>{["present", "missing", "ambiguous", "unreadable"].map(s => <option key={s}>{s}</option>)}</select>
          {(["page", "start", "end"] as const).map(locator => <label key={locator} className="text-xs">{locator}<input aria-label={`Record ${index + 1} ${field} ${locator}`} type="number" min={locator === "page" ? 1 : 0} disabled={value.status !== "present"} className={input} value={value[locator] ?? ""} onChange={e => update(index, field, { ...value, [locator]: e.target.value === "" ? null : Number(e.target.value) })} /></label>)}</div>
        {value.status === "present" && value.page === null && <p className="text-xs text-amber-800">No unique source match. Check the value and specify the correct citation before approval.</p>}
      </div>;
    })}</div></details>)}
    <button className={button} type="button" onClick={() => change(JSON.stringify({ ...output, records: [...output.records, Object.fromEntries(fields.map(f => [f, { status: "missing", value: null, page: null, start: null, end: null }]))] }, null, 2))}>Add another source record</button>
  </div>;
}

export function DocumentLab() {
  const { ws, bundle } = useData();
  if (!bundle.workspace.intake) return <div className="border border-line p-6"><h1 className="text-2xl">Document lab</h1><p className="my-3">Choose an uploaded institution above, or create one in Records & overview. Fixed example workspaces cannot train or promote models.</p><Link href="/command" className="underline">Open Records & overview</Link></div>;
  return <Lab key={ws} ws={ws} />;
}

function Lab({ ws }: { ws: string }) {
  const base = `/api/workspaces/${ws}/extraction`;
  const [state, setState] = useState<State | null>(null);
  const [selected, setSelected] = useState("");
  const [role, setRole] = useState("invoice");
  const [file, setFile] = useState<File | null>(null);
  const [replaces, setReplaces] = useState("");
  const [editor, setEditor] = useState("");
  const [transcript, setTranscript] = useState("");
  const [group, setGroup] = useState("");
  const [consent, setConsent] = useState(false);
  const [includeRecords, setIncludeRecords] = useState(false);
  const [note, setNote] = useState("");
  const [authorization, setAuthorization] = useState("");
  const [model, setModel] = useState("");
  const [modelName, setModelName] = useState("");
  const [baseline, setBaseline] = useState("");
  const [dataset, setDataset] = useState("");
  const [datasetName, setDatasetName] = useState("");
  const [purpose, setPurpose] = useState("train");
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const refresh = useCallback(async () => { const next = await intakeApi<State>(base); setState(next); return next; }, [base]);
  useEffect(() => { let active = true; intakeApi<State>(base).then(s => { if (active) setState(s); }).catch(e => { if (active) setError(String(e)); }); return () => { active = false; }; }, [base]);
  const benchmarkRunning = state?.benchmark_job.some(j => ["queued", "running"].includes(j.status));
  useEffect(() => { if (!benchmarkRunning) return; const timer = setInterval(() => { void refresh().catch(e => setError(String(e))); }, 3000); return () => clearInterval(timer); }, [benchmarkRunning, refresh]);
  const doc = state?.documents.find(d => d.id === selected);
  const correction = state?.correction.filter(c => c.document_id === selected).at(-1);
  const prediction = state?.prediction.filter(p => p.document_id === selected).at(-1);
  async function act(action: () => Promise<unknown>, success: string) {
    setBusy(true); setError(""); setMessage("");
    try { await action(); await refresh(); setMessage(success); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  const post = (path: string, body: unknown) => intakeApi(base + path, { method: "POST", body: JSON.stringify(body) });
  function choose(d: Doc) {
    setSelected(d.id);
    const saved = state?.correction.filter(c => c.document_id === d.id).at(-1);
    const predicted = state?.prediction.filter(p => p.document_id === d.id && p.output).at(-1);
    const blank = { schema_version: state?.schema_version, records: [Object.fromEntries((state?.schemas[d.role] || []).map(k => [k, { status: "missing", value: null, page: null, start: null, end: null }]))] };
    setEditor(JSON.stringify(saved?.output || predicted?.output || blank, null, 2));
    setTranscript(JSON.stringify(d.pages.map(p => p.text), null, 2));
    setGroup(saved?.group || ""); setConsent(saved?.training_authorized || false); setIncludeRecords(false); setNote(""); setAuthorization("");
  }
  const latestCorrections = state?.correction.filter((c, i, all) => !all.slice(i + 1).some(next => next.document_id === c.document_id)) || [];
  const availableModels = state?.model.filter(m => !state.retirement.some(r => r.model_id === m.id)) || [];
  return <div className="mx-auto max-w-6xl space-y-6">
    <header><h1 className="text-3xl font-semibold">Documents & model improvement</h1><p className="mt-2 text-ink-dim">Add evidence anytime → check extraction → approve corrections → freeze datasets → benchmark → approve a model release.</p>
      <p className="mt-2 text-sm">Training weights come from your partner. This page manages evidence and evaluation, not automatic self-training or audit decisions.</p><Link href="/command" className="underline">Back to records, file updates & scans</Link></header>
    {error && <p role="alert" className="border border-red-300 bg-red-50 p-3 text-red-900">{error}</p>}
    {message && <p role="status" className="border border-teal-300 bg-teal-50 p-3">{message}</p>}
    {!state ? <p>Loading document workspace…</p> : <>
      <section className="border border-line p-5"><h2 className="text-xl font-semibold">1. Add documents to this institution</h2><p className="my-2 text-sm">PDF, PNG, JPEG, TXT or Markdown. Up to 10 MB, 20 pages, 12 megapixels/page. Original bytes stay on this laptop. Add new files here whenever they arrive; existing records are preserved.</p>
        <div className="flex flex-wrap items-end gap-3"><label>Document type<select className={input} value={role} onChange={e => setRole(e.target.value)}>{Object.keys(state.schemas).map(r => <option key={r}>{r}</option>)}</select></label>
          <label>Choose document<input className={input} type="file" accept=".pdf,.png,.jpg,.jpeg,.txt,.md" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
          <label>New file or revision<select className={input} value={replaces} onChange={e => setReplaces(e.target.value)}><option value="">New document</option>{state.documents.filter(d => d.role === role).map(d => <option key={d.id} value={d.id}>Replaces {d.name} v{d.version}</option>)}</select></label>
          <button className={button} disabled={busy || !file} onClick={() => act(async () => { const form = new FormData(); form.append("file", file!); form.append("role", role); if (replaces) form.append("replaces_id", replaces); const d = await intakeApi<Doc>(base + "/documents", { method: "POST", body: form }); choose(d); }, "Document preserved and processed. Review any OCR warnings before using the text.")}>Upload & process</button></div>
        <div className="mt-3 flex flex-wrap gap-2">{state.documents.map(d => <button className={button} key={d.id} onClick={() => choose(d)}>{d.name} · {d.role} · v{d.version}</button>)}</div>
      </section>
      {doc && <section className="border border-line p-5"><h2 className="text-xl font-semibold">2. Review {doc.name}</h2><p className="break-all font-mono text-xs">Original SHA256: {doc.sha256}</p><a className="underline" href={`${API_URL}${base}/documents/${doc.id}/original`}>Download preserved original</a>
        <div className="my-3 flex flex-wrap gap-2"><select aria-label="Extraction model" className={button} value={model} onChange={e => setModel(e.target.value)}><option value="">Active model {state.active ? `(${state.active.model_id})` : "— none yet"}</option>{availableModels.map(m => <option value={m.id} key={m.id}>{m.name}</option>)}</select>
          <button className={button} disabled={busy || (!model && !state.active)} onClick={() => act(async () => { const p = await intakeApi<{ output: Output | null; error: string | null }>(base + "/predict", { method: "POST", body: JSON.stringify({ document_id: doc.id, model_id: model || null }) }); if (p.error) throw new Error(p.error); setEditor(JSON.stringify(p.output, null, 2)); }, "Extraction ready for human review—not yet accepted or used for training.")}>Extract with local model</button></div>
        <div className="grid gap-4 lg:grid-cols-2"><div className="max-h-[650px] overflow-auto">{doc.pages.map(p => <article className="mb-4 border border-line p-3" key={p.page}><h3 className="font-semibold">Page {p.page} · {p.method}</h3>{p.warnings.map(w => <p className="text-sm text-amber-800" key={w}>{w}</p>)}{![".txt", ".md"].includes(doc.suffix) && <a target="_blank" rel="noreferrer" className="underline" href={`${API_URL}${base}/documents/${doc.id}/pages/${p.page}`}>View original page image</a>}<pre className="whitespace-pre-wrap text-xs">{p.text}</pre></article>)}</div>
          <div><p className="mb-2 text-sm">Present values must match the page text. Character offsets are zero-based, end exclusive. Records follow source order.</p><FieldEditor text={editor} doc={doc} fields={state.schemas[doc.role]} change={setEditor} /><details className="mt-3"><summary>Advanced extraction JSON</summary><label>Extraction JSON<textarea aria-label="Extraction JSON" spellCheck={false} className={`${input} h-96 font-mono text-xs`} value={editor} onChange={e => setEditor(e.target.value)} /></label></details></div></div>
        <details className="my-3"><summary>Correct OCR transcription before labeling</summary><p className="my-2 text-sm">Compare each page image first. This creates a new text revision and invalidates old labels/datasets; the original file is never overwritten.</p><textarea aria-label="Page transcription JSON array" className={`${input} h-40 font-mono`} value={transcript} onChange={e => setTranscript(e.target.value)} /><button disabled={busy || !note.trim()} className={button} onClick={() => act(() => post(`/documents/${doc.id}/transcription`, { expected_text_sha256: doc.text_sha256, pages: JSON.parse(transcript), note }), "Transcription version saved. Re-select the document and review all field spans again.")}>Save transcription revision</button></details>
        <div className="grid gap-3 md:grid-cols-2"><label>Institution/vendor/template group<input className={input} value={group} onChange={e => setGroup(e.target.value)} placeholder="Keep related templates in the same split" /></label><label>Review note<input className={input} value={note} onChange={e => setNote(e.target.value)} /></label><label>Dataset authorization / restriction note<input className={input} value={authorization} onChange={e => setAuthorization(e.target.value)} placeholder="Synthetic data I own, or describe restrictions" /></label><label className="flex items-center gap-2"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />I am authorized to use this document for training/evaluation</label></div>
        <div className="mt-3 flex flex-wrap gap-2"><button className={button} disabled={busy || !group.trim() || !note.trim() || !authorization.trim()} onClick={() => act(() => post("/corrections", { document_id: doc.id, prediction_id: prediction?.id || null, expected_previous: correction?.id || null, text_sha256: doc.text_sha256, output: JSON.parse(editor), group, note, training_authorized: consent, authorization_note: authorization }), "Human-reviewed correction saved. Nothing has been automatically posted or trained.")}>Approve correction / update consent</button>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={includeRecords} onChange={e => setIncludeRecords(e.target.checked)} />Also stage structured records (only if these events are not already imported; otherwise leave as corroborating evidence)</label>
          <button className={button} disabled={busy || !correction || correction.text_sha256 !== doc.text_sha256} onClick={() => act(() => post("/stage", { correction_id: correction!.id, include_records: includeRecords }), "Approved extraction staged. Open Records & overview, review the import, resolve validation issues, then explicitly commit.")}>Stage latest approved correction for intake</button></div>
      </section>}
      <section className="border border-line p-5"><h2 className="text-xl font-semibold">3. Freeze a dataset</h2><p className="my-2 text-sm">Select reviewed, authorized documents. Related institutions/templates cannot occur in both train and evaluation sets. Held-out labels never go to the inference endpoint or training export.</p>
        {latestCorrections.map(c => <label className="my-1 flex gap-2 text-sm" key={c.id}><input type="checkbox" disabled={!c.training_authorized} checked={chosen.includes(c.id)} onChange={e => setChosen(e.target.checked ? [...chosen, c.id] : chosen.filter(x => x !== c.id))} />{state.documents.find(d => d.id === c.document_id)?.name} · {c.group} · {c.training_authorized ? "authorized" : "not authorized"}</label>)}
        <div className="my-3 flex flex-wrap gap-2"><input aria-label="Dataset name" className={button} value={datasetName} onChange={e => setDatasetName(e.target.value)} placeholder="Dataset version name" /><select aria-label="Dataset purpose" className={button} value={purpose} onChange={e => setPurpose(e.target.value)}><option value="train">Training export</option><option value="evaluation">Held-out evaluation</option></select><button className={button} disabled={busy || !chosen.length || !datasetName.trim()} onClick={() => act(async () => { await post("/datasets", { name: datasetName, purpose, correction_ids: chosen }); setChosen([]); }, "Dataset frozen with immutable labels, source hashes and split groups.")}>Freeze selected corrections</button></div>
        {state.dataset.map(d => <div className="mb-2 break-all text-sm" key={d.id}>{d.name} · {d.purpose} · {d.groups.length} groups · <code>{d.sha256}</code><a className="ml-2 underline" href={`${API_URL}${base}/datasets/${d.id}/manifest.json`}>Download manifest</a>{d.purpose === "train" && <a className="ml-2 underline" href={`${API_URL}${base}/datasets/${d.id}/training.jsonl`}>Download training JSONL</a>}</div>)}
      </section>
      <section className="border border-line p-5"><h2 className="text-xl font-semibold">4. Register and benchmark partner models</h2><p className="my-2 text-sm">An admin first configures the named loopback inference endpoint and artifact/training manifest on the server. Registering a candidate does not activate it. No model is installed or trained by these controls.</p>
        <label className="my-3 block">Model registration / release decision note<input className={input} value={note} onChange={e => setNote(e.target.value)} placeholder="Why this candidate or release is appropriate" /></label>
        <div className="flex flex-wrap gap-2"><input aria-label="Configured model name" className={button} placeholder="Configured model name" value={modelName} onChange={e => setModelName(e.target.value)} /><button className={button} disabled={busy || !modelName || !note.trim()} onClick={() => act(() => post("/models", { name: modelName, note }), "Model manifest registered; benchmark before activation.")}>Register model using review note</button></div>
        <div className="my-3 grid gap-2 md:grid-cols-3"><label>Frozen evaluation set<select className={input} value={dataset} onChange={e => setDataset(e.target.value)}><option value="">Select…</option>{state.dataset.filter(d => d.purpose === "evaluation").map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label><label>Baseline model<select className={input} value={baseline} onChange={e => setBaseline(e.target.value)}><option value="">Select…</option>{availableModels.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label><label>Candidate model<select className={input} value={model} onChange={e => setModel(e.target.value)}><option value="">Select…</option>{availableModels.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label></div>
        <button className={button} disabled={busy || benchmarkRunning || !dataset || !model || !baseline || model === baseline} onClick={() => act(() => post("/benchmark-jobs", { dataset_id: dataset, baseline_id: baseline, candidate_id: model }), "Paired benchmark queued locally. Progress persists here; only completed evaluation results can qualify for promotion.")}>Run paired benchmark (may take several minutes)</button>
        {state.benchmark_job.map(j => <p key={j.id} className="my-2 text-sm" role="status">Benchmark {j.id}: {j.status}{j.error ? ` — ${j.error}` : ""}</p>)}
        <details className="my-3"><summary>Promotion thresholds (engineering gates, not measured accuracy)</summary><pre className="overflow-auto text-xs">{JSON.stringify(state.policy, null, 2)}</pre></details>
        {state.evaluation.map(e => <article className="my-3 border border-line p-3" key={e.id}><b>{e.passed ? "Passed gates" : "Not eligible for promotion"}</b><p className="text-xs">{e.id}</p><a className="text-sm underline" href={`${API_URL}${base}/evaluations/${e.id}/report.json`}>Download measured benchmark report</a><ul className="my-2 list-disc pl-5 text-sm">{e.failures.map(f => <li key={f}>{f}</li>)}</ul><details><summary>Measured baseline and candidate metrics</summary><pre className="overflow-auto text-xs">{JSON.stringify(e.runs, null, 2)}</pre></details><button className={button} disabled={busy || !e.passed || !note.trim()} onClick={() => act(() => post("/promote", { evaluation_id: e.id, expected_version: state.active?.version || 0, note }), "Model explicitly promoted. Future extractions use this version; past outputs are unchanged.")}>Approve promotion using review note</button></article>)}
      </section>
      <section className="border border-line p-5"><h2 className="text-xl font-semibold">5. Monitor, roll back or retire</h2><p className="my-2">Active model: {state.active?.model_id || "None—manual review remains available"}</p><p className="text-sm">{state.prediction.length} extraction attempts · {state.prediction.filter(p => p.error).length} failed/invalid · {state.correction.length} reviewed revisions. These counts are not model accuracy.</p>
        {state.release.map(r => <div className="my-2 flex flex-wrap items-center gap-2" key={r.id}><span className="text-sm">Release {r.version}: {r.model_id}</span><button className={button} disabled={busy || !note.trim() || !state.active || r.model_id === state.active.model_id} onClick={() => act(() => post("/rollback", { release_id: r.id, expected_version: state.active!.version, note }), "Rolled back to a previously approved release.")}>Roll back to this release</button></div>)}
        <button className={button} disabled={busy || !model || !note.trim() || model === state.active?.model_id} onClick={() => act(() => post("/retire", { model_id: model, note }), "Candidate retired; cannot be used or promoted.")}>Retire selected inactive model</button>
      </section>
    </>}
    {busy && <p role="status">Processing… Keep this page open. Originals are preserved; do not repeat the operation.</p>}
  </div>;
}
