"use client";

import Link from "next/link";
import { useData } from "@/lib/data";
import { SherlockMark } from "@/components/SherlockMark";

export function Topbar() {
  const { ws, setWs, intakeWorkspaces, apiError } = useData();
  return (
    <header className="flex flex-wrap items-center gap-4 border-b border-line bg-surface px-4 py-3">
      <Link href="/" aria-label="Sherlock / Start here" className="flex items-center gap-2.5"><SherlockMark size={32} /><span className="text-lg font-semibold tracking-tight">Sherlock<span className="ml-2 text-xs font-normal text-ink-dim">Start here</span></span></Link>
      <nav aria-label="Main navigation" className="flex flex-wrap gap-3 text-sm"><Link href="/command">Records</Link><Link href="/scan">Scan</Link><Link href="/findings">Findings</Link><Link href="/reports">Reports</Link><Link href="/access">Access & data</Link></nav>
      <label className="ml-auto text-xs">Workspace <select aria-label="Workspace" value={ws} onChange={e => setWs(e.target.value)} className="ml-2 max-w-64 border border-line bg-white p-2 text-sm">
        <option value="sandbox">Fixed demo · Sandbox University</option><option value="mit">Public report example · MIT</option>
        {intakeWorkspaces.map(w => <option key={w.id} value={w.id}>{w.name} · {w.id.slice(-4)}</option>)}
      </select></label>
      {!ws.startsWith("ws-") && <p className="w-full text-xs text-amber-800">Example workspace: displayed findings and activity are bundled demonstrations, not a new analysis. <Link href="/" className="underline">Start an interactive fictional scan</Link>.</p>}
      {apiError && <p role="alert" className="w-full text-xs text-red-700">{apiError} · <Link href="/access" className="underline">Check access</Link></p>}
    </header>
  );
}
