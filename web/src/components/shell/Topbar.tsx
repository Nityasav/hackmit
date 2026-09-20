"use client";

import Link from "next/link";
import { useData } from "@/lib/data";
import { SherlockMark } from "@/components/SherlockMark";

export function Topbar() {
  const { ws, setWs, intakeWorkspaces, apiError } = useData();
  return (
    <header className="flex flex-wrap items-center gap-4 border-b border-line bg-surface px-4 py-3">
      <Link href="/" aria-label="Sherlock / Start here" className="flex shrink-0 items-center gap-2.5"><SherlockMark size={28} /><span className="text-xl font-semibold leading-none tracking-[-0.035em]">Sherlock</span></Link>
      <label className="ml-auto text-xs">Workspace <select aria-label="Workspace" value={ws} onChange={e => setWs(e.target.value)} className="ml-2 max-w-64 border border-line bg-white p-2 text-sm">
        <option value="sandbox">Fixed demo · Sandbox University</option><option value="mit">Public report example · MIT</option>
        {intakeWorkspaces.map(w => <option key={w.id} value={w.id}>{w.name} · {w.id.slice(-4)}</option>)}
      </select></label>
      {!ws.startsWith("ws-") && <p className="w-full text-xs text-amber-800">Example workspace: displayed findings and activity are bundled demonstrations, not a new analysis. <Link href="/" className="underline">Start an interactive fictional scan</Link>.</p>}
      {apiError && <p role="alert" className="w-full text-xs text-red-700">{apiError} · <Link href="/access" className="underline">Check access</Link></p>}
    </header>
  );
}
