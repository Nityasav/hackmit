"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useData } from "@/lib/data";
import { TABS } from "@/lib/tabs";
import type { WorkspaceId } from "@/lib/types";

const WORKSPACES: { id: WorkspaceId; name: string; sub: string }[] = [
  { id: "mit", name: "MIT FY2025", sub: "Public report · read-only" },
  { id: "sandbox", name: "Sandbox University", sub: "Synthetic · September close" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { ws, setWs, bundle } = useData();
  const [open, setOpen] = useState(false);
  const pending = bundle.approvals.filter((a) => a.status === "pending").length;
  const current = WORKSPACES.find((w) => w.id === ws)!;
  const groups = [...new Set(TABS.map((t) => t.group))];

  return (
    <aside className="flex w-[210px] flex-none flex-col border-r border-line bg-white px-2.5 py-3.5">
      <Link href="/" className="flex items-center gap-2 px-1 pb-3 text-[15px] font-bold">
        <i className="inline-block h-[18px] w-[18px] rounded-[5px] bg-gradient-to-br from-teal-700 to-teal-500" />
        SchoolTrace
      </Link>

      <div className="relative mb-2">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full cursor-pointer rounded-lg border border-line px-2.5 py-1.5 text-left text-xs font-semibold hover:border-teal-300"
        >
          {current.name} <span className="float-right text-slate-400">▾</span>
          <small className="block font-normal text-slate-500">{current.sub}</small>
        </button>
        {open && (
          <div className="absolute inset-x-0 top-full z-20 mt-1 overflow-hidden rounded-lg border border-line bg-white shadow-lg">
            {WORKSPACES.map((w) => (
              <button
                key={w.id}
                type="button"
                onClick={() => {
                  setWs(w.id);
                  setOpen(false);
                }}
                className={`block w-full cursor-pointer px-2.5 py-2 text-left text-xs hover:bg-slate-50 ${w.id === ws ? "bg-teal-50" : ""}`}
              >
                <b className="font-semibold">{w.name}</b>
                <small className="block text-slate-500">{w.sub}</small>
              </button>
            ))}
          </div>
        )}
      </div>

      <nav className="flex flex-col">
        {groups.map((g) => (
          <div key={g}>
            <div className="px-2 pb-1 pt-2.5 text-[10px] uppercase tracking-wider text-slate-400">{g}</div>
            {TABS.filter((t) => t.group === g).map((t) => {
              const active = t.href === "/" ? pathname === "/" : pathname.startsWith(t.href);
              const disabled = bundle.workspace.disabled_tabs.includes(t.id);
              return (
                <Link
                  key={t.id}
                  href={t.href}
                  className={`flex items-center gap-2 rounded-[7px] px-2.5 py-[7px] text-[12.5px] font-medium ${
                    active ? "bg-emerald-50 text-teal-700" : disabled ? "text-slate-300" : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {t.label}
                  {disabled ? (
                    <span className="ml-auto text-[11px]" title="Not available for public reports">
                      ⊘
                    </span>
                  ) : t.id === "approvals" && pending > 0 ? (
                    <span className="ml-auto rounded-full bg-teal-700 px-1.5 text-[10px] text-white">{pending}</span>
                  ) : t.tag ? (
                    <span className="ml-auto rounded bg-teal-100 px-1 text-[9px] font-bold text-teal-700">{t.tag}</span>
                  ) : null}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="mt-auto border-t border-slate-100 p-2 text-[10.5px] text-slate-500">
        5 agents · {bundle.workspace.model}
        <br />
        Run budget: {bundle.workspace.run_budget.used} / {bundle.workspace.run_budget.total} tool calls
      </div>
    </aside>
  );
}
