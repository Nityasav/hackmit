"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function Topbar() {
  const router = useRouter();
  const [q, setQ] = useState("");

  return (
    <header className="flex items-center gap-2.5 border-b border-line bg-surface px-4 py-2.5">
      <form
        className="flex flex-1 items-center gap-2 rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 focus-within:border-teal-400/70"
        onSubmit={(e) => {
          e.preventDefault();
          router.push(`/reasoning?q=${encodeURIComponent(q)}`);
        }}
      >
        <span className="text-teal-300">✦</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask your finance team why… e.g. “why was INV-2291 cleared?”"
          className="w-full bg-transparent text-[12.5px] outline-none placeholder:text-ink-faint"
        />
      </form>
    </header>
  );
}
