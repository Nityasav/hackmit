"use client";

import { useEffect, useState } from "react";

import { intakeApi, useData } from "@/lib/data";
import { Button } from "@/components/ui";

interface ReviewView {
  snapshot_id: string | null;
  scan: { id: string; record_count: number } | null;
  findings: { status: string; stale?: boolean }[];
}

/**
 * The rules-based pass over committed records.
 *
 * It runs locally with no model and no cost, and it is what turns a committed
 * snapshot into findings. Its button used to live only on the briefing screen,
 * which meant the step between committing records and having anything to read
 * had no control anywhere the work actually happens.
 */
export function RecordChecks({ ws }: { ws: string }) {
  const { refreshBundle } = useData();
  const [view, setView] = useState<ReviewView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // The fetch lives inside the effect so a state update cannot be traced back
  // into the effect body; `reload` is how the scan asks for a fresh read.
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!ws) return;
    let mounted = true;
    intakeApi<ReviewView>(`/api/workspaces/${encodeURIComponent(ws)}/review`)
      .then((next) => { if (mounted) setView(next); })
      .catch(() => { /* The shared API status line reports outages; keep the last view. */ });
    return () => { mounted = false; };
  }, [ws, reload]);

  async function scan() {
    setBusy(true);
    setError("");
    try {
      await intakeApi(`/api/workspaces/${encodeURIComponent(ws)}/review/scans`, { method: "POST" });
      setReload((n) => n + 1);
      await refreshBundle();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The checks could not run.");
    } finally {
      setBusy(false);
    }
  }

  const live = view?.findings.filter((f) => !f.stale) ?? [];
  const attention = live.filter((f) => f.status === "attention").length;
  const gaps = live.filter((f) => f.status === "gap").length;

  return (
    <div className="border border-line bg-surface-2 p-5">
      <p className="max-w-[68ch] text-[14px] leading-relaxed">
        These run on this machine with no model and no cost. They read the committed records and
        raise what does not add up, before any agent is asked anything.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button primary disabled={busy || !view?.snapshot_id} onClick={() => void scan()}>
          {busy ? "Running checks…" : view?.scan ? "Run the checks again" : "Check the committed records"}
        </Button>
        {!view?.snapshot_id && (
          <span className="text-[13px] text-ink-dim">
            Commit this school&rsquo;s records on Books first.
          </span>
        )}
        {view?.scan && (
          <span className="font-accent text-[13px] text-ink-dim">
            {view.scan.record_count} records checked · {attention} need attention · {gaps} evidence gaps
          </span>
        )}
      </div>

      {error && <p role="alert" className="mt-3 text-[13px] text-accent-bad">{error}</p>}
    </div>
  );
}
