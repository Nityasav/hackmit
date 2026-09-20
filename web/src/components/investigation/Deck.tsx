"use client";

import { Button } from "@/components/ui";
import type { PeriodSnapshot } from "@/lib/types";

/**
 * The same period as slides, one per printed page.
 *
 * Built from the identical frozen payload the one-pager uses, which is the point: a deck
 * and a document of the same period that disagree are two accounts of one month, and the
 * reader has no way to tell which is the real one. Neither file computes anything.
 *
 * A slide carries one idea and the figures for it. Where the one-pager packs the period
 * densely because a reader has it in their hands, a slide is read from across a room in
 * ten seconds, so the type is larger and there is less of it.
 */

const money = (cents: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })
    .format(cents / 100);

const exact = (cents: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);

const signed = (cents: number) => (cents < 0 ? "−" : "") + money(Math.abs(cents));

export function Deck({ data, stale }: { data: PeriodSnapshot; stale?: boolean }) {
  const { workspace: w, result, checks, close, controls, variance } = data;
  const tied = checks.trial_balance_balances && checks.balance_sheet_balances && checks.cash_flow_ties;
  const categories = Object.entries(result.expense_by_category_cents).sort((a, b) => b[1] - a[1]);
  const biggest = categories[0]?.[1] ?? 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 print:hidden">
        <Button primary onClick={() => window.print()}>Save as PDF</Button>
        <p className="text-[13px] text-ink-dim">
          Prints one slide per page. In the dialog choose <b>Save as PDF</b>, set layout
          to <b>Landscape</b>, and leave headers and footers off.
        </p>
      </div>

      {stale && (
        <p role="status" className="border-l-4 border-amber-500 bg-amber-50 p-4 text-[13.5px] print:hidden">
          Records have been committed since this deck was prepared. It is historical
          rather than wrong.
        </p>
      )}

      <div className="deck space-y-5">
        <Slide>
          <p className="font-accent text-[13px] uppercase tracking-[0.3em] text-ink-dim">
            {w.start} to {w.end}
          </p>
          <h1 className="mt-4 text-[44px] font-semibold leading-none tracking-tight">{w.name}</h1>
          <p className="mt-4 text-[18px] text-ink-dim">Period review</p>
          <p className="mt-auto font-accent text-[12px] text-ink-dim">
            Every figure computed from {data.records.toLocaleString()} committed records,
            in exact cents. None of them was written by a language model.
          </p>
        </Slide>

        <Slide>
          <SlideTitle>The result</SlideTitle>
          <div className="mt-8 grid grid-cols-3 gap-8">
            <Big label="Revenue" value={money(result.revenue_cents)} />
            <Big label="Expenses" value={money(result.expense_cents)} />
            <Big label="Result" value={signed(result.net_cents)} lead />
          </div>
          <p className="mt-auto text-[14px] text-ink-dim">
            {result.net_cents < 0 ? "The period spent more than it earned." : "The period earned more than it spent."}
            {" "}Exact: {exact(result.net_cents)}.
          </p>
        </Slide>

        <Slide>
          <SlideTitle>Does it tie?</SlideTitle>
          <div className="mt-8 space-y-5">
            <Line ok={checks.balance_sheet_balances}
                  label="Assets equal liabilities plus equity"
                  detail={checks.balance_sheet_balances
                    ? "Exact to the cent, with the period result shown separately so the balance is a check rather than an assumption"
                    : `Out by ${exact(Math.abs(checks.balance_sheet_difference_cents))}`} />
            <Line ok={checks.cash_flow_ties}
                  label="Cash walked from the entries lands on the balance sheet"
                  detail={checks.cash_flow_ties
                    ? "No movement was dropped on the way into an activity"
                    : "An entry was missed"} />
            <Line ok={close.ready}
                  label="The period is ready to close"
                  detail={close.ready
                    ? "Nothing supplied contradicts it"
                    : `Blocked by ${close.blocked_by.join(", ")}`} />
          </div>
          {!tied && (
            <p className="mt-auto text-[14px] font-medium text-red-800">
              Until these hold, the figures in this deck should not be presented.
            </p>
          )}
        </Slide>

        <Slide>
          <SlideTitle>Where the money went</SlideTitle>
          <div className="mt-8 space-y-4">
            {categories.slice(0, 5).map(([category, cents]) => (
              <div key={category}>
                <div className="flex items-baseline justify-between text-[16px]">
                  <span className="capitalize">{category.replace(/_/g, " ")}</span>
                  <span className="font-num tabular-nums">{money(cents)}</span>
                </div>
                {/* Proportional to the largest category, so the bars compare with each
                    other and not with a total nobody is looking at. */}
                <div className="mt-1 h-2 w-full bg-surface-2">
                  <div className="h-2 bg-ink" style={{ width: `${Math.max(2, (cents * 100) / biggest)}%` }} />
                </div>
              </div>
            ))}
          </div>
          <p className="mt-auto font-accent text-[12px] text-ink-dim">
            Categories come from the chart of accounts, so this and the statements group
            the same accounts the same way.
          </p>
        </Slide>

        <Slide>
          <SlideTitle>
            {controls.exception_count === 0
              ? "Every control test passed"
              : `${controls.exception_count} exception${controls.exception_count === 1 ? "" : "s"}`}
          </SlideTitle>
          {controls.exception_count === 0 ? (
            <div className="mt-8">
              <p className="text-[18px]">
                {controls.pass_count} tests ran against these books and each found nothing.
              </p>
              {/* Named, because "no exceptions" and "we did not look" read identically
                  and only one of them is a finding. */}
              <ul className="mt-5 space-y-2 text-[15px] text-ink-dim">
                {controls.passed.map((title) => <li key={title}>· {title}</li>)}
              </ul>
            </div>
          ) : (
            <table className="mt-7 w-full border-collapse text-[15px]">
              <tbody>
                {controls.exceptions.map((item) => (
                  <tr key={item.id} className="border-b border-line align-top">
                    <td className="py-2.5 pr-6">
                      {item.title}
                      <div className="font-num text-[12px] text-ink-dim">{item.records.join(" · ")}</div>
                    </td>
                    <td className="w-36 py-2.5 text-right font-num tabular-nums">
                      {item.amount_cents === null ? "—" : exact(item.amount_cents)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-auto font-accent text-[12px] text-ink-dim">
            A duplicate candidate is not a duplicate payment. Amounts from different tests
            may overlap and are not added together.
          </p>
        </Slide>

        {variance.lines.length > 0 && (
          <Slide>
            <SlideTitle>Against the approved budget</SlideTitle>
            <table className="mt-7 w-full border-collapse text-[15px]">
              <thead>
                <tr className="border-b border-ink text-[12px] uppercase tracking-wider text-ink-dim">
                  <th className="pb-2 text-left font-normal">Account</th>
                  <th className="pb-2 text-right font-normal">Budget</th>
                  <th className="pb-2 text-right font-normal">Actual</th>
                  <th className="pb-2 text-right font-normal">Variance</th>
                </tr>
              </thead>
              <tbody>
                {variance.lines.slice(0, 5).map((line) => (
                  <tr key={line.account} className="border-b border-line">
                    <td className="py-2.5">{line.name}</td>
                    <td className="py-2.5 text-right font-num tabular-nums text-ink-dim">{money(line.planned_cents)}</td>
                    <td className="py-2.5 text-right font-num tabular-nums">{money(line.actual_cents)}</td>
                    <td className="py-2.5 text-right font-num tabular-nums">
                      {signed(line.variance_cents)}
                      <span className="ml-2 text-[12px] text-ink-dim">{line.favourable ? "fav" : "adv"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-auto font-accent text-[12px] text-ink-dim">
              Over-spending is adverse; over-earning is not. Expense and revenue variances
              are never added together.
            </p>
          </Slide>
        )}

        <Slide>
          <SlideTitle>What this does not establish</SlideTitle>
          <ul className="mt-8 space-y-4 text-[15px] leading-relaxed">
            {data.limitations.map((line) => <li key={line}>{line}</li>)}
          </ul>
          {data.snapshot_id && (
            <p className="mt-auto font-num text-[11px] text-ink-dim">Snapshot {data.snapshot_id}</p>
          )}
        </Slide>
      </div>
    </div>
  );
}

function Slide({ children }: { children: React.ReactNode }) {
  return (
    <section className="deck-slide mx-auto flex aspect-[16/9] w-full max-w-[1000px] flex-col border border-line bg-white p-12 text-ink">
      {children}
    </section>
  );
}

function SlideTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-[30px] font-semibold leading-tight tracking-tight">{children}</h2>;
}

function Big({ label, value, lead }: { label: string; value: string; lead?: boolean }) {
  return (
    <div>
      <p className="font-accent text-[12px] uppercase tracking-[0.2em] text-ink-dim">{label}</p>
      <p className={`mt-2 font-num tabular-nums ${lead ? "text-[46px] font-semibold" : "text-[34px]"}`}>
        {value}
      </p>
    </div>
  );
}

function Line({ ok, label, detail }: { ok: boolean; label: string; detail: string }) {
  return (
    <div className="flex gap-4">
      <span aria-hidden className={`text-[24px] leading-none ${ok ? "text-green-700" : "text-red-700"}`}>
        {ok ? "✓" : "✗"}
      </span>
      <div>
        <p className="text-[18px]">{label}</p>
        <p className="mt-0.5 text-[14px] text-ink-dim">{detail}</p>
        <span className="sr-only">{ok ? "holds" : "does not hold"}</span>
      </div>
    </div>
  );
}
