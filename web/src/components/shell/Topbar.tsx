"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useData } from "@/lib/data";

export function Topbar() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const { bundle } = useData();
  const recorded = bundle.workspace.recorded_from;

  return (
    <header className="border-b border-line bg-surface">
      {/* A recording should never be mistaken for a run happening now. */}
      {recorded && (
        <div className="border-b border-line bg-surface-2 px-4 py-1.5 text-[12.5px] text-ink-dim">
          <b className="text-ink">Recorded workspace.</b> Nothing here is running: this is {recorded}.
        </div>
      )}
      <div className="flex items-center gap-4 px-4 py-2.5">
      <form
        className="flex flex-1 items-center gap-2 rounded-lg border border-line bg-surface-2 px-2.5 py-2.5 focus-within:border-ink"
        onSubmit={(e) => {
          e.preventDefault();
          router.push(`/reasoning?q=${encodeURIComponent(q)}`);
        }}
      >
        <span className="text-ink">✦</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask your finance team why… e.g. “why was INV-2291 cleared?”"
          className="w-full bg-transparent text-[14px] outline-none placeholder:text-ink-faint"
        />
      </form>
      </div>
    </header>
  );
}
