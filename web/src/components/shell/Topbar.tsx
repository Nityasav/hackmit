"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useData } from "@/lib/data";
import { Pill, Pulse } from "@/components/ui";

const MODE_LABEL = { live: "Live run", recorded: "Recorded run", scripted: "Scripted preview", not_started: "No agent run yet" } as const;

export function Topbar() {
  const router = useRouter();
  const { bundle, source, apiError } = useData();
  const [q, setQ] = useState("");
  const working = bundle.agents.filter((a) => a.status === "working").length;
  const pending = bundle.approvals.filter((a) => a.status === "pending").length;
  const isPublic = bundle.workspace.kind === "public";

  return (
    <header className="flex items-center gap-2.5 border-b border-line bg-white px-4 py-2.5">
      <form
        className="flex flex-1 items-center gap-2 rounded-lg border border-line bg-slate-50 px-2.5 py-1.5 focus-within:border-teal-400"
        onSubmit={(e) => {
          e.preventDefault();
          router.push(`/reasoning?q=${encodeURIComponent(q)}`);
        }}
      >
        <span className="text-teal-700">✦</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask your finance team why… e.g. “why was INV-2291 cleared?”"
          className="w-full bg-transparent text-[12.5px] outline-none placeholder:text-slate-400"
        />
      </form>

      {working > 0 ? (
        <span className="flex items-center gap-1.5 whitespace-nowrap rounded-full bg-emerald-50 px-2.5 py-1 text-[11.5px] font-semibold text-teal-700">
          <Pulse />
          {working} agents working
        </span>
      ) : (
        <span className="whitespace-nowrap rounded-full bg-slate-100 px-2.5 py-1 text-[11.5px] font-semibold text-slate-600">
          Agents idle
        </span>
      )}

      {!isPublic && (
        <Link
          href="/approvals"
          className="whitespace-nowrap rounded-full bg-amber-100 px-2.5 py-1 text-[11.5px] font-semibold text-amber-800"
        >
          {pending} need you
        </Link>
      )}

      <Pill tone={isPublic ? "green" : "amber"}>{isPublic ? "Public report" : "Synthetic scenario"}</Pill>
      <Pill tone="blue">
        {MODE_LABEL[bundle.workspace.mode]}
      </Pill>
      {source === "api" && <Pill tone={apiError ? "red" : "teal"}>{apiError ? "API offline" : "Live API"}</Pill>}
    </header>
  );
}
