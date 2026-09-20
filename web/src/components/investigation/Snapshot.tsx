"use client";

import { useEffect, useState } from "react";

import { ApiError, intakeApi } from "@/lib/api";
import { Button } from "@/components/ui";
import type { PeriodSnapshot } from "@/lib/types";

/**
 * The period on one page, for someone who was not in the room.
 *
 * Every figure comes from `/deliverables/snapshot`, computed in integer cents by the
 * accounting modules. This file formats them and writes nothing — which is what makes
 * printing it to PDF and handing it to a board a defensible thing to do.
 *
 * ## It is one read, deliberately
 *
 * Four fetches would assemble a document out of four moments, and a commit landing
 * between the first and the last gives you a page where every figure is true and the
 * page as a whole is of no particular period. One read, one snapshot id, one timestamp.
 *
 * ## What it refuses to do
 *
 * It will not present figures that do not tie. If the trial balance is out or the cash
 * flow does not reconcile, the page says so where the numbers would have been and stays
 * unprintable — a board pack that looks finished and is not is worse than no board pack.
 */

const money = (cents: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);

// Figures use a minus sign rather than a hyphen and are never coloured red on their own:
// a loss is a fact, not an alarm, and the reader decides what it means.
const signed = (cents: number) => (cents < 0 ? "−" : "") + money(Math.abs(cents));

const day = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { day: "numeric", month: "long", year: "numeric" });

function reason(error: unknown, fallback: string) {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : fallback;
}

