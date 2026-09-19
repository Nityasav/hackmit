"use client";

import { useData } from "@/lib/data";
import { money } from "@/lib/format";
import type { Bundle } from "@/lib/types";
import { AgentAvatar, AiTag, Button, Card, CardTitle, FindingStatusPill, PageHeader, Pill } from "@/components/ui";
import AdvancedStats from "@/components/ui/advanced-stats";

export default function ReportsPage() {
  const { bundle } = useData();
  const { report, workspace, findings, approvals } = bundle;
  const gate = report.applies_approval ? approvals.find((a) => a.id === report.applies_approval) : undefined;
  const applied = !gate || gate.status === "approved";
  const beforeLabel = report.before_label ?? "As reported";
  const afterLabel = report.after_label ?? (applied ? "After approved fixes" : `After ${gate?.id} (pending)`);

  if (workspace.intake) return <><PageHeader title="Reports" subtitle="No investigation report yet" /><Card>Your uploaded sources are available in the Command center. An agent investigation and independent review must run before findings or financial reports can be generated.</Card></>;

  return (
    <>
      <PageHeader title="Reports" subtitle="Written by the CFO Agent from verified findings only" />

      <div className="mb-2.5">
        <AdvancedStats />
      </div>

      <div className="grid gap-2.5 min-[900px]:grid-cols-2">
        <Card>
          <CardTitle>
            <AgentAvatar id="cfo" size="sm" />
            {report.title}
            <span className="ml-1">
              <AiTag>AI-written</AiTag>
            </span>
          </CardTitle>
          <ol className="mb-2 list-inside list-decimal text-[12.5px] text-ink-dim">
            {report.sections.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          <div className="flex flex-wrap gap-1.5">
            <Button primary onClick={() => download(`${workspace.id}-report.md`, toMarkdown(bundle))}>
              Export Markdown
            </Button>
            <Button onClick={() => download(`${workspace.id}-bundle.json`, JSON.stringify(bundle, null, 2))}>
              Export JSON
            </Button>
          </div>
          <div className="mt-2 text-[11px] text-ink-dim">
            Every claim in the export carries its finding ID, evidence and status. Unresolved items stay in their own
            section instead of being dropped.
          </div>
        </Card>

        <Card>
          <CardTitle right={applied ? undefined : "preview until you approve"}>
            {beforeLabel} vs {afterLabel}
          </CardTitle>
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-[10px] text-ink-dim">
                <th className="border-b border-line p-1.5 text-left font-semibold">Measure</th>
                <th className="border-b border-line p-1.5 text-right font-semibold">{beforeLabel}</th>
                <th className="border-b border-line p-1.5 text-right font-semibold">{afterLabel}</th>
              </tr>
            </thead>
            <tbody>
              {report.comparisons.map((c) => (
                <tr key={c.label}>
                  <td className="border-b border-line p-1.5">{c.label}</td>
                  <td className="border-b border-line p-1.5 text-right font-mono">{c.before}</td>
                  <td className={`border-b border-line p-1.5 text-right font-mono ${applied ? "" : "text-ink-faint"}`}>
                    {c.after}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {gate && (
            <div className="mt-2">
              <Pill tone={applied ? "green" : "amber"}>
                {applied ? `${gate.id} approved and applied` : `Waiting on your approval of ${gate.id}`}
              </Pill>
            </div>
          )}
        </Card>

        <Card className="min-[900px]:col-span-2">
          <CardTitle>Findings in this pack</CardTitle>
          {findings.map((f) => (
            <div key={f.id} className="flex items-center gap-2 border-t border-line py-1.5 first:border-t-0">
              <span className="font-mono text-[10.5px] text-ink-faint">{f.id}</span>
              <b>{f.title}</b>
              <span className="truncate text-ink-dim">{f.summary}</span>
              <span className="ml-auto flex flex-none items-center gap-1.5">
                {f.amount_cents != null && <span className="font-mono">{money(f.amount_cents)}</span>}
                <FindingStatusPill status={f.status} />
              </span>
            </div>
          ))}
        </Card>
      </div>
    </>
  );
}

function toMarkdown(b: Bundle): string {
  const lines: string[] = [
    `# ${b.report.title}`,
    "",
    `- Institution: ${b.workspace.name} (${b.workspace.kind === "public" ? "public report" : "synthetic scenario"})`,
    `- Period: ${b.workspace.period}`,
    `- Snapshot: ${b.workspace.snapshot_id}`,
    `- Model: ${b.workspace.model}`,
    "",
    "## Findings",
    "",
    "| ID | Finding | Status | Amount | Found by | Verified by |",
    "| --- | --- | --- | ---: | --- | --- |",
    ...b.findings.map(
      (f) =>
        `| ${f.id} | ${f.title} | ${f.status} | ${f.amount_cents == null ? "—" : money(f.amount_cents)} | ${f.agent} | ${f.verified_by ?? "—"} |`,
    ),
    "",
    "## Evidence",
    "",
    ...b.findings.flatMap((f) => [`### ${f.id} — ${f.title}`, "", ...f.evidence.map((e) => `- ${e.label}${e.edge ? ` → ${e.edge}` : ""}`), ""]),
    "## Decisions requested",
    "",
    ...b.approvals.map((a) => `- **${a.id}** ${a.title} — ${a.status}`),
    "",
    "## Limitations",
    "",
    "- Amounts come from the deterministic calculation engine; narrative is generated from accepted findings only.",
    "- Unresolved items remain unresolved. No clean opinion is implied.",
    b.workspace.kind === "public"
      ? "- Public-report mode is read-only. No claim is made about records the report does not contain."
      : "- All institutions, people and transactions in this scenario are fictional.",
    "",
  ];
  return lines.join("\n");
}

function download(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
