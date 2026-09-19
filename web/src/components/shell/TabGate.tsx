"use client";

import { useData } from "@/lib/data";
import type { TabId } from "@/lib/types";

/** Renders children unless the active workspace disables this tab (e.g. MIT has no Approvals). */
export function TabGate({ tab, children }: { tab: TabId; children: React.ReactNode }) {
  const { bundle, setWs } = useData();
  if (!bundle.workspace.disabled_tabs.includes(tab)) return <>{children}</>;
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-2 text-center">
      <div className="text-3xl text-slate-300">⊘</div>
      <div className="font-semibold">Not available for {bundle.workspace.name}</div>
      <p className="max-w-sm text-[12.5px] text-slate-500">
        This is a read-only public report. Agents can read and reconcile it, but there are no transactions to
        run workflows on, approve, or learn from.
      </p>
      <button
        type="button"
        onClick={() => setWs("sandbox")}
        className="mt-1 cursor-pointer rounded-[7px] bg-teal-700 px-3 py-1.5 text-[11.5px] font-semibold text-white"
      >
        Switch to Sandbox University
      </button>
    </div>
  );
}
