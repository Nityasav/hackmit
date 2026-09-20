"use client";

import Link from "next/link";
import { useData } from "@/lib/data";
import { HelpGuide } from "@/components/HelpGuide";

/**
 * One bar, two jobs: which school's books you are looking at, and the way back
 * to the walkthrough. Navigation lives in the sidebar and nowhere else.
 */
export function Topbar() {
  const { ws, setWs, intakeWorkspaces, apiError } = useData();
  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-line bg-surface px-6 py-3">
      <label className="flex items-center gap-2 text-xs text-ink-dim">
        School
        <select
          aria-label="School"
          value={ws}
          onChange={(e) => setWs(e.target.value)}
          className="max-w-64 border border-line bg-white px-2 py-1.5 text-sm text-ink"
        >
          {intakeWorkspaces.length === 0 && <option value="">No school added yet</option>}
          {intakeWorkspaces.map((w) => (
            <option key={w.id} value={w.id}>{w.name} · {w.id.slice(-4)}</option>
          ))}
        </select>
      </label>
      {intakeWorkspaces.length === 0 && (
        <p className="text-xs text-ink-dim">
          <Link href="/" className="underline">Add a school&rsquo;s records</Link> to start.
        </p>
      )}
      <div className="ml-auto">
        <HelpGuide />
      </div>
      {apiError && (
        <p role="alert" className="w-full text-xs text-red-700">
          {apiError} · <Link href="/access" className="underline">Check access</Link>
        </p>
      )}
    </header>
  );
}
