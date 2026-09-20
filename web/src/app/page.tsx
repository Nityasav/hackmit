"use client";

import Link from "next/link";
import { SourcesPanel } from "@/components/SourcesPanel";
import { useData } from "@/lib/data";

/**
 * Books — the only place data enters the product.
 *
 * The uploader is the page: one sentence saying what this is, then the real
 * records panel. Nothing here explains the navigation; there are three
 * destinations and they are on the left.
 */
export default function BooksPage() {
  const { ws } = useData();

  return (
    <div className="mx-auto max-w-6xl space-y-8 pb-10">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-ink-dim">SchoolTrace</p>
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

      {/* Keyed so switching schools resets the upload draft rather than carrying
          another institution's staged files across. */}
      <SourcesPanel key={ws} />

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
