"use client";

import { useEffect, useState } from "react";

import { API_URL, intakeApi, useData } from "@/lib/data";
import type { Coverage, SourceDetail } from "@/lib/types";
import { Button } from "@/components/ui";

const ROLE_LABEL: Record<string, string> = {
  chart: "Chart of accounts", opening: "Opening balances", ledger: "General ledger",
  payroll: "Payroll", grants: "Grant register", budget: "Budget", invoice: "Invoices",
  fees: "Student fees", collections: "Collections (money received)", deposits: "Bank deposits",
  sponsorships: "Sponsorships & pledges", service: "Service records",
  policy: "Award terms / policy", document: "Document",
};

/**
 * Every file this school's review is built on.
 *
 * Findings cite a source and a line, so being able to open that exact file and
 * read the line yourself is the whole promise. This is where to do that without
 * going through a finding first.
 */
export function FileBrowser({ ws }: { ws: string }) {
  const { apiError } = useData();
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [open, setOpen] = useState<SourceDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ws) return;
    let mounted = true;
    intakeApi<Coverage>(`/api/workspaces/${encodeURIComponent(ws)}/coverage`)
      .then((next) => { if (mounted) setCoverage(next); })
      .catch(() => { /* The shared status line reports outages. */ });
    return () => { mounted = false; };
  }, [ws]);

  async function read(id: string) {
    setBusy(id);
    setError("");
    try {
      setOpen(await intakeApi<SourceDetail>(`/api/workspaces/${encodeURIComponent(ws)}/sources/${encodeURIComponent(id)}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "That file could not be opened.");
    } finally {
      setBusy(null);
    }
  }

  const sources = coverage?.sources ?? [];
  const active = sources.filter((s) => s.active);
  const superseded = sources.filter((s) => !s.active);

  if (!ws) {
    return (
      <p className="border border-line bg-surface-2 p-5 text-[14px]">
        No school selected yet. Add one on Books to upload records.
      </p>
    );
  }

  return (
    <div className="grid gap-8 min-[980px]:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <section>
        <div className="flex items-baseline gap-3">
          <h2 className="text-[15px] font-semibold">In this review</h2>
          <span className="font-accent text-[13px] text-ink-dim">
            {active.length} {active.length === 1 ? "file" : "files"}
          </span>
        </div>

        {active.length === 0 && (
          <p className="mt-3 border border-line bg-surface-2 p-5 text-[14px]">
            Nothing committed yet. Upload records on Books and commit them; they appear here with
            the line numbers every finding points back to.
          </p>
        )}

        <ul className="mt-3 grid gap-2">
          {active.map((s) => (
            <li key={s.id}>
              <button
                onClick={() => void read(s.id)}
                disabled={busy === s.id}
                className="flex w-full items-center justify-between gap-3 border border-line bg-surface p-3 text-left hover:bg-surface-2 disabled:opacity-50"
              >
                <span className="min-w-0">
                  <span className="block truncate text-[14px] font-semibold">{s.name}</span>
                  <span className="block text-[12.5px] text-ink-dim">{ROLE_LABEL[s.role] ?? s.role}</span>
                </span>
                <span className="shrink-0 font-accent text-[12.5px] text-ink-dim">
                  {busy === s.id ? "Opening…" : "Read"}
                </span>
              </button>
            </li>
          ))}
        </ul>

        {superseded.length > 0 && (
          <details className="mt-5">
            <summary className="cursor-pointer text-[13px] text-ink-dim">
              {superseded.length} replaced by a later upload
            </summary>
            <ul className="mt-2 grid gap-1">
              {superseded.map((s) => (
                <li key={s.id} className="border border-line p-2 text-[13px] text-ink-dim">
                  {s.name} · {ROLE_LABEL[s.role] ?? s.role}
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <section>
        <h2 className="text-[15px] font-semibold">What the agents read</h2>
        {error && <p role="alert" className="mt-3 bg-red-50 p-3 text-[13px] text-accent-bad">{error}</p>}
        {apiError && !error && (
          <p role="alert" className="mt-3 bg-red-50 p-3 text-[13px] text-accent-bad">{apiError}</p>
        )}

        {!open ? (
          <p className="mt-3 border border-line bg-surface-2 p-5 text-[14px]">
            Choose a file to see it exactly as the agents do, line by line. Findings cite these
            line numbers.
          </p>
        ) : (
          <div className="mt-3 border border-line bg-surface p-4">
            <div className="flex flex-wrap items-baseline gap-2">
              <b className="text-[14px]">{open.name}</b>
              <span className="font-accent text-[12.5px] text-ink-dim">
                {open.line_count} {open.line_count === 1 ? "line" : "lines"}
              </span>
            </div>
            <p className="mt-1 break-all font-accent text-[12px] text-ink-faint">
              sha256 {open.sha256.slice(0, 16)}
            </p>

            <pre className="mt-3 max-h-[26rem] overflow-auto whitespace-pre-wrap border border-line bg-surface-2 p-3 text-[12.5px] leading-relaxed">
              {open.lines.map((l) => `${String(l.number).padStart(4, " ")}  ${l.text}`).join("\n")}
            </pre>
            {open.lines.length < open.line_count && (
              <p className="mt-2 text-[12.5px] text-ink-dim">
                Showing the first {open.lines.length} of {open.line_count} lines.
              </p>
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <a
                href={`${API_URL}/api/workspaces/${encodeURIComponent(ws)}/sources/${encodeURIComponent(open.id)}/download`}
                className="border border-line px-3 py-2 text-[13px] hover:bg-surface-2"
              >
                Download this file
              </a>
              <Button onClick={() => setOpen(null)}>Close</Button>
              {open.extraction_origin && (
                <span className="font-accent text-[12.5px] text-ink-dim">
                  Read from {open.extraction_origin.name}
                </span>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
