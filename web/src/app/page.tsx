"use client";

import Link from "next/link";
import { useState } from "react";

import { DocumentIntake } from "@/components/DocumentIntake";
import { RecordsBrowser } from "@/components/RecordsBrowser";
import { GuidedWorkflow } from "@/components/GuidedWorkflow";
import { SourcesPanel } from "@/components/SourcesPanel";
import { useData } from "@/lib/data";
import type { IntakeUiProgress } from "@/lib/workflow";

/**
 * Books — the only place data enters the product.
 *
 * The uploader is the page: one sentence saying what this is, the step you are
 * on, then the real records panel. Nothing here explains the navigation; there
 * are three destinations and they are on the left.
 */
export default function BooksPage() {
  const { ws, bundle } = useData();
  const [intake, setIntake] = useState<IntakeUiProgress | null>(null);

  return (
    <div className="mx-auto max-w-6xl space-y-8 pb-10">
      <header>
        <h1 className="max-w-3xl text-4xl font-semibold leading-tight md:text-5xl">
          Upload your records.
          <br />
          {/* Playfair italic: the high-contrast serif carries the second line,
              so the pair reads as one sentence in two voices. */}
          <span className="font-accent text-[1.12em] font-normal italic tracking-[-0.01em] text-ink">
            Start a review.
          </span>
        </h1>
        <p className="mt-5 max-w-xl text-lg leading-relaxed text-ink-dim">
          Upload your records, check the import, then start an investigation.
        </p>
      </header>

      <GuidedWorkflow bundle={bundle} intake={intake} />

      {/* Keyed so switching workspaces resets the upload draft rather than carrying
          another company's staged files across. */}
      <SourcesPanel key={ws} onProgressChange={setIntake} />

      <section id="source-documents" className="scroll-mt-4">
        <h2 className="text-base font-semibold">Documents</h2>
        <p className="mb-3 mt-1 max-w-prose text-[13px] leading-relaxed text-ink-dim">
          Upload a PDF, review its extracted values, then import.
        </p>
        <DocumentIntake key={ws} />
      </section>

      <section id="source-registers-section" className="scroll-mt-4">
        <h2 className="text-base font-semibold">Search the records</h2>
        <p className="mb-3 mt-1 max-w-prose text-[13px] leading-relaxed text-ink-dim">
          Filter transactions by date and export a spreadsheet.
        </p>
        <RecordsBrowser key={ws} />
      </section>

      <footer className="border-t border-line pt-5 text-sm text-ink-dim">
        <p>
          Reviews cover the records you supply and do not constitute an audit opinion.
        </p>
        <Link href="/access" className="mt-3 inline-block underline">
          Access &amp; data settings
        </Link>
      </footer>
    </div>
  );
}
