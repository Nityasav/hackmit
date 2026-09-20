"use client";

import { Vault } from "@/components/files/Vault";
import { useData } from "@/lib/data";

export default function FilesPage() {
  const { ws } = useData();
  return (
    <div className="mx-auto max-w-6xl pb-16">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-ink-dim">Files</p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
          What this review is built on.
        </h1>
        <p className="mt-5 max-w-2xl text-[17px] leading-relaxed text-ink-dim">
          Every file you uploaded, every check that reads it, and everything a check still needs.
          Turn it around, then click anything to see what it is and what depends on it.
        </p>
      </header>
      <div className="mt-8">
        <Vault key={ws} ws={ws} />
      </div>
    </div>
  );
}
