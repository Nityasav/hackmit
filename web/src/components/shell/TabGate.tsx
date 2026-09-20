"use client";

import { useData } from "@/lib/data";
import Link from "next/link";
import type { TabId } from "@/lib/types";

/** Renders children unless the active workspace disables this tab (e.g. MIT has no Approvals). */
export function TabGate({ tab, children }: { tab: TabId; children: React.ReactNode }) {
  const { bundle, setWs } = useData();
  if (!bundle.workspace.disabled_tabs.includes(tab)) return <>{children}</>;
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-2 text-center">
      <div className="text-3xl text-ink-faint">⊘</div>
      <div className="font-semibold">Not available for {bundle.workspace.name}</div>
      <p className="max-w-sm text-[14px] text-ink-dim">
        {bundle.workspace.intake
          ? "Records, connected investigations and human follow-up are available in the guided review. Automatic learning and model training are not enabled. No playbook silently changes future conclusions."
          : "This is a read-only public report. There are no transactions to run workflows on, approve, or learn from."}
      </p>
      {bundle.workspace.intake && <Link href="/scan" className="text-sm text-teal-700 underline">Open the guided review</Link>}
      <button
        type="button"
        onClick={() => setWs("sandbox")}
        className="mt-1 cursor-pointer rounded-none bg-ink px-3 py-2.5 text-[13.5px] font-semibold text-white"
      >
        Switch to Sandbox University
      </button>
    </div>
  );
}
