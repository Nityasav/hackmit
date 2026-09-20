"use client";

import Link from "next/link";
import { useData } from "@/lib/data";

export function Topbar() {
  const { ws, setWs, intakeWorkspaces, apiError } = useData();
  return (
    <header className="flex flex-wrap items-center gap-4 border-b border-line bg-surface px-4 py-3">
      <Link href="/" className="font-semibold">SchoolTrace / Start here</Link>
      <nav aria-label="Main navigation" className="flex flex-wrap gap-3 text-sm"><Link href="/command">Records</Link><Link href="/scan">Scan</Link><Link href="/findings">Findings</Link><Link href="/reports">Director briefing</Link><Link href="/access">Access & data</Link></nav>
      <label className="ml-auto text-xs">Workspace <select aria-label="Workspace" value={ws} onChange={e => setWs(e.target.value)} className="ml-2 max-w-64 border border-line bg-white p-2 text-sm">
        {intakeWorkspaces.length === 0 && <option value="">No workspace yet</option>}
        {intakeWorkspaces.map(w => <option key={w.id} value={w.id}>{w.name} · {w.id.slice(-4)}</option>)}
      </select></label>
      {intakeWorkspaces.length === 0 && <p className="w-full text-xs text-ink-dim">No workspace yet. <Link href="/" className="underline">Create one and upload records</Link> to start a review.</p>}
      {apiError && <p role="alert" className="w-full text-xs text-red-700">{apiError} · <Link href="/access" className="underline">Check access</Link></p>}
    </header>
  );
}
