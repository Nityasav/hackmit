"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, intakeApi } from "@/lib/api";
import { Pill } from "@/components/ui";
import type { EventDetail, TimelineEvent } from "@/lib/types";

/**
 * Every transaction in the period, one row each.
 *
 * One row per *economic event*, not per document. The invoice, the order, the receipt,
 * the payment, the bank line and the journal entries are six views of one thing that
 * happened, and a list that showed each separately would report one purchase six times.
 * Opening a row shows exactly what carries that identity — which is the question the
 * whole event model exists to answer.
 */

function reason(error: unknown, fallback: string) {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : fallback;
}

const KIND_TONE: Record<string, "green" | "amber" | "gray"> = {
  sale: "green",
  purchase: "amber",
};

export function Timeline({ ws }: { ws: string }) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [open, setOpen] = useState("");
  const [detail, setDetail] = useState<EventDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const body = await intakeApi<{ events: TimelineEvent[] }>(
          `/api/workspaces/${ws}/agents/timeline`,
        );
        setEvents(body.events);
        setError("");
      } catch (e) {
        setError(reason(e, "The timeline could not be read"));
      }
    })();
  }, [ws]);

  const show = useCallback(
    async (id: string) => {
      if (open === id) {
        setOpen("");
        setDetail(null);
        return;
      }
      setOpen(id);
      setDetail(null);
      try {
        setDetail(await intakeApi<EventDetail>(`/api/workspaces/${ws}/agents/timeline/${encodeURIComponent(id)}`));
      } catch (e) {
        setError(reason(e, "That event could not be read"));
      }
    },
    [open, ws],
  );

  if (error) {
    return (
      <p role="alert" className="border border-line bg-surface p-4 text-[13.5px] text-red-800">
        {error}
      </p>
    );
  }

  if (!events.length) {
    return (
      <p className="text-[13.5px] text-ink-dim">
        No transactions yet. Events are created when records are committed, from the
        references the records themselves carry.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {events.map((event) => (
        <div key={event.id} className="border border-line">
          <button
            type="button"
            onClick={() => void show(event.id)}
            aria-expanded={open === event.id}
            className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left hover:bg-surface-2"
          >
            <span className="font-accent text-[13px] text-ink-dim">{event.occurred_on}</span>
            <Pill tone={KIND_TONE[event.kind] ?? "gray"}>{event.kind.replace(/_/g, " ")}</Pill>
            <span className="min-w-0 flex-1 truncate text-[14px]">{event.title}</span>
            <span className="text-[12.5px] text-ink-dim">
              {event.record_count} record{event.record_count === 1 ? "" : "s"}
            </span>
          </button>

          {open === event.id && (
            <div className="border-t border-line bg-surface-2 px-4 py-4">
              {!detail ? (
                <p className="text-[13.5px] text-ink-dim">Reading…</p>
              ) : (
                <>
                  <p className="text-[13px] text-ink-dim">
                    {detail.roles.length} kind{detail.roles.length === 1 ? "" : "s"} of record carry this
                    identity: {detail.roles.map((role) => role.replace(/_/g, " ")).join(", ")}.
                  </p>
                  <ul className="mt-3 space-y-1">
                    {detail.records.map((record) => (
                      <li key={`${record.role}-${record.record_key}`} className="font-accent text-[13px]">
                        <span className="text-ink-dim">{record.role.replace(/_/g, " ")}</span>{" "}
                        {record.record_key.split("\u001f").join(" · ")}
                      </li>
                    ))}
                  </ul>

                  {detail.links.length > 0 && (
                    <>
                      <h4 className="mt-4 text-[13px] font-semibold">How these were connected</h4>
                      <ul className="mt-1 space-y-1 text-[13px]">
                        {detail.links.map((link, i) => (
                          <li key={`${link.from_id}-${link.to_id}-${i}`}>
                            {link.from_id} → {link.to_id} · {link.kind.replace(/_/g, " ")} ·{" "}
                            {/* An exact reference match and a fuzzy one are both links, and a
                                reader has to be able to tell them apart. */}
                            <span className="text-ink-dim">
                              {link.method} match, confidence {link.confidence} of 100
                            </span>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}

                  <h4 className="mt-4 text-[13px] font-semibold">
                    What the agents decided about it ({detail.decisions.length})
                  </h4>
                  {detail.decisions.length === 0 ? (
                    <p className="mt-1 text-[13px] text-ink-dim">
                      Nothing has been decided about this transaction. That is not a
                      statement that it is fine.
                    </p>
                  ) : (
                    <ul className="mt-1 space-y-1 text-[13px]">
                      {detail.decisions.map((decision) => (
                        <li key={decision.id}>
                          <b>{decision.agent}</b> · {decision.summary}
                          {decision.escalated ? " · waiting on a person" : ""}
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
