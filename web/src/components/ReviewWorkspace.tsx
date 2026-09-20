"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { API_URL, intakeApi, useData } from "@/lib/data";

type FollowUp = { version: number; owner: string; status: string; note: string; actor: string };
type Finding = { id: string; title: string; role: string; status: string; explanation: string; amount_cents: number | null;
  action: string; origin: string; review: string; evidence: { source_id: string; line: number }[];
  snapshot_id: string; stale: boolean; follow_up: FollowUp | null };
type View = { workspace: { name: string; start: string; end: string }; snapshot_id: string | null;
  scan: { id: string; snapshot_id: string; record_count: number; created_at: string } | null;
  findings: Finding[]; changes: { id: string; title: string; before: string; after: string }[];
  live: { id: string; status: string; briefing: string; report_markdown: string; unresolved: string[];
    tasks: { spec: { id: string; role: string }; status: string }[] } | null; live_stale: boolean;
  history: { id: string; created_at: string; actor: string; kind: string; payload: { note?: string; status?: string; owner?: string } }[];
  limitations: string[]; demo: boolean; evidence_added: boolean };
const roles: Record<string, string> = { cfo: "CFO Agent", ap: "AP & Payments", py: "Payroll & Budget", gr: "Grants & Compliance" };
const currency = (cents: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
const control = "border border-line bg-white px-3 py-2 text-sm disabled:opacity-40";
const primary = "bg-ink px-4 py-3 text-sm font-semibold text-white disabled:opacity-40";

export function ReviewWorkspace({ section = "overview" }: { section?: "overview" | "findings" | "reports" | "actions" }) {
  const { ws } = useData();
  return <WorkspaceReview key={ws} ws={ws} section={section} />;
}

function WorkspaceReview({ ws, section }: { ws: string; section: string }) {
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [filter, setFilter] = useState("attention");
  const [selected, setSelected] = useState("");
  const [source, setSource] = useState<{ name: string; lines: { number: number; text: string }[]; line_count: number } | null>(null);
  const [sourceRef, setSourceRef] = useState<{ id: string; start: number } | null>(null);
  const uploaded = ws.startsWith("ws-");
  const refresh = useCallback(async () => {
    const next = await intakeApi<View>(`/api/workspaces/${ws}/review`);
    setView(next); return next;
  }, [ws]);
  useEffect(() => {
    if (!uploaded) return;
    let active = true;
    const load = async () => {
      try { const next = await intakeApi<View>(`/api/workspaces/${ws}/review`); if (active) { setView(next); setError(""); } }
      catch (e) { if (active) setError(e instanceof Error ? e.message : "Review unavailable"); }
    };
    void load(); const timer = setInterval(load, 4000);
    return () => { active = false; clearInterval(timer); };
  }, [uploaded, ws]);
  async function run(action: "scan" | "evidence") {
    setBusy(action); setError("");
    try {
      if (action === "evidence") await intakeApi(`/api/workspaces/${ws}/review/demo-evidence`, { method: "POST" });
      await intakeApi(`/api/workspaces/${ws}/review/scans`, { method: "POST" }); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Scan failed"); }
    finally { setBusy(""); }
  }
  async function readSource(id: string, start: number) {
    setError("");
    try { setSource(await intakeApi(`/api/workspaces/${ws}/sources/${encodeURIComponent(id)}?start=${start}&limit=20`)); setSourceRef({ id, start }); }
    catch (e) { setError(e instanceof Error ? e.message : "Source unavailable"); }
  }
  if (!uploaded) return <div className="border border-line p-6"><h1 className="text-2xl font-semibold">Start with records, not a sample dashboard.</h1>
    <p className="my-3 max-w-2xl text-ink-dim">This workspace is a fixed example. Create a fresh fictional scan to interact with imported records, or select your uploaded workspace above.</p>
    <Link href="/" className={primary + " inline-block"}>Start from the home page →</Link></div>;
  const filtered = view?.findings.filter(f => filter === "all" || (filter === "attention" ? f.status !== "pass" : f.status === filter)) || [];
  const current = filtered.find(f => f.id === selected) || filtered[0];
  const stale = !!view?.scan && view.scan.snapshot_id !== view.snapshot_id;
  return <div className="mx-auto max-w-6xl space-y-5">
    <div><p className="text-xs uppercase tracking-widest text-ink-dim">Your financial review · fictional management profile</p>
      <h1 className="mt-2 text-3xl font-semibold">{section === "reports" ? "Director briefing" : section === "actions" ? "Assign follow-up. Record a decision." : section === "findings" ? "What needs your attention?" : "Review the period. Follow the evidence."}</h1>
      <p className="mt-2 text-ink-dim">{view?.workspace.name || "Loading workspace…"} · {view?.workspace.start} — {view?.workspace.end}</p></div>
    <div className="flex flex-wrap gap-2 text-sm">
      {[["1 · Records", "/command"], ["2 · Scan", "/scan"], ["3 · Findings", "/findings"], ["4 · Follow-up", "/approvals"], ["5 · Report", "/reports"]].map(([label, href]) => <Link key={href} href={href} className={control}>{label}</Link>)}
    </div>
    <section className="border border-line bg-surface-2 p-5"><div className="flex flex-wrap items-center gap-3">
      <button disabled={!!busy || !view?.snapshot_id} className={primary} onClick={() => void run("scan")}>{busy === "scan" ? "Running checks…" : view?.scan ? "Rerun record checks" : "Scan committed records"}</button>
      <Link href="/cfo" className={control}>Optional: live five-agent review ↗</Link>
      {view?.demo && <button className={control} disabled={!!busy || view.evidence_added} onClick={() => void run("evidence")}>{busy === "evidence" ? "Importing evidence and rescanning…" : view.evidence_added ? "Service evidence added" : "Add the withheld service record & rescan"}</button>}
    </div><p className="mt-3 text-sm text-ink-dim">Record checks run locally, without a model. A live review sends selected records to the API provider and can incur cost. Neither changes your books.</p>
</section>
    {error && <p role="alert" className="border border-red-300 bg-red-50 p-3 text-red-800">{error}</p>}
    {(stale || view?.live_stale) && <p role="status" className="border border-amber-300 bg-amber-50 p-4">New records have been committed. Older results are historical, not current assurance. Rerun before making a decision.</p>}
    {view && <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[["Records in last scan", view.scan?.record_count || 0], ["Needs attention", view.findings.filter(f => !f.stale && f.status === "attention").length], ["Evidence gaps", view.findings.filter(f => !f.stale && f.status === "gap").length], ["Narrow checks passed", view.findings.filter(f => !f.stale && f.status === "pass").length]].map(([label, n]) => <div key={label} className="border border-line p-4"><b className="block font-num text-3xl">{n}</b><span className="text-sm text-ink-dim">{label}</span></div>)}</div>
      <p className="text-xs text-ink-dim">Snapshot: {view.snapshot_id || "No committed sources"}. Counts describe supplied records, not the whole institution. Amounts overlap and are not a savings total. Decisions apply only to their original snapshot; earlier follow-up remains in the history below.</p>
      {view.live && <section className="border border-line p-4"><h2 className="font-semibold">Live five-agent review · {view.live.status}{view.live_stale ? " · outdated snapshot" : ""}</h2><p className="mt-2">{view.live.briefing}</p>
        <div className="mt-2 flex flex-wrap gap-3 text-xs">{view.live.tasks.map(t => <span key={t.spec.id}>{roles[t.spec.role]}: {t.status}</span>)}</div>
        <details className="mt-3"><summary>Unresolved agent questions ({view.live.unresolved.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5">{view.live.unresolved.map((s, i) => <li key={i}>{s}</li>)}</ul></details></section>}
      {view.changes.length > 0 && <section className="border border-green-300 bg-green-50 p-4"><h2 className="font-semibold">What changed after the latest scan?</h2>{view.changes.map(c => <div className="mt-3" key={c.id}><b>{c.title}</b><p className="text-sm">Before: {c.before}</p><p className="text-sm">Now: {c.after}</p></div>)}<p className="mt-3 text-xs">Adding evidence does not automatically approve its contents or resolve a finding.</p></section>}
      {section === "reports" ? <section className="border border-line p-5"><a className={primary + " inline-block"} href={`${API_URL}/api/workspaces/${ws}/review/report`}>Download director briefing (.md)</a><button className={control + " ml-2"} onClick={() => window.print()}>Print / save PDF</button><pre className="print-report mt-5 whitespace-pre-wrap font-sans text-sm leading-relaxed">{briefing(view)}</pre></section> : <>
        <div className="flex flex-wrap items-center gap-3"><h2 className="text-xl font-semibold">Checks & reviewed findings</h2><label className="ml-auto text-sm">Show <select className={control} value={filter} onChange={e => setFilter(e.target.value)}><option value="attention">Attention + gaps</option><option value="all">All checks</option><option value="pass">Narrow passes</option><option value="gap">Evidence gaps</option></select></label></div>
        {!view.findings.length && <p className="border border-line p-5">No scan results yet. Commit records on the Records page, then start a scan above. An empty list is not a clean audit.</p>}
        <div className="grid gap-5 lg:grid-cols-[1fr_1.1fr]"><div className="space-y-2">{filtered.map(f => <button key={f.id} onClick={() => { setSelected(f.id); setSource(null); }} aria-pressed={current?.id === f.id} className={`w-full border p-4 text-left ${current?.id === f.id ? "border-ink bg-surface-2" : "border-line"}`}>
          <span className="text-xs uppercase tracking-wide text-ink-dim">{roles[f.role]} · {f.origin === "live_agent" ? "Auditor-accepted claim" : f.origin === "standalone_candidate" ? "Standalone candidate" : "Rules-based check"}{f.stale ? " · historical" : ""}</span><b className="my-2 block">{f.title}</b>
          <span className={f.status === "attention" ? "text-red-700" : f.status === "gap" ? "text-amber-800" : "text-green-800"}>{f.status === "pass" ? "Passed within stated scope" : f.status === "gap" ? "Evidence needed" : "Investigate"}</span>{f.amount_cents !== null && <span className="ml-3 font-num">{currency(f.amount_cents)}</span>}
          {f.follow_up && <small className="mt-2 block">Follow-up: {f.follow_up.status.replaceAll("_", " ")} · {f.follow_up.owner || "Unassigned"}</small>}</button>)}</div>
          {current && <article className="self-start border border-line p-5"><h2 className="text-xl font-semibold">{current.title}</h2><p className="my-3 leading-relaxed">{current.explanation}</p><p className="text-sm text-ink-dim">{current.review}</p><h3 className="mt-5 font-semibold">Suggested next step</h3><p className="mt-1 text-sm">{current.action}</p>
            <h3 className="mt-5 font-semibold">Inspect original evidence</h3><div className="my-3 flex flex-wrap gap-2">{current.evidence.map((e, i) => <button className={control} key={`${e.source_id}-${e.line}`} onClick={() => void readSource(e.source_id, Math.max(1, e.line - 1))}>Source {i + 1} · line {e.line}</button>)}{!current.evidence.length && <p className="text-sm text-ink-dim">This is a missing-input check; no source has been fabricated.</p>}</div>
            {source && <section aria-label="Original source" className="my-4 border border-line bg-surface-2 p-3"><b>{source.name}</b><pre className="my-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs">{source.lines.map(l => `${l.number}: ${l.text}`).join("\n")}</pre><p className="text-xs">Showing a bounded excerpt of {source.line_count} lines.</p><button className={control} disabled={!sourceRef || sourceRef.start + 20 > source.line_count} onClick={() => sourceRef && void readSource(sourceRef.id, sourceRef.start + 20)}>Next lines</button></section>}
            <FollowUpForm key={`${current.id}-${current.snapshot_id}-${current.follow_up?.version || 0}`} ws={ws} finding={current} saved={refresh} />
          </article>}</div>
      </>}
      <details className="border border-line p-4"><summary className="cursor-pointer font-semibold">Human follow-up & scan history ({view.history.length})</summary>{view.history.map(e => <div key={e.id} className="border-t border-line py-3 text-sm"><b>{e.kind} · {e.actor}</b><p>{e.created_at}</p><p>{e.payload.status?.replaceAll("_", " ")} {e.payload.owner} {e.payload.note}</p></div>)}</details>
      <details className="border border-line p-4" open><summary className="font-semibold">What this review does not establish</summary><ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-ink-dim">{view.limitations.map(l => <li key={l}>{l}</li>)}</ul></details>
    </>}
  </div>;
}

function FollowUpForm({ ws, finding: f, saved }: { ws: string; finding: Finding; saved: () => Promise<unknown> }) {
  const [owner, setOwner] = useState(f.follow_up?.owner || ""); const [note, setNote] = useState("");
  const [status, setStatus] = useState("open"); const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setMessage("");
    try { await intakeApi(`/api/workspaces/${ws}/review/actions`, { method: "POST", body: { finding_id: f.id, snapshot_id: f.snapshot_id, expected_version: f.follow_up?.version || 0, owner, note, status } }); await saved(); }
    catch (e) { setMessage(e instanceof Error ? e.message : "Unable to save"); } finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="mt-5 space-y-3 border-t border-line pt-4"><h3 className="font-semibold">Record human follow-up</h3>
    <label className="block text-sm">Owner / team<input className={control + " mt-1 w-full"} value={owner} onChange={e => setOwner(e.target.value)} maxLength={120} placeholder="e.g. Finance operations" /></label>
    <label className="block text-sm">Next action<select className={control + " mt-1 w-full"} value={status} onChange={e => setStatus(e.target.value)}><option value="open">Assign / add a note</option><option value="evidence_requested">Request supporting evidence</option><option value="proposed">Propose a correction for review</option><option disabled={f.follow_up?.status !== "proposed"} value="approved_proposal">Approve the proposal (no posting)</option><option disabled={f.follow_up?.status !== "proposed"} value="rejected_proposal">Reject the proposal</option></select></label>
    <label className="block text-sm">Reason / requested evidence<textarea required maxLength={2000} value={note} onChange={e => setNote(e.target.value)} className={control + " mt-1 min-h-20 w-full"} /></label>
    <button className={primary} disabled={busy || f.stale || !note.trim()}>{busy ? "Saving…" : f.stale ? "Rerun before deciding" : "Save follow-up"}</button><p className="text-xs text-ink-dim">Saved to this snapshot’s history. No email sent, journal posted or payment released.</p>{message && <p role="alert" className="text-red-700">{message}</p>}
  </form>;
}

function briefing(v: View) {
  return [`# ${v.workspace.name} — director briefing`, `Period: ${v.workspace.start} to ${v.workspace.end}`, `Current snapshot: ${v.snapshot_id}`, "", "## Method", "Rules-based checks over committed source records. Optional live-agent claims are identified separately. This is not an audit opinion.", "", ...v.findings.flatMap(f => [
    `### ${f.title}`, `${f.status.toUpperCase()}${f.stale ? " · HISTORICAL / RERUN REQUIRED" : ""} · ${f.origin} · snapshot ${f.snapshot_id}`, f.explanation,
    f.amount_cents === null ? "Amount: not established" : `Check amount: ${currency(f.amount_cents)} (not savings; may overlap other checks)`,
    `Next step: ${f.action}`, `Evidence: ${f.evidence.map(e => `${e.source_id}, line ${e.line}`).join("; ") || "missing input"}`,
    `Human follow-up: ${f.follow_up ? `${f.follow_up.status}; owner ${f.follow_up.owner || "unassigned"}; ${f.follow_up.note}` : "not recorded"}`, ""]),
    "## Live CFO report", v.live ? `${v.live_stale ? "HISTORICAL SNAPSHOT — RERUN REQUIRED\n" : ""}${v.live.report_markdown || v.live.briefing}` : "No live model review has run.", "", "## Limitations", ...v.limitations.map(l => `- ${l}`)].join("\n");
}
