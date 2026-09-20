"use client";

import { useEffect, useRef, useState } from "react";
import { HelpCircle, X } from "lucide-react";
import { useData } from "@/lib/data";

const SEEN_KEY = "sherlock.help.seen.v1";

export function HelpGuide() {
  const { bundle } = useData();
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
      <dialog ref={dialog} aria-labelledby="sherlock-help-title" onCancel={(event) => { event.preventDefault(); close(); }} onClick={(event) => { if (event.target === event.currentTarget) close(); }} className="m-auto max-h-[90vh] w-[min(760px,calc(100vw-2rem))] overflow-auto border border-line bg-surface p-0 text-ink shadow-2xl backdrop:bg-ink/40">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-surface px-5 py-4">
          <div><p className="font-num text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-dim">Sherlock guide</p><h2 id="sherlock-help-title" className="mt-1 text-xl font-bold">From records to a reviewable CFO report</h2></div>
          <button type="button" onClick={close} className="grid h-10 w-10 place-items-center border border-line hover:bg-surface-2" aria-label="Close help"><X aria-hidden="true" className="h-4 w-4" /></button>
        </div>
        <div className="space-y-6 p-5 text-[14px] leading-6">
          <p>Sherlock turns a committed set of finance records into cited agent work. It keeps source files, investigation results, human decisions, and reports connected so you can trace every claim.</p>
          <div className="grid gap-px border border-line bg-line sm:grid-cols-2">
            <div className="bg-surface p-4"><b>Recorded examples</b><p className="mt-1 text-ink-dim">Sandbox University and MIT FY2025 are saved demonstrations. Browse them safely; nothing is running and their controls do not change live records.</p></div>
            <div className="bg-surface p-4"><b>Institution workspaces</b><p className="mt-1 text-ink-dim">A workspace you create starts empty. You choose sources, validate them, commit a snapshot, and explicitly start any model call.</p></div>
          </div>
          <div>
            <h3 className="font-semibold">How the workflow works</h3>
            <ol className="mt-3 grid gap-2 sm:grid-cols-2">
              {["Create an institution workspace.", "Add CSV, TXT, or Markdown records.", "Preview mappings and resolve validation issues.", "Commit the validated snapshot.", "Choose an agent and start the investigation.", "Review cited findings and decide proposals.", "Read the report generated from current state."].map((step, index) => <li key={step} className="flex gap-3 border-t border-line pt-2"><span className="font-num text-ink-dim">{index + 1}</span><span>{step}</span></li>)}
            </ol>
          </div>
          <div className="border-l-2 border-ink bg-surface-2 p-4">
            <h3 className="font-semibold">Fastest way to test it</h3>
            <p className="mt-1 text-ink-dim">Create a synthetic USD institution for September 1–30, 2026. In <b>Records &amp; investigation</b>, choose <b>Use fictional starter pack</b>, then <b>Preview import</b> and <b>Confirm &amp; commit records</b>. Finally choose an agent and press Run. That last click can use a configured model provider; no model call starts during setup.</p>
          </div>
          <p className="text-[12px] text-ink-dim">Current workspace: <b className="text-ink">{bundle.workspace.name}</b> · {bundle.workspace.intake ? "institution workspace" : "recorded example"}. The Command Center always shows the next available step from its current state.</p>
          <button type="button" onClick={close} className="min-h-10 bg-ink px-4 text-[13px] font-semibold text-white hover:bg-ink-dim">Start exploring</button>
        </div>
      </dialog>
    </>
  );
}
