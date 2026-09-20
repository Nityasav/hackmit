"use client";

import { useEffect, useState } from "react";
import { api, intakeApi } from "@/lib/api";

type AuditReport = {
  headline: string; executive_summary: string; stale: boolean; status: string;
  workspace: { name: string; start: string; end: string }; created_at: string;
  counts: { attention: number; gap: number; pass: number; pending: number };
  domains: { id: string; name: string; recorded: number; total: number; not_assessed: string[] }[];
  unresolved: string[];
  findings: { id: string; title: string; status: string; explanation: string; action: string; review: string }[];
};

export function AuditDeliverable({ ws, thread }: { ws: string; thread: string }) {
  const [report, setReport] = useState<AuditReport | null>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const path = `/api/workspaces/${encodeURIComponent(ws)}/audit-reports/${encodeURIComponent(thread)}`;
  useEffect(() => {
    const controller = new AbortController();
    void intakeApi<AuditReport>(path, { signal: controller.signal }).then(setReport).catch(e => {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Report unavailable.");
    });
    return () => controller.abort();
  }, [path]);
  async function download() {
    setDownloading(true); setError("");
    try {
      const response = await api.get(path + "/pdf", { responseType: "blob", timeout: 60000 });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url; link.download = "sherlock-financial-audit.pdf";
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setError("PDF export failed. Your recorded report is still available here."); }
    finally { setDownloading(false); }
  }
  return <section aria-label="Financial audit deliverable" className="border-t border-line bg-white p-5 sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-xs font-semibold uppercase tracking-widest text-ink-dim">Financial audit deliverable</p>
        <h3 className="mt-2 text-xl font-semibold">{report?.headline || "Preparing recorded report…"}</h3></div>
      <button onClick={() => void download()} disabled={!report || downloading} className="shrink-0 bg-ink px-4 py-3 text-sm font-semibold text-white disabled:opacity-40">{downloading ? "Preparing PDF…" : "Download audit PDF"}</button>
    </div>
    {error && <p role="alert" className="mt-3 text-sm text-red-800">{error}</p>}
    {report && <>
      <p className="mt-2 text-xs text-ink-dim">{report.workspace.name} · {report.workspace.start} to {report.workspace.end} · {new Date(report.created_at).toLocaleString()}</p>
      {report.stale && <p className="mt-3 border border-amber-200 bg-amber-50 p-3 text-sm">Historical report: the books have changed or the original snapshot is unknown.</p>}
      <p className="mt-4 max-w-3xl text-sm leading-relaxed">{report.executive_summary}</p>
      <div className="my-5 grid grid-cols-2 gap-3 sm:grid-cols-4">{[
        ["Need attention", report.counts.attention], ["Evidence gaps", report.counts.gap],
        ["Passed in scope", report.counts.pass], ["Pending decisions", report.counts.pending],
      ].map(([label, value]) => <div key={label} className="border border-line bg-surface-2 p-3"><p className="text-2xl font-semibold tabular-nums">{value}</p><p className="mt-1 text-xs text-ink-dim">{label}</p></div>)}</div>
      <details className="border border-line p-4"><summary className="cursor-pointer text-sm font-semibold">Coverage, findings & next steps</summary>
        <div className="my-4 grid gap-3 sm:grid-cols-2">{report.domains.map(domain => <div key={domain.id} className="min-w-0 border border-line p-3">
          <div className="flex justify-between gap-3 text-sm"><b>{domain.name}</b><span className="shrink-0">{domain.recorded}/{domain.total}</span></div>
          <div className="my-2 h-1.5 bg-zinc-200"><div className="h-full bg-ink" style={{ width: `${domain.recorded / Math.max(1, domain.total) * 100}%` }} /></div>
          <p className="text-xs leading-relaxed text-ink-dim">{domain.not_assessed.length ? `No recorded contribution: ${domain.not_assessed.join(", ")}.` : "Every specialist has a recorded contribution. This is coverage, not assurance."}</p>
        </div>)}</div>
        {!!report.unresolved.length && <div className="mb-4 border border-amber-200 bg-amber-50 p-3"><h4 className="text-sm font-semibold">Unresolved scope & evidence</h4><ul className="mt-2 list-disc space-y-2 pl-4 text-xs leading-relaxed">{report.unresolved.map((gap, i) => <li key={i}>{gap}</li>)}</ul></div>}
        <div className="max-h-[32rem] space-y-3 overflow-y-auto">{report.findings.map((finding, i) => <details key={finding.id || i} className="border border-line p-3">
          <summary className="cursor-pointer text-sm font-semibold">{finding.title} <span className="ml-2 text-xs font-normal text-ink-dim">{finding.status === "attention" ? "Needs attention" : finding.status === "gap" ? "Evidence gap" : "Passed in scope"}</span></summary>
          <p className="mt-3 text-sm leading-relaxed">{finding.explanation}</p><p className="mt-2 text-sm leading-relaxed"><b>Next step:</b> {finding.action}</p><p className="mt-2 text-xs text-ink-dim">{finding.review}</p>
        </details>)}</div>
      </details>
      <p className="mt-3 text-xs text-ink-dim">Automated review of supplied books. Not a certified audit or independent audit opinion. Nothing is posted or paid.</p>
    </>}
  </section>;
}
