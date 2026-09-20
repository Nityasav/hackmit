"use client";

import { useCallback, useEffect, useState } from "react";

import { AnimatedDropdown } from "@/components/ui/animated-dropdown";
import { API_URL, intakeApi, useData } from "@/lib/data";
import { displayLabel } from "@/lib/format";

type Record_ = { role: string; record_key: string; payload: Record<string, unknown>;
  source_id: string; locator: number };
type Register = {
  role: string; label: string; filtered_on: string; available_dates: string[];
  start: string | null; end: string | null; count: number;
  records_without_this_date: number; records: Record_[]; truncated: boolean;
};

const control = "border border-line bg-white px-3 py-2 text-sm disabled:opacity-40";

/**
 * Asking the committed records a question.
 *
 * The books could be uploaded and read line by line, but not interrogated —
 * there was no way to ask which payouts settled on a date, and no way to take
 * a period away as a file.
 *
 * The one thing this screen insists on is saying which date it filtered on.
 * Most roles carry several that mean different things, so "everything in
 * September" is not one question: invoiced, due and paid in September are
 * three different registers, and a total from the wrong one is wrong in a way
 * that looks entirely reasonable. Where no date is clearly primary the API
 * refuses to guess, and the error names the choices rather than picking one.
 */
export function RecordsBrowser() {
  const { ws, bundle } = useData();
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [dates, setDates] = useState<Record<string, { dates: string[]; default: string | null }>>({});
  const [role, setRole] = useState("");
  const [field, setField] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [register, setRegister] = useState<Register | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Only roles that actually hold records: offering an empty one produces a
  // blank register, which reads as "nothing happened" rather than "nothing was
  // uploaded".
  useEffect(() => {
    if (!ws) return;
    let active = true;
    void intakeApi<{ counts: Record<string, number> }>(`/api/workspaces/${ws}/coverage`)
      .then(c => { if (active) setCounts(c.counts || {}); })
      .catch(() => { if (active) setCounts({}); });
    // Which dates each role carries, fetched up front: a role with several
    // refuses to guess, so the choice has to be offerable before the first
    // query rather than discovered from an error.
    void intakeApi<typeof dates>(`/api/workspaces/${ws}/record-dates`)
      .then(d => { if (active) setDates(d || {}); })
      .catch(() => { if (active) setDates({}); });
    return () => { active = false; };
  }, [ws]);

  // Roles that hold records AND carry a date. Vendors, customers and policies
  // are reference data and documents, not transactions: they have no date to
  // filter on, so offering them only produced a 422 once picked.
  const populated = Object.entries(counts)
    .filter(([role, n]) => n > 0 && (dates[role]?.dates.length || 0) > 0)
    .map(([role]) => role);
  const undatable = Object.entries(counts)
    .filter(([role, n]) => n > 0 && !(dates[role]?.dates.length))
    .map(([role]) => role);

  const query = useCallback((withField: string) => {
    const params = new URLSearchParams({ role });
    if (withField) params.set("field", withField);
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    return params.toString();
  }, [role, start, end]);

  async function run(withField = field) {
    if (!role) return;
    setBusy(true); setError(""); setRegister(null);
    try {
      const next = await intakeApi<Register>(`/api/workspaces/${ws}/records?${query(withField)}`);
      setRegister(next);
      setField(next.filtered_on);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The register could not be read.");
    } finally {
      setBusy(false);
    }
  }

  const columns = register?.records.length
    ? Object.keys(register.records[0].payload)
    : [];

  return (
    <section id="source-registers" className="border border-line p-5">
      <h3 className="text-[15px] font-semibold tracking-tight">Find records, and take a period away</h3>
      <p className="my-2 max-w-prose text-[13px] leading-relaxed text-ink-dim">
        Search the committed records by date — every payout settled on a day, every invoice due in a
        month. The register always says which date it filtered on, because invoiced, due and paid are
        different questions and a total from the wrong one looks just as convincing.
      </p>

      <div className="my-3 flex flex-wrap items-end gap-3 text-[13px]">
        <label>Kind of record
          <AnimatedDropdown
            className="ml-2"
            value={role}
            disabled={busy}
            placeholder="Choose…"
            options={populated.map(r => ({ value: r, label: `${displayLabel(r)} (${counts[r]})` }))}
            onChange={value => { setRole(value); setField(""); setRegister(null); setError(""); }}
          />
        </label>
        <label>From<input type="date" className={control + " ml-2"} value={start} disabled={busy}
          onChange={e => setStart(e.target.value)} /></label>
        <label>To<input type="date" className={control + " ml-2"} value={end} disabled={busy}
          onChange={e => setEnd(e.target.value)} /></label>
        {(dates[role]?.dates.length || 0) > 1 && (
          <label>Date to use
            <AnimatedDropdown
              className="ml-2"
              value={field}
              disabled={busy}
              placeholder="Choose…"
              options={dates[role].dates.map(d => ({ value: d, label: displayLabel(d) }))}
              onChange={value => { setField(value); setError(""); }}
            />
          </label>
        )}
        <button className={control} disabled={busy || !role} onClick={() => void run()}>
          {busy ? "Reading…" : "Find records"}
        </button>
        {register && register.count > 0 && (
          <a className={control} href={`${API_URL}/api/workspaces/${ws}/records.csv?${query(field)}`}>
            Download spreadsheet ({register.count})
          </a>
        )}
      </div>

      {error && <p role="alert" className="border border-red-300 bg-red-50 p-3 text-[13px] text-red-800">{error}</p>}

      {register && (
        <>
          <p className="text-[13px]">
            <b>{register.count}</b> {register.label.toLowerCase()} · filtered on{" "}
            <b>{displayLabel(register.filtered_on)}</b>
            {register.start || register.end
              ? ` · ${register.start || "the earliest record"} to ${register.end || "the latest record"}`
              : " · every date"}
          </p>
          {register.records_without_this_date > 0 && (
            <p className="mt-1 text-[12.5px] text-amber-800">
              {register.records_without_this_date} record(s) of this kind carry no{" "}
              {displayLabel(register.filtered_on).toLowerCase()} and are not counted here. That is a
              gap in the records, not an absence of transactions.
            </p>
          )}
          {register.truncated && (
            <p className="mt-1 text-[12.5px] text-amber-800">
              Showing the first {register.records.length}. The spreadsheet carries all {register.count}.
            </p>
          )}

          {register.count === 0 ? (
            <p className="mt-3 border border-line p-4 text-[13px]">
              No {register.label.toLowerCase()} fall in that range. An empty register is not a clean
              result — it means nothing was supplied that matches.
            </p>
          ) : (
            <div className="mt-3 max-h-[420px] overflow-auto border border-line">
              <table className="w-full border-collapse text-[12.5px]">
                <thead className="sticky top-0 bg-surface-2">
                  <tr>
                    <th className="border-b border-line p-2 text-left font-semibold">Source</th>
                    {columns.map(c => (
                      <th key={c} className="border-b border-line p-2 text-left font-semibold">
                        {displayLabel(c)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {register.records.map(r => (
                    <tr key={`${r.source_id}-${r.locator}-${r.record_key}`}>
                      <td className="border-b border-line p-2 font-mono text-[11.5px] text-ink-dim">
                        line {r.locator}
                      </td>
                      {columns.map(c => (
                        <td key={c} className="border-b border-line p-2">
                          {r.payload[c] === null || r.payload[c] === undefined ? "" : String(r.payload[c])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {undatable.length > 0 && (
        <p className="mb-2 text-[12.5px] text-ink-dim">
          {undatable.map(displayLabel).join(", ")} are not listed: they are reference data and
          documents rather than transactions, so they carry no date to search by.
        </p>
      )}

      {!register && !error && (
        <p className="text-[13px] text-ink-dim">
          {populated.length
            ? "Choose a kind of record and a range."
            : bundle.workspace.snapshot_id
              ? "No records are committed yet. Add them above, then commit."
              : "Commit an import first — a register reads committed records, not staged ones."}
        </p>
      )}
    </section>
  );
}
