"use client";

import Link from "next/link";
import { useState } from "react";

import { DocumentIntake } from "@/components/DocumentIntake";
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
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-ink-dim">Sherlock</p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight md:text-5xl">
          An Office of the CFO for schools,
          <br />
          <span className="text-ink-dim">run by AI agents.</span>
        </h1>
        <p className="mt-5 max-w-xl text-lg leading-relaxed text-ink-dim">
          Add this school&rsquo;s records below. Five agents investigate them, show the line every number came
          from, check each other&rsquo;s work, and hand you a decision to make.
        </p>
      </header>

      {/* What to do next, and where that sits in the whole job. */}
      <GuidedWorkflow bundle={bundle} intake={intake} />

      {/* Keyed so switching schools resets the upload draft rather than carrying
          another institution's staged files across. */}
      <SourcesPanel key={ws} onProgressChange={setIntake} />

      <section id="source-documents" className="scroll-mt-4">
        <h2 className="text-base font-semibold">3. A PDF, a photo or a scan</h2>
        <p className="mb-3 mt-1 max-w-prose text-[13px] leading-relaxed text-ink-dim">
          Not everything arrives as a spreadsheet. Upload the document, check every value it produced against the
          page it came from, then stage it for the import above. The original file is kept exactly as you gave it,
          and every record made from it can be traced back to the page and character it was read from.
        </p>
        <DocumentIntake key={ws} />
      </section>

      <footer className="border-t border-line pt-5 text-sm text-ink-dim">
        <p>
          A bounded management-review tool&mdash;not an audit opinion, fraud detector or accounting system. Use
          fictional or approved public information only. Do not upload confidential school-board data.
        </p>
        <Link href="/access" className="mt-3 inline-block underline">
          Access, privacy &amp; deleting a workspace
        </Link>
      </footer>
    </div>
  );
}
