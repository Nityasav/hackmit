"use client";

import Link from "next/link";
import { useData } from "@/lib/data";
import { HelpGuide } from "@/components/HelpGuide";
import { AnimatedDropdown } from "@/components/ui/animated-dropdown";

/**
 * One bar, two jobs: which company's books you are looking at, and the way back
 * to the walkthrough. Navigation lives in the sidebar and nowhere else.
 */
export function Topbar() {
  const { ws, setWs, intakeWorkspaces, apiError } = useData();
  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-line bg-surface px-6 py-3">
      <label className="flex items-center gap-2 text-xs text-ink-dim">
        Company
        <AnimatedDropdown
          aria-label="Company"
          value={ws}
          onChange={setWs}
          placeholder="No company added yet"
          options={intakeWorkspaces.map((w) => ({
            value: w.id,
            label: `${w.name} · ${w.id.slice(-4)}`,
          }))}
          className="max-w-64"
        />
      </label>
      {intakeWorkspaces.length === 0 && (
        <p className="text-xs text-ink-dim">
          <Link href="/" className="underline">Add a company&rsquo;s records</Link> to start.
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
