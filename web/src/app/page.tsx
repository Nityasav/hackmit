"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { intakeApi, useData } from "@/lib/data";

export default function Home() {
  const { setWs, refreshWorkspaces } = useData(); const router = useRouter();
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function demo() {
    setBusy(true); setError("");
    try { const result = await intakeApi<{ workspace: string }>("/api/review-demo", { method: "POST" }); await refreshWorkspaces(); setWs(result.workspace); router.push("/scan"); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not start demo"); setBusy(false); }
  }
  return <div className="mx-auto max-w-6xl py-6"><p className="text-xs font-semibold uppercase tracking-[0.25em] text-ink-dim">SchoolTrace / your finance review desk</p>
    <div className="mt-6 grid gap-10 lg:grid-cols-[1.4fr_1fr]"><section><h1 className="max-w-3xl text-4xl font-semibold leading-tight md:text-6xl">Know what needs attention.<br /><span className="text-ink-dim">See the evidence behind it.</span></h1>
      <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-dim">Turn a school’s financial records into a reviewable list of questions, checks and next steps. Inspect every source. Ask your finance team for missing evidence. Keep the final decision human.</p>
      <div className="mt-7 flex flex-wrap gap-3"><button disabled={busy} onClick={() => void demo()} className="bg-ink px-6 py-4 font-semibold text-white disabled:opacity-50">{busy ? "Importing fictional records & running checks…" : "Try the guided financial scan →"}</button><Link className="border border-line px-6 py-4" href="/command">Use my own sample records</Link></div>
      <p className="mt-3 text-xs text-ink-dim">Local demo · fictional USD school district · no API key needed for record checks · no payment execution</p>
      {error && <p role="alert" className="mt-4 text-red-700">{error} <Link className="underline" href="/access">Check access & sign in</Link></p>}</section>
      <aside className="border border-line bg-surface-2 p-7"><p className="text-xs uppercase tracking-widest">Judge’s challenge / about 3 minutes</p><h2 className="mt-3 text-2xl font-semibold">Could you explain this month’s exceptions to the board?</h2>
        <ol className="mt-6 list-decimal space-y-5 pl-5"><li>Scan the fictional September records.</li><li>Find the repeated invoice. Open its original source.</li><li>Assign follow-up, then add the withheld service memo.</li><li>Rescan. Notice what changed—and what is still unproven.</li><li>Export your director briefing.</li></ol><p className="mt-6 border-t border-line pt-4 text-sm text-ink-dim">Want to see the agents reason? Start the optional live five-agent review from the scan page. Provider calls are separate and explicitly labelled.</p></aside></div>
    <section className="mt-12 border-t border-line pt-7"><h2 className="text-2xl font-semibold">Where do I go?</h2><div className="mt-5 grid gap-4 md:grid-cols-3">
      {[["01", "Records & overview", "Create a workspace, upload files, check coverage and commit a snapshot.", "/command"], ["02", "Scan & findings", "Run checks, investigate exceptions and open the original evidence.", "/scan"], ["03", "Follow-up & decisions", "Assign an owner, request support or record a proposed correction.", "/approvals"], ["04", "Director reports", "Get an exportable briefing with unresolved issues and limitations.", "/reports"], ["05", "Live agent team", "Ask the CFO, AP, Payroll, Grants and Auditor to review a committed snapshot.", "/cfo"], ["06", "Access & data", "Understand demo limits, sign in when configured, or delete a workspace.", "/access"]].map(([n, title, text, href]) => <Link key={href} href={href} className="border border-line p-5 transition-colors hover:bg-surface-2"><span className="font-num text-xs text-ink-dim">{n}</span><h3 className="mt-2 font-semibold">{title} ↗</h3><p className="mt-2 text-sm leading-relaxed text-ink-dim">{text}</p></Link>)}</div></section>
    <p className="mt-8 border-t border-line pt-5 text-sm text-ink-dim">A bounded management-review prototype—not an audit opinion, fraud detector or Ontario accounting system. Use fictional or approved public information only. Do not upload confidential school-board data.</p>
  </div>;
}
