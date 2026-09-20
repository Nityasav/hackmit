"use client";

import { displayLabel } from "@/lib/format";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useState } from "react";
import { Decisions } from "@/components/Decisions";
import { API_URL, intakeApi, useData } from "@/lib/data";
import type { SourceDetail } from "@/lib/types";

type FollowUp = { version: number; owner: string; status: string; note: string; actor: string };
type Finding = { id: string; title: string; role: string; status: string; explanation: string; amount_cents: number | null;
  action: string; origin: string; review: string; evidence: { source_id: string; line: number }[];
  snapshot_id: string; stale: boolean; follow_up: FollowUp | null };
type View = { workspace: { name: string; start: string; end: string }; snapshot_id: string | null;
  scan: { id: string; snapshot_id: string; record_count: number; created_at: string } | null;
  findings: Finding[]; changes: { id: string; title: string; before: string; after: string }[];
  // A tally of what the agents concluded, read off the decision trail they
  // wrote. It used to be a coordinator run object carrying a task list, a
  // briefing and its own status; that coordinator no longer exists, and
  // reading its shape off this one crashed the whole Briefing page.
  live: { decisions: number; escalated: number; spend_cents: number } | null; live_stale: boolean;
  // `summary` is one plain sentence saying what was actually done. The list
  // used to show an event kind and a timestamp, which says that something
  // happened without saying what.
  history: { id: string; created_at: string; actor: string; kind: string; summary?: string;
    agent?: string | null;
    payload: { note?: string; status?: string; owner?: string } }[];
  limitations: string[] };
const roles: Record<string, string> = { cfo: "CFO Agent", ap: "AP & Payments", py: "Payroll & Budget", gr: "Grants & Compliance", rc: "Revenue & Collections" };
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
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [byAgent, setByAgent] = useState("");
  const [source, setSource] = useState<SourceDetail | null>(null);
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
  async function run() {
    setBusy("scan"); setError("");
    try { await intakeApi(`/api/workspaces/${ws}/review/scans`, { method: "POST" }); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "Scan failed"); }
    finally { setBusy(""); }
  }
  async function readSource(id: string, start: number) {
    setError("");
    try { setSource(await intakeApi(`/api/workspaces/${ws}/sources/${encodeURIComponent(id)}?start=${start}&limit=20`)); setSourceRef({ id, start }); }
    catch (e) { setError(e instanceof Error ? e.message : "Source unavailable"); }
  }
  if (!uploaded) return <div className="border border-line p-6"><h1 className="text-2xl font-semibold">No company is selected yet.</h1>
    <p className="my-3 max-w-2xl text-ink-dim">Create an institution and commit its records to prepare a briefing.</p>
    <Link href="/" className={primary + " inline-block"}>Add a company&rsquo;s records →</Link></div>;
  // Money-in checks are sorted last so the heading in the list marks one contiguous group.
  const filtered = (view?.findings.filter(f => filter === "all" || (filter === "attention" ? f.status !== "pass" : filter === "rc" ? f.role === "rc" : f.status === filter)) || [])
    .sort((a, b) => Number(a.role === "rc") - Number(b.role === "rc"));
  const current = filtered.find(f => f.id === selected) || filtered[0];
  const stale = !!view?.scan && view.scan.snapshot_id !== view.snapshot_id;
  // Dates are ISO, so a prefix comparison is the whole filter. `to` includes
  // the chosen day rather than cutting it off at midnight.
  const shownHistory = (view?.history || []).filter(e => {
    const day = e.created_at.slice(0, 10);
    if (fromDate && day < fromDate) return false;
    if (toDate && day > toDate) return false;
    if (byAgent === "__none") return !e.agent;
    if (byAgent && e.agent !== byAgent) return false;
    return true;
  });
  const historyAgents = [...new Set((view?.history || []).map(e => e.agent).filter(Boolean))] as string[];
  return <div className="mx-auto max-w-6xl space-y-5">
    <div><p className="text-xs uppercase tracking-widest text-ink-dim">Financial review</p>
      <h1 className="mt-2 text-3xl font-semibold">{section === "reports" ? "Director briefing" : section === "actions" ? "Follow-up" : section === "findings" ? "Findings" : "Period review"}</h1>
      <p className="mt-2 text-ink-dim">{view?.workspace.name || "Loading workspace…"} · {view?.workspace.start} — {view?.workspace.end}</p></div>
    <section className="border border-line bg-surface-2 p-5"><div className="flex flex-wrap items-center gap-3">
      <button disabled={!!busy || !view?.snapshot_id} className={primary} onClick={() => void run()}>{busy ? "Running checks…" : view?.scan ? "Rerun record checks" : "Scan committed records"}</button>
    </div><p className="mt-3 text-sm text-ink-dim">Record checks run locally, without a model. A live review sends selected records to the API provider and can incur cost. Neither changes your books.</p>
