"use client";

import { useState } from "react";

import { AnimatedDisclosure } from "@/components/ui/animated-disclosure";
import { intakeApi } from "@/lib/api";
import type { Coverage, DataRequirement } from "@/lib/types";

/**
 * What the agents still need, asked for here.
 *
 * Nothing on this screen is authored. The list is `api/app/requirements.py`, which is
 * the one place that decides what any agent depends on — so Books cannot ask for a file
 * nobody reads, and an agent cannot quietly depend on data nobody was asked to supply.
 * Adding an agent that needs sales-tax registrations adds a box here, with no edit to
 * this component.
 *
 * Two kinds of ask. Most are files, and their answer is an upload through the normal
 * import flow. A few are a single value — a materiality threshold, a home jurisdiction —
 * where a one-row CSV would be worse than a question, so they are answered inline.
 */
export function DataRequirements({
  ws, coverage, onSaved,
}: {
  ws: string;
  coverage: Coverage;
  onSaved: () => void;
}) {

  // A running API can predate a frontend update. Missing requirements are not
  // an empty checklist: do not crash or falsely claim everything is supplied.
  if (!Array.isArray(coverage.requirements)) {
    return <section className="mt-4 border border-line p-3" aria-label="What the agents need">
      <p role="alert" className="text-sm">Requirements are unavailable. The records service needs to be updated or restarted to match this app.</p>
      <button type="button" onClick={onSaved} className="mt-2 border border-line px-3 py-2 text-xs">Retry requirements</button>
    </section>;
  }

  const outstanding = coverage.requirements.filter((r) => !r.satisfied);
  const missingRequired = outstanding.filter((r) => !r.optional);
  const groups = [
    { label: "Required records and settings", items: missingRequired },
    { label: "Optional records and settings", items: outstanding.filter(r => r.optional) },
    { label: "Already supplied", items: coverage.requirements.filter(r => r.satisfied) },
  ];

  return (
    <section className="mt-4" aria-label="What the agents need">
      <AnimatedDisclosure
        className="border border-line p-3"
        summaryClassName="text-sm font-semibold"
        summary={<>What the agents need
          <span className="ml-3 text-xs font-normal text-ink-dim">{coverage.satisfied_count}/{coverage.required_count} required items supplied · {missingRequired.length} remaining</span>
        </>}
      >

      {missingRequired.length === 0 && (
        <p className="mt-2 max-w-prose text-xs text-ink-dim">
          Everything required has been supplied. That means the agents can read these records —
          not that the books are complete.
        </p>
      )}

      {groups.map(group => <AnimatedDisclosure
        key={group.label}
        className="mt-3 border-t border-line pt-3"
        summaryClassName="text-xs font-semibold"
        summary={<>{group.label} ({group.items.length})</>}
      >
        <div className="mt-3 grid items-start gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {group.items.map((requirement) =>
          requirement.kind === "setting" ? (
            <SettingAsk key={requirement.id} ws={ws} requirement={requirement} onSaved={onSaved} />
          ) : (
            <FileAsk key={requirement.id} requirement={requirement} />
          ),
        )}
        </div>
      </AnimatedDisclosure>)}
      </AnimatedDisclosure>
    </section>
  );
}

/** Who is waiting on this, in the words the registry uses. */
function WaitingOn({ requirement }: { requirement: DataRequirement }) {
  if (requirement.satisfied || requirement.needed_by.length === 0) return null;
  return (
    <p className="mt-1 font-num text-[11px] text-ink-faint">
      Waiting: {requirement.needed_by.join(", ")}
    </p>
  );
}

function Status({ requirement }: { requirement: DataRequirement }) {
  const tone = requirement.satisfied
    ? "bg-surface-2 text-ink"
    : requirement.optional
      ? "bg-surface-2 text-ink-dim"
      : "bg-amber-50 text-amber-800";
  const label = requirement.satisfied ? "Supplied" : requirement.optional ? "Optional" : "Needed";
  return <span className={`mt-1 inline-block px-1.5 py-0.5 text-[10px] ${tone}`}>{label}</span>;
}

function FileAsk({ requirement }: { requirement: DataRequirement }) {
  return (
    <div className="border border-line p-3">
      <div className="font-semibold">{requirement.label}</div>
      <Status requirement={requirement} />
      <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">{requirement.unlocks}</p>
      {!requirement.satisfied && requirement.after.length > 0 && (
        <p className="mt-1 text-[11px] text-ink-faint">Supply after: {requirement.after.join(", ")}</p>
      )}
      <WaitingOn requirement={requirement} />
    </div>
  );
}

/**
 * A single value, answered here.
 *
 * Money is stored in integer cents like every other amount in the system, so the input
 * takes major units and converts exactly — parsing to cents rather than multiplying a
 * float, because 0.1 + 0.2 has no place anywhere near a ledger.
 */
function SettingAsk({
  ws, requirement, onSaved,
}: {
  ws: string;
  requirement: DataRequirement;
  onSaved: () => void;
}) {
  const isMoney = requirement.control === "money";
  // The saved answer is the source of truth; `draft` exists only while someone is
  // typing over it. Deriving the displayed value rather than mirroring the prop into
  // state means a save elsewhere shows up here without an effect to keep them in step.
  const [draft, setDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const saved = requirement.value;
  const value = draft ?? (saved === null ? "" : isMoney ? majorUnits(Number(saved)) : String(saved));

  async function save() {
    setBusy(true);
    setError("");
    try {
      const parsed = isMoney || requirement.control === "integer" ? toWhole(value, isMoney) : value.trim();
      if (parsed === null) throw new Error("Enter a number, without a currency symbol.");
      await intakeApi(`/api/workspaces/${encodeURIComponent(ws)}/settings`, {
        method: "PATCH",
        body: { settings: { [requirement.setting as string]: parsed } },
      });
      setDraft(null);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border border-line p-3">
      <div className="font-semibold">{requirement.label}</div>
      <Status requirement={requirement} />
      <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">{requirement.unlocks}</p>
      <div className="mt-2 flex gap-1.5">
        <input
          aria-label={requirement.label}
          className="min-w-0 flex-1 border border-line px-2 py-1 text-xs"
          placeholder={placeholderFor(requirement)}
          value={value}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void save();
          }}
        />
        <button type="button" disabled={busy} className="border border-line px-2 py-1 text-xs" onClick={() => void save()}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
      {error && <p role="alert" className="mt-1 text-[11px] text-red-800">{error}</p>}
      <WaitingOn requirement={requirement} />
    </div>
  );
}

function placeholderFor(requirement: DataRequirement): string {
  if (requirement.control === "money") return "e.g. 2500.00";
  if (requirement.control === "integer") return "e.g. 5";
  if (requirement.control === "month_day") return "e.g. 12-31";
  return "";
}

function majorUnits(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const value = Math.abs(cents);
  return `${sign}${Math.trunc(value / 100)}.${String(value % 100).padStart(2, "0")}`;
}

/** Exact major-to-minor conversion. Returns null when the text is not a plain number. */
function toWhole(raw: string, money: boolean): number | null {
  const text = raw.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
  if (!money) return text.includes(".") ? null : Number(text);
  const [whole, fraction = ""] = text.split(".");
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
}
