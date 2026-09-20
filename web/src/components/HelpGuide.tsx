"use client";

import { useEffect, useRef, useState } from "react";
import { HelpCircle, X } from "lucide-react";
import { useData } from "@/lib/data";
import { NAV } from "@/lib/tabs";

const SEEN_KEY = "sherlock.help.seen.v1";

/** What each of the three screens is for, in the order the work happens. */
const SCREENS: Record<string, string> = {
  books: "Everything starts here. Add this school's files, see how each column was read, and commit one fixed set of records. Nothing is saved until you have looked at it.",
  investigation: "Ask the agents a question in your own words. Five of them read the committed records, each quotes the line behind every claim, and the Internal Auditor re-checks the others before anything reaches you.",
  briefing: "The write-up you hand over. It is built from the records committed here and the follow-up recorded against them, and it says plainly what the review does not establish.",
};

const HOW = [
  "Add a school and the period its records cover.",
  "Add CSV, text or Markdown files — or stage the fictional sample pack.",
  "Check how each file was read, and fix anything flagged.",
  "Commit the records, so the agents work from one fixed set.",
  "Ask the agents your question and press start.",
  "Read what they found, and open the original line behind each claim.",
  "Hand over the briefing.",
];

export function HelpGuide() {
  const { bundle, ws } = useData();
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    queueMicrotask(() => {
      try {
        if (!localStorage.getItem(SEEN_KEY)) setOpen(true);
      } catch {}
    });
  }, []);

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (open && !node.open) node.showModal();
    if (!open && node.open) node.close();
  }, [open]);

  function close() {
    try { localStorage.setItem(SEEN_KEY, "true"); } catch {}
    setOpen(false);
  }

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="inline-flex min-h-10 shrink-0 items-center gap-2 border border-line bg-surface px-3 text-[13px] font-semibold hover:bg-surface-2" aria-haspopup="dialog">
        <HelpCircle aria-hidden="true" className="h-4 w-4" /> <span className="hidden sm:inline">Help</span>
      </button>
      <dialog
        ref={dialog}
        aria-labelledby="sherlock-help-title"
        onCancel={(event) => { event.preventDefault(); close(); }}
        onClick={(event) => { if (event.target === event.currentTarget) close(); }}
        className="m-auto max-h-[90vh] w-[min(760px,calc(100vw-2rem))] overflow-auto border border-line bg-surface p-0 text-ink shadow-2xl backdrop:bg-ink/40"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-surface px-5 py-4">
          <div>
            <p className="font-num text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-dim">Sherlock guide</p>
            <h2 id="sherlock-help-title" className="mt-1 text-xl font-bold">From a school&rsquo;s records to a briefing you can hand over</h2>
          </div>
          <button type="button" onClick={close} className="grid h-10 w-10 place-items-center border border-line hover:bg-surface-2" aria-label="Close help">
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-6 p-5 text-[14px] leading-6">
          <p>There are three screens, in the order the work happens. Everything you see on them comes from the files you uploaded or from what the agents did with them.</p>
          <ol className="grid gap-px border border-line bg-line">
            {NAV.map((item, index) => (
              <li key={item.id} className="bg-surface p-4">
                <b>{index + 1}. {item.label}</b>
                <p className="mt-1 text-ink-dim">{SCREENS[item.id]}</p>
              </li>
            ))}
          </ol>
          <div>
            <h3 className="font-semibold">Start to finish</h3>
            <ol className="mt-3 grid gap-2 sm:grid-cols-2">
              {HOW.map((step, index) => (
                <li key={step} className="flex gap-3 border-t border-line pt-2">
                  <span className="font-num text-ink-dim">{index + 1}</span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </div>
          <div className="border-l-2 border-ink bg-surface-2 p-4">
            <h3 className="font-semibold">The quickest way to try it</h3>
            <p className="mt-1 text-ink-dim">
              On <b>Books</b>, add a school, open <b>Try a fictional sample record pack</b> and stage it, then preview the import and commit it. Now go to <b>Investigation</b> and press start. That last press is the only thing that makes a paid model call; nothing during setup does.
            </p>
          </div>
          <p className="text-[12px] text-ink-dim">
            {ws ? <>Current school: <b className="text-ink">{bundle.workspace.name}</b> · {bundle.workspace.period}.</> : "No school has been added yet."} Books always shows the next step from where you actually are.
          </p>
          <button type="button" onClick={close} className="min-h-10 bg-ink px-4 text-[13px] font-semibold text-white hover:bg-ink-dim">Start</button>
        </div>
      </dialog>
    </>
  );
}
