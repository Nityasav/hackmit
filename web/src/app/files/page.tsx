"use client";

import { FileLibrary } from "@/components/files/FileLibrary";
import { useData } from "@/lib/data";

export default function FilesPage() {
  const { ws } = useData();
  return (
    <div className="mx-auto max-w-6xl pb-16">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-ink-dim">Files</p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
          Everything you have uploaded.
        </h1>
        <p className="mt-5 max-w-2xl text-[17px] leading-relaxed text-ink-dim">
          Every document read for this institution and every file its records were parsed out of.
          Open one to see what it holds, or read the map to see which file came from which document.
        </p>
      </header>
      <div className="mt-8">
        <FileLibrary key={ws} ws={ws} />
      </div>
    </div>
  );
}
