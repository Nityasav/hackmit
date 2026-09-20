"use client";

import { FileBrowser } from "@/components/files/FileBrowser";
import { useData } from "@/lib/data";

export default function FilesPage() {
  const { ws } = useData();
  return (
    <div className="mx-auto max-w-5xl pb-16">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-ink-dim">Files</p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
          Every file this review is built on.
        </h1>
        <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-ink-dim">
          Open any of them and read the same lines the agents read. Nothing here is a summary:
          it is the file you uploaded.
        </p>
      </header>
      <div className="mt-10">
        <FileBrowser key={ws} ws={ws} />
      </div>
    </div>
  );
}
