"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { intakeApi, useData } from "@/lib/data";

export default function Home() {
  const { setWs, refreshWorkspaces, intakeWorkspaces } = useData();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Loads the sample record set through the same import, mapping and commit
  // path as your own files. Nothing about the result is precomputed.
  async function loadSample() {
    setBusy(true);
    setError("");
    try {
      const result = await intakeApi<{ workspace: string }>("/api/review-demo", { method: "POST" });
      await refreshWorkspaces();
      setWs(result.workspace);
      router.push("/scan");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the sample records");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl py-6">
      <p className="text-xs font-semibold uppercase tracking-[0.25em] text-ink-dim">
        SchoolTrace / your finance review desk
      </p>

      <section className="mt-6">
        <h1 className="max-w-3xl text-4xl font-semibold leading-tight md:text-6xl">
          Know what needs attention.
          <br />
          <span className="text-ink-dim">See the evidence behind it.</span>
        </h1>
        <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-dim">
          Turn a school&rsquo;s financial records into a reviewable list of questions, checks and
          next steps. Inspect every source. Ask your finance team for missing evidence. Keep the
          final decision human.
        </p>

        <div className="mt-7 flex flex-wrap gap-3">
          <Link className="bg-ink px-6 py-4 font-semibold text-white" href="/command">
            {intakeWorkspaces.length ? "Open your workspace" : "Create a workspace →"}
          </Link>
          <button
            disabled={busy}
            onClick={() => void loadSample()}
            className="border border-line px-6 py-4 disabled:opacity-50"
          >
            {busy ? "Importing sample records & running checks…" : "Load sample records"}
          </button>
        </div>
        <p className="mt-3 text-xs text-ink-dim">
          Fictional USD school district sample · no payment execution
        </p>
        {error && (
          <p role="alert" className="mt-4 text-red-700">
            {error} <Link className="underline" href="/access">Check access &amp; sign in</Link>
          </p>
        )}
      </section>

      <section className="mt-12 border-t border-line pt-7">
        <h2 className="text-2xl font-semibold">Where do I go?</h2>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          {[
            ["Records & overview", "Create a workspace, upload files, check coverage and commit a snapshot.", "/command"],
            ["Scan & findings", "Run checks, investigate exceptions and open the original evidence.", "/scan"],
            ["Follow-up", "Assign an owner, request support or record a proposed correction.", "/board"],
            ["Director briefing", "Export a briefing with unresolved issues and stated limitations.", "/reports"],
            ["Live agent team", "Ask the CFO, AP, Payroll, Grants and Auditor to review a committed snapshot.", "/cfo"],
            ["Access & data", "Understand limits, sign in, or delete a workspace.", "/access"],
          ].map(([title, text, href]) => (
            <Link key={href} href={href} className="border border-line p-5 transition-colors hover:bg-surface-2">
              <h3 className="font-semibold">{title} ↗</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-dim">{text}</p>
            </Link>
          ))}
        </div>
      </section>

      <p className="mt-8 border-t border-line pt-5 text-sm text-ink-dim">
        A bounded management-review tool&mdash;not an audit opinion, fraud detector or accounting
        system. Use fictional or approved public information only. Do not upload confidential
        school-board data.
      </p>
    </div>
  );
}