</section>
    {error && <p role="alert" className="border border-red-300 bg-red-50 p-3 text-red-800">{error}</p>}
    {(stale || view?.live_stale) && <p role="status" className="border border-amber-300 bg-amber-50 p-4">New records have been committed. Older results are historical, not current assurance. Rerun before making a decision.</p>}
    {view && <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[["Records in last scan", view.scan?.record_count || 0], ["Needs attention", view.findings.filter(f => !f.stale && f.status === "attention").length], ["Evidence gaps", view.findings.filter(f => !f.stale && f.status === "gap").length], ["Narrow checks passed", view.findings.filter(f => !f.stale && f.status === "pass").length]].map(([label, n]) => <div key={label} className="border border-line p-4"><b className="block font-num text-3xl">{n}</b><span className="text-sm text-ink-dim">{label}</span></div>)}</div>
      <p className="text-xs text-ink-dim">Snapshot: {view.snapshot_id || "No committed sources"}. Counts describe supplied records, not the whole institution. Amounts overlap and are not a savings total. Decisions apply only to their original snapshot; earlier follow-up remains in the history below.</p>
      {view.live && <section className="border border-line p-4"><h2 className="font-semibold">Live agent review{view.live_stale ? " · outdated snapshot" : ""}</h2>
        <div className="mt-2 flex flex-wrap gap-6 text-sm">
          <span><b className="font-num">{view.live.decisions}</b> agent conclusion(s)</span>
          <span><b className="font-num">{view.live.escalated}</b> escalated to a person</span>
          <span><b className="font-num">{currency(view.live.spend_cents)}</b> spent</span>
        </div>
        <p className="mt-2 text-xs text-ink-dim">Each conclusion appears below with its evidence. An escalated one is waiting on a person; none of them approves, posts or pays anything.</p></section>}
      {view.changes.length > 0 && <section className="border border-green-300 bg-green-50 p-4"><h2 className="font-semibold">What changed after the latest scan?</h2>{view.changes.map(c => <div className="mt-3" key={c.id}><b>{c.title}</b><p className="text-sm">Before: {c.before}</p><p className="text-sm">Now: {c.after}</p></div>)}<p className="mt-3 text-xs">Adding evidence does not automatically approve its contents or resolve a finding.</p></section>}
      {/* Also on Investigation, beside the precedent it produces. It belongs
          on both: that screen shows the loop, this one is where a person
          comes to review and act, and looking for it here first is the
          reasonable instinct. */}
      <Decisions />
      {section === "reports" ? <section className="border border-line p-5"><a className={primary + " inline-block"} href={`${API_URL}/api/workspaces/${ws}/review/report`}>Download briefing (.md)</a><button className={control + " ml-2"} onClick={() => window.print()}>Print / save PDF</button><pre className="print-report mt-5 whitespace-pre-wrap font-sans text-sm leading-relaxed">{briefing(view)}</pre></section> : <>
        <div className="flex flex-wrap items-center gap-3"><h2 className="text-xl font-semibold">Checks & reviewed findings</h2><label className="ml-auto text-sm">Show <select className={control} value={filter} onChange={e => setFilter(e.target.value)}><option value="attention">Attention + gaps</option><option value="all">All checks</option><option value="pass">Narrow passes</option><option value="gap">Evidence gaps</option><option value="rc">Money coming in</option></select></label></div>
        {!view.findings.length && <p className="border border-line p-5">No scan results yet. Commit records on the Records page, then start a scan above. An empty list is not a clean audit.</p>}
        <div className="grid gap-5 lg:grid-cols-[1fr_1.1fr]"><div className="space-y-2">{filtered.map((f, i) => <Fragment key={f.id}>
          {f.role === "rc" && filtered[i - 1]?.role !== "rc" && <h3 className="pt-3 text-xs font-semibold uppercase tracking-widest text-ink-dim">Money coming in · fees, collections, deposits, pledges</h3>}
          <button onClick={() => { setSelected(f.id); setSource(null); }} aria-pressed={current?.id === f.id} className={`w-full border p-4 text-left ${current?.id === f.id ? "border-ink bg-surface-2" : "border-line"}`}>
          <span className="text-xs uppercase tracking-wide text-ink-dim">{roles[f.role]} · {f.origin === "live_agent" ? "Auditor-accepted claim" : f.origin === "standalone_candidate" ? "Standalone candidate" : "Rules-based check"}{f.stale ? " · historical" : ""}</span><b className="my-2 block">{f.title}</b>
          <span className={f.status === "attention" ? "text-red-700" : f.status === "gap" ? "text-amber-800" : "text-green-800"}>{f.status === "pass" ? "Passed within stated scope" : f.status === "gap" ? "Evidence needed" : "Investigate"}</span>{f.amount_cents !== null && <span className="ml-3 font-num">{currency(f.amount_cents)}</span>}
          {f.follow_up && <small className="mt-2 block">Follow-up: {displayLabel(f.follow_up.status)} · {f.follow_up.owner || "Unassigned"}</small>}</button></Fragment>)}</div>
          {current && <article className="self-start border border-line p-5"><h2 className="text-xl font-semibold">{current.title}</h2><p className="my-3 leading-relaxed">{current.explanation}</p><p className="text-sm text-ink-dim">{current.review}</p><h3 className="mt-5 font-semibold">Suggested next step</h3><p className="mt-1 text-sm">{current.action}</p>
            <h3 className="mt-5 font-semibold">Inspect original evidence</h3><div className="my-3 flex flex-wrap gap-2">{current.evidence.map((e, i) => <button className={control} key={`${e.source_id}-${e.line}`} onClick={() => void readSource(e.source_id, Math.max(1, e.line - 1))}>Source {i + 1} · line {e.line}</button>)}{!current.evidence.length && <p className="text-sm text-ink-dim">This is a missing-input check; no source has been fabricated.</p>}</div>
            {source && <section aria-label="Original source" className="my-4 border border-line bg-surface-2 p-3"><b>{source.name}</b>
              {source.extraction_origin && <div className="my-2 text-sm"><p>This is text someone read out of a document and checked, not the document itself.</p>
                <a className="underline" href={`${API_URL}/api/workspaces/${ws}/extraction/documents/${source.extraction_origin.document_id}/original`}>Download the original: {source.extraction_origin.name}</a>
                {source.extraction_origin.has_images && source.extraction_origin.pages.map(page => <a key={page} target="_blank" rel="noreferrer" className="ml-3 underline" href={`${API_URL}/api/workspaces/${ws}/extraction/documents/${source.extraction_origin!.document_id}/pages/${page}`}>Original page {page}</a>)}</div>}
              <pre className="my-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs">{source.lines.map(l => `${l.number}: ${l.text}`).join("\n")}</pre><p className="text-xs">Showing a bounded excerpt of {source.line_count} lines.</p><button className={control} disabled={!sourceRef || sourceRef.start + 20 > source.line_count} onClick={() => sourceRef && void readSource(sourceRef.id, sourceRef.start + 20)}>Next lines</button></section>}
            <FollowUpForm key={`${current.id}-${current.snapshot_id}-${current.follow_up?.version || 0}`} ws={ws} finding={current} saved={refresh} />
          </article>}</div>
      </>}
      <details className="border border-line p-4"><summary className="cursor-pointer font-semibold">Human follow-up &amp; scan history ({shownHistory.length}{shownHistory.length !== view.history.length ? ` of ${view.history.length}` : ""})</summary>
        <div className="mt-3 flex flex-wrap items-end gap-3 text-xs">
          <label>From<input type="date" className={control + " ml-2"} value={fromDate} onChange={e => setFromDate(e.target.value)} /></label>
          <label>To<input type="date" className={control + " ml-2"} value={toDate} onChange={e => setToDate(e.target.value)} /></label>
          <label>Raised by
            <select className={control + " ml-2"} value={byAgent} onChange={e => setByAgent(e.target.value)}>
              <option value="">Any agent</option>
              {historyAgents.map(a => <option key={a} value={a}>{roles[a] || a}</option>)}
              {/* A record check is arithmetic over rows, not an agent's conclusion. */}
              <option value="__none">Record checks (no agent)</option>
            </select>
          </label>
          {(fromDate || toDate || byAgent) &&
            <button className={control} onClick={() => { setFromDate(""); setToDate(""); setByAgent(""); }}>Clear</button>}
        </div>{!view.history.length && <p className="mt-3 text-sm text-ink-dim">Nothing yet. Approving or rejecting an agent&rsquo;s conclusion, recording a follow-up on a finding, and running the record checks all appear here.</p>}
        {!!view.history.length && !shownHistory.length && <p className="mt-3 text-sm text-ink-dim">Nothing in this range. The history holds the most recent hundred entries, so something older may exist and not be shown.</p>}
        {shownHistory.map(e => <div key={e.id} className="border-t border-line py-3 text-sm">
          <p>{e.summary || `${e.actor} · ${e.kind}`}</p>
          <p className="mt-1 text-xs text-ink-dim">{e.created_at.slice(0, 19).replace("T", " ")} · {e.kind} · {e.agent ? `raised by ${roles[e.agent] || e.agent}` : "record check, no agent"}</p>
        </div>)}</details>
      <details className="border border-line p-4" open><summary className="font-semibold">Scope & limitations</summary><ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-ink-dim">{view.limitations.map(l => <li key={l}>{l}</li>)}</ul></details>
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
    "## Live agent review", v.live ? `${v.live_stale ? "HISTORICAL SNAPSHOT — RERUN REQUIRED\n" : ""}${v.live.decisions} agent conclusion(s), ${v.live.escalated} escalated to a person. Each one is listed above with its evidence. No approval, posting or payment was made.` : "No live agent review has run.", "", "## Limitations", ...v.limitations.map(l => `- ${l}`)].join("\n");
}
