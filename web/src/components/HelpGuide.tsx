"use client";

import { useEffect, useRef, useState } from "react";
import { HelpCircle, X } from "lucide-react";
import { useData } from "@/lib/data";
import { NAV } from "@/lib/tabs";

const SEEN_KEY = "sherlock.help.seen.v1";

/** What each screen is for, in the order the work happens. */
const SCREENS: Record<string, string> = {
  books: "Create an institution, upload files, check the import and commit the records.",
  investigation: "Set a review question, start the agents and inspect their findings and evidence.",
  agents: "Watch every task the agents are running: the steps taken, the evidence read and what stopped for you.",
  briefing: "Review the results, unresolved questions and follow-up. Export a report.",
};

const HOW = [
  "Add a company and the period its records cover.",
  "Add the company's CSV record files, and its documents as PDFs.",
  "Check how each file was read, and fix anything flagged.",
  "Commit the records, so the agents work from one fixed set.",
  "Set a review question and start the investigation.",
  "Read what they found, and open the original line behind each claim.",
  "Review and export the briefing.",
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
            <h2 id="sherlock-help-title" className="mt-1 text-xl font-bold">Using Sherlock</h2>
          </div>
          <button type="button" onClick={close} className="grid h-10 w-10 place-items-center border border-line hover:bg-surface-2" aria-label="Close help">
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-6 p-5 text-[14px] leading-6">
          <p>Start with Books, then open Investigation and Briefing.</p>
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
          <p className="text-[12px] text-ink-dim">
            {ws ? <>Current company: <b className="text-ink">{bundle.workspace.name}</b> · {bundle.workspace.period}.</> : "No company has been added yet."} Books shows the next step.
          </p>
          <button type="button" onClick={close} className="min-h-10 bg-ink px-4 text-[13px] font-semibold text-white hover:bg-ink-dim">Start</button>
        </div>
      </dialog>
    </>
  );
}
