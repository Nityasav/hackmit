"use client";

import { useState } from "react";

import { AnimatedDropdown } from "@/components/ui/animated-dropdown";
import { STARTER_PACKS, packFiles, type Period } from "@/lib/starterPacks";
import type { SourceRole } from "@/lib/types";

/**
 * Sample records to try the product with before you have files of your own.
 *
 * Loading a pack only fills the file chooser below it: the files are staged,
 * mapped, validated and committed exactly like uploaded ones, and nothing is
 * committed here. They are fictional, and the panel says so where someone will
 * read it rather than in a footnote.
 */
export function StarterPacks({
  period,
  disabled,
  onLoad,
}: {
  period: Period | null;
  disabled: boolean;
  onLoad: (files: { file: File; role: SourceRole }[]) => void;
}) {
  const [selected, setSelected] = useState(STARTER_PACKS[0].id);
  const pack = STARTER_PACKS.find((p) => p.id === selected) ?? STARTER_PACKS[0];

  return (
    <div className="mt-5 border border-line bg-surface-2 p-4">
      <h3 className="font-semibold">No records to hand? Start from a sample pack</h3>
      <p className="my-2 max-w-prose text-xs text-ink-dim">
        Fictional records for a school that does not exist, written against this workspace&rsquo;s own period so
        the dates land inside it. They load into the file chooser below; you still preview the import and commit
        it yourself.
      </p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <AnimatedDropdown
          aria-label="Starter pack"
          className="w-full"
          options={STARTER_PACKS.map((option) => ({ value: option.id, label: option.label }))}
          value={selected}
          disabled={disabled}
          onChange={setSelected}
        />
        <button
          type="button"
          className="whitespace-nowrap border border-line bg-white px-3 py-2 text-xs font-semibold hover:bg-surface-3 disabled:opacity-40"
          disabled={disabled || !period}
          onClick={() => period && onLoad(packFiles(pack, period))}
        >
          Load these files
        </button>
      </div>
      <p className="mt-3 text-xs text-ink-dim">{pack.summary}</p>
      <p className="mt-2 text-[11px] text-ink-dim"><b>What a review should find:</b> {pack.expect}</p>
      {!period && <p className="mt-2 text-xs text-amber-700">Create an institution first; the pack is dated from its review period.</p>}
    </div>
  );
}