export function Snapshot({ ws }: { ws: string }) {
  const [data, setData] = useState<PeriodSnapshot | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    void (async () => {
      setLoading(true);
      try {
        const body = await intakeApi<PeriodSnapshot>(`/api/workspaces/${ws}/deliverables/snapshot`);
        if (live) { setData(body); setError(""); }
      } catch (e) {
        if (live) setError(reason(e, "The snapshot could not be prepared"));
      } finally {
        if (live) setLoading(false);
      }
    })();
    return () => { live = false; };
  }, [ws]);

  if (loading && !data) return <p className="text-[13.5px] text-ink-dim">Preparing the snapshot…</p>;
  if (error) return <p role="alert" className="border border-line bg-surface p-4 text-[13.5px] text-red-800">{error}</p>;
  if (!data) return null;

  const { workspace: w, result, position, checks, close, controls, variance } = data;
  const tied = checks.trial_balance_balances && checks.balance_sheet_balances && checks.cash_flow_ties;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 print:hidden">
        <Button primary onClick={() => window.print()}>Save as PDF</Button>
        <p className="text-[13px] text-ink-dim">
          Prints as one page. In the dialog choose <b>Save as PDF</b>, and leave headers
          and footers off.
        </p>
      </div>

      {!tied && (
        <p role="alert" className="border-l-4 border-red-700 bg-red-50 p-4 text-[13.5px] text-red-900 print:hidden">
          These books do not tie, so this page is not a document to hand anyone. Fix what
          is listed on it first.
        </p>
      )}

      {/* The page itself. A4-ish at 96dpi, so what is on screen is what prints. */}
      <article className="snapshot-page mx-auto w-full max-w-[820px] border border-line bg-white p-10 text-ink">
        <header className="flex items-baseline justify-between border-b-2 border-ink pb-4">
          <div>
            <h1 className="text-[26px] font-semibold leading-tight tracking-tight">{w.name}</h1>
            <p className="mt-1 font-accent text-[13px] text-ink-dim">
              Period snapshot · {w.start} to {w.end}
              {w.jurisdiction ? ` · ${w.jurisdiction}` : ""}
            </p>
          </div>
          <div className="text-right">
            <p className="font-num text-[13px]">{day(data.prepared_at)}</p>
            <p className="font-accent text-[11.5px] text-ink-dim">{data.records.toLocaleString()} records</p>
          </div>
        </header>

        {/* The result. The one figure a reader looks for first, given the room to be it. */}
        <section className="mt-7 grid grid-cols-3 gap-6">
          <Figure label="Revenue" value={money(result.revenue_cents)} />
          <Figure label="Expenses" value={money(result.expense_cents)} />
          <Figure label="Result for the period" value={signed(result.net_cents)} emphasis />
        </section>

        {/* The identities. These decide whether anything above may be shown at all, so
            they sit directly beneath it rather than in a footnote. */}
        <section className="mt-7 border-y border-line py-4">
          <h2 className="font-accent text-[11px] uppercase tracking-[0.2em] text-ink-dim">Does it tie?</h2>
          <div className="mt-3 grid grid-cols-3 gap-6 text-[13.5px]">
            <Check
              ok={checks.balance_sheet_balances}
              label="Assets = liabilities + equity"
              detail={checks.balance_sheet_balances
                ? "Exact to the cent"
                : `Out by ${money(Math.abs(checks.balance_sheet_difference_cents))}`}
            />
            <Check ok={checks.cash_flow_ties} label="Cash agrees with the balance sheet"
                   detail={checks.cash_flow_ties ? "Every entry accounted for" : "An entry was missed"} />
            <Check ok={close.ready} label="Ready to close"
                   detail={close.ready ? "Nothing supplied contradicts it"
                                       : `${close.blocked_by.length} blocking item`} />
          </div>
        </section>

        <section className="mt-7 grid grid-cols-2 gap-10">
          <div>
            <h2 className="font-accent text-[11px] uppercase tracking-[0.2em] text-ink-dim">Position</h2>
            <dl className="mt-3 space-y-1.5 text-[13.5px]">
              <Row label="Assets" value={money(position.assets_cents)} />
              <Row label="Liabilities" value={money(position.liabilities_cents)} />
              <Row label="Equity" value={money(position.equity_cents)} />
              <Row label="Cash at start" value={money(position.opening_cash_cents)} muted />
              <Row label="Cash at end" value={money(position.closing_cash_cents)} />
            </dl>
          </div>
          <div>
            <h2 className="font-accent text-[11px] uppercase tracking-[0.2em] text-ink-dim">Where it went</h2>
            <dl className="mt-3 space-y-1.5 text-[13.5px]">
              {Object.entries(result.expense_by_category_cents)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 5)
                .map(([category, cents]) => (
                  <Row key={category} label={category.replace(/_/g, " ")} value={money(cents)} />
                ))}
            </dl>
          </div>
        </section>

        <section className="mt-7">
          <div className="flex items-baseline justify-between">
            <h2 className="font-accent text-[11px] uppercase tracking-[0.2em] text-ink-dim">
              Exceptions raised
            </h2>
            <p className="font-num text-[13px]">
              {controls.exception_count} of {controls.exception_count + controls.pass_count} tests
            </p>
          </div>

          {controls.exceptions.length === 0 ? (
            /* A pass is a finding. Naming the tests is the difference between "we looked
               and found nothing" and silence, which read identically otherwise. */
            <div className="mt-3 border-l-2 border-green-700 bg-green-50/60 p-3 text-[13.5px]">
              <p><b>No exception was raised.</b> {controls.pass_count} tests ran and each found nothing:</p>
              <p className="mt-1 text-ink-dim">{controls.passed.join(" · ")}</p>
            </div>
          ) : (
            <table className="mt-3 w-full border-collapse text-[13px]">
              <tbody>
                {controls.exceptions.map((item) => (
                  <tr key={item.id} className="border-b border-line align-top">
                    <td className="py-2 pr-4">
                      <b className="font-medium">{item.title}</b>
                      <div className="font-num text-[11.5px] text-ink-dim">{item.records.join(" · ")}</div>
                    </td>
                    <td className="w-28 py-2 text-right font-num">
                      {item.amount_cents === null ? "—" : money(item.amount_cents)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {controls.omitted > 0 && (
            <p className="mt-2 text-[12px] text-ink-dim">
              {controls.omitted} further exception{controls.omitted === 1 ? "" : "s"} not shown here.
            </p>
          )}
        </section>

        {variance.lines.length > 0 && (
          <section className="mt-7">
            <div className="flex items-baseline justify-between">
              <h2 className="font-accent text-[11px] uppercase tracking-[0.2em] text-ink-dim">
                Against the approved budget
              </h2>
              <p className="font-num text-[13px]">
                {money(variance.expense_actual_cents)} of {money(variance.expense_planned_cents)}
              </p>
            </div>
            <table className="mt-3 w-full border-collapse text-[13px]">
              <tbody>
                {variance.lines.map((line) => (
                  <tr key={line.account} className="border-b border-line">
                    <td className="py-1.5 pr-4">{line.name}</td>
                    <td className="w-28 py-1.5 text-right font-num text-ink-dim">{money(line.planned_cents)}</td>
                    <td className="w-28 py-1.5 text-right font-num">{money(line.actual_cents)}</td>
                    <td className="w-28 py-1.5 text-right font-num">
                      {signed(line.variance_cents)}
                      {/* Over-spending is adverse; over-earning is not. The sign alone
                          does not say, so the word does. */}
                      <span className="ml-1 text-[11px] text-ink-dim">
                        {line.favourable ? "fav" : "adv"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {variance.omitted > 0 && (
              <p className="mt-2 text-[12px] text-ink-dim">
                {variance.omitted} smaller variance{variance.omitted === 1 ? "" : "s"} not shown.
              </p>
            )}
          </section>
        )}

        <footer className="mt-8 border-t border-line pt-3">
          <ul className="space-y-1 text-[10.5px] leading-snug text-ink-dim">
            {data.limitations.map((line) => <li key={line}>{line}</li>)}
          </ul>
          {data.snapshot_id && (
            <p className="mt-2 font-num text-[10px] text-ink-dim">Snapshot {data.snapshot_id}</p>
          )}
        </footer>
      </article>
    </div>
  );
}

function Figure({ label, value, emphasis }: { label: string; value: string; emphasis?: boolean }) {
  return (
    <div>
      <p className="font-accent text-[11px] uppercase tracking-[0.18em] text-ink-dim">{label}</p>
      <p className={`mt-1 font-num tabular-nums ${emphasis ? "text-[30px] font-semibold" : "text-[22px]"}`}>
        {value}
      </p>
    </div>
  );
}

function Check({ ok, label, detail }: { ok: boolean; label: string; detail: string }) {
  return (
    <div className="flex gap-2">
      <span aria-hidden className={`mt-0.5 text-[15px] leading-none ${ok ? "text-green-700" : "text-red-700"}`}>
        {ok ? "✓" : "✗"}
      </span>
      <div>
        <p className="font-medium">{label}</p>
        <p className="text-[12px] text-ink-dim">{detail}</p>
        <span className="sr-only">{ok ? "holds" : "does not hold"}</span>
      </div>
    </div>
  );
}

function Row({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className={muted ? "text-ink-dim" : ""}>{label}</dt>
      <dd className="font-num tabular-nums">{value}</dd>
    </div>
  );
}
