"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, intakeApi } from "@/lib/api";
import { Pill } from "@/components/ui";
import type { Deliverable, DeliverableRow } from "@/lib/types";

import { Deck } from "./Deck";
import { Snapshot } from "./Snapshot";

/**
 * The documents someone asked for.
 *
 * Nothing appears here on its own. A workspace with no deliverables shows an empty state
 * that says how to get one, rather than a document nobody wanted — producing one for
 * every company would fill the screen with artifacts and bury the ones that were
 * actually requested.
 *
 * Each row opens the document exactly as it was when it was made. The payload is frozen
 * at creation, so reopening a report next week shows what it said, not what the books
 * say now.
 */

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-US", {
    day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
  });

function reason(error: unknown, fallback: string) {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : fallback;
}

export function Deliverables({ ws }: { ws: string }) {
  const [rows, setRows] = useState<DeliverableRow[]>([]);
  const [open, setOpen] = useState<Deliverable | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const body = await intakeApi<{ deliverables: DeliverableRow[] }>(
      `/api/workspaces/${ws}/deliverables`);
    setRows(body.deliverables);
  }, [ws]);

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        await load();
        if (live) setError("");
      } catch (e) {
        if (live) setError(reason(e, "The deliverables could not be read"));
      } finally {
        if (live) setLoading(false);
      }
    })();
    // Polled, because the document is produced by the chat on another tab. Without this
    // you ask for a report and this screen keeps saying nobody asked for one.
    const timer = setInterval(() => { void load().catch(() => undefined); }, 4000);
    return () => { live = false; clearInterval(timer); };
  }, [load]);

  const show = useCallback(async (id: string) => {
    if (open?.id === id) { setOpen(null); return; }
    setError("");
    try {
      setOpen(await intakeApi<Deliverable>(`/api/workspaces/${ws}/deliverables/${id}`));
    } catch (e) {
      setError(reason(e, "That document could not be opened"));
    }
  }, [open?.id, ws]);

  if (loading) return <p className="text-[13.5px] text-ink-dim">Reading…</p>;

  return (
    <div className="space-y-5">
      {error && (
        <p role="alert" className="border border-line bg-surface p-4 text-[13.5px] text-red-800 print:hidden">
          {error}
        </p>
      )}

      {rows.length === 0 ? (
        <div className="border border-dashed border-line p-6 print:hidden">
          <p className="text-[14px] font-medium">No document has been asked for yet.</p>
          <p className="mt-2 max-w-xl text-[13.5px] text-ink-dim">
            Ask the Chief Financial Agent on the Investigation tab — &ldquo;make me a
            one-pager&rdquo; or &ldquo;build a slide deck&rdquo; — and it appears here,
            ready to print. Nothing is produced unless you ask, so an empty list means
            nobody asked rather than that there is nothing to report.
          </p>
        </div>
      ) : (
        <ul className="space-y-2 print:hidden">
          {rows.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                onClick={() => void show(row.id)}
                aria-expanded={open?.id === row.id}
                className={`flex w-full flex-wrap items-center gap-3 border p-4 text-left hover:bg-surface-2 ${
                  open?.id === row.id ? "border-ink bg-surface-2" : "border-line"}`}
              >
                <Pill tone={row.stale ? "amber" : "gray"}>{row.kind_label}</Pill>
                <span className="min-w-0 flex-1">
                  <b className="block text-[14px]">{row.title}</b>
                  {row.requested_by && (
                    <span className="text-[12.5px] text-ink-dim">
                      Asked for: &ldquo;{row.requested_by}&rdquo;
                    </span>
                  )}
                </span>
                <span className="font-accent text-[12px] text-ink-dim">{when(row.created_at)}</span>
                <span className="text-[12.5px] text-ink-dim">
                  {open?.id === row.id ? "Close" : "Open"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && (
        open.kind === "deck"
          ? <Deck data={open.payload} stale={open.stale} />
          : <Snapshot data={open.payload} stale={open.stale} />
      )}
    </div>
  );
}
