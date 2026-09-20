"use client";

import { useEffect, useMemo, useState } from "react";

import { API_URL, intakeApi, useData } from "@/lib/data";
import type { Coverage, SourceDetail } from "@/lib/types";
import { buildVault, describeNode, ROLE_LABEL, ROLE_PURPOSE, type ReviewFinding } from "@/lib/vault";
import { Button } from "@/components/ui";
import { KIND_LABEL, VaultGraph } from "./VaultGraph";

interface ReviewPayload { findings?: ReviewFinding[] }

/** Keyed by node id so a stale read is ignored rather than cleared by a
 *  synchronous setState, which the react-hooks compiler rule disallows. */
interface Opened { id: string; source: SourceDetail | null; error: string }

/**
 * The review's files, and how they hold each other up.
 *
 * The map is the page. Every line on it was published by the server: a check is
 * joined to a file because the check requires that file's role, and a finding to
 * a file because it cited that file. Clicking anything explains it.
 */
export function Vault({ ws }: { ws: string }) {
  const { apiError } = useData();
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [findings, setFindings] = useState<ReviewFinding[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  // One piece of state, so each path in the effect below makes exactly one
  // update. Two calls trip react-hooks/set-state-in-effect.
  const [opened, setOpened] = useState<Opened | null>(null);

  useEffect(() => {
    if (!ws) return;
    let mounted = true;
    Promise.all([
      intakeApi<Coverage>(`/api/workspaces/${encodeURIComponent(ws)}/coverage`),
      intakeApi<ReviewPayload>(`/api/workspaces/${encodeURIComponent(ws)}/review`),
    ])
      .then(([c, r]) => { if (mounted) { setCoverage(c); setFindings(r.findings ?? []); } })
      .catch(() => { /* The shared status line reports outages. */ });
    return () => { mounted = false; };
  }, [ws]);

  const graph = useMemo(() => buildVault(coverage, findings), [coverage, findings]);
  const described = selected ? describeNode(graph, selected) : null;

  // Reading a file is a separate request, made only when one is opened.
  useEffect(() => {
    const node = described?.node;
    if (!node || node.kind !== "file" || !node.sourceId) return;
    const nodeId = node.id;
    let mounted = true;
    intakeApi<SourceDetail>(`/api/workspaces/${encodeURIComponent(ws)}/sources/${encodeURIComponent(node.sourceId)}`)
      .then((d) => { if (mounted) setOpened({ id: nodeId, source: d, error: "" }); })
      .catch((e) => {
        if (mounted) setOpened({ id: nodeId, source: null, error: e instanceof Error ? e.message : "That file could not be opened." });
      });
    return () => { mounted = false; };
  }, [described?.node, ws]);

  const current = opened && opened.id === selected ? opened : null;
  const source = current?.source ?? null;
  const error = current?.error ?? "";

  const counts = useMemo(() => ({
    file: graph.nodes.filter((n) => n.kind === "file").length,
    check: graph.nodes.filter((n) => n.kind === "check").length,
    finding: graph.nodes.filter((n) => n.kind === "finding").length,
    missing: graph.nodes.filter((n) => n.kind === "missing").length,
  }), [graph]);

  if (!ws) {
    return <p className="border border-line bg-surface-2 p-5 text-[14px]">
      No school selected yet. Add one on Books to upload records.
    </p>;
  }

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px]">
        {(["file", "check", "finding", "missing"] as const).map((kind) => (
          <span key={kind} className="flex items-center gap-2">
            <span
              aria-hidden
              className="inline-block h-2.5 w-2.5"
              style={{ background: { file: "#09090b", check: "#52525b", finding: "#b45309", missing: "#dc2626" }[kind] }}
            />
            <span className="font-num font-semibold">{counts[kind]}</span>
            <span className="text-ink-dim">{KIND_LABEL[kind]}</span>
          </span>
        ))}
        <span className="ml-auto font-accent text-[12.5px] text-ink-faint">
          Drag to rotate · scroll to zoom · click anything
        </span>
      </div>

      <VaultGraph graph={graph} selected={selected} onSelect={setSelected} />

      {apiError && <p role="alert" className="mt-3 bg-red-50 p-3 text-[13px] text-accent-bad">{apiError}</p>}

      <div className="mt-6">
        {!described ? (
          <p className="border border-line bg-surface-2 p-5 text-[14px]">
            Click a point to see what it is, what depends on it, and what it produced. Red points
            are required by a check and have not been supplied.
          </p>
        ) : (
          <article className="border border-line bg-surface p-5">
            <div className="flex flex-wrap items-baseline gap-3">
              <h2 className="text-[17px] font-semibold">{described.node.label}</h2>
              <span className="font-accent text-[12.5px] text-ink-dim">
                {KIND_LABEL[described.node.kind]}
                {described.node.role ? ` · ${ROLE_LABEL[described.node.role] ?? described.node.role}` : ""}
                {described.node.status ? ` · ${described.node.status.replaceAll("_", " ")}` : ""}
              </span>
              <Button onClick={() => setSelected(null)}>Close</Button>
            </div>

            <p className="mt-3 max-w-[70ch] text-[14px] leading-relaxed">{described.node.detail}</p>

            <div className="mt-5 grid gap-5 md:grid-cols-2">
              {described.requiredBy.length > 0 && (
                <Relations title="Why it is needed" note="Checks that cannot run without it">
                  {described.requiredBy.map((n) => (
                    <Row key={n.id} label={n.label} onClick={() => setSelected(n.id)} />
                  ))}
                </Relations>
              )}
              {described.requires.length > 0 && (
                <Relations title="What it reads" note="Files this check depends on">
                  {described.requires.map((n) => (
                    <Row key={n.id} label={n.label} missing={n.kind === "missing"} onClick={() => setSelected(n.id)} />
                  ))}
                </Relations>
              )}
              {described.citedBy.length > 0 && (
                <Relations title="What came out of it" note="Findings that quote this file">
                  {described.citedBy.map((n) => (
                    <Row key={n.id} label={n.label} onClick={() => setSelected(n.id)} />
                  ))}
                </Relations>
              )}
              {described.cites.length > 0 && (
                <Relations title="Evidence behind it" note="Files this finding quotes">
                  {described.cites.map((n) => (
                    <Row key={n.id} label={n.label} onClick={() => setSelected(n.id)} />
                  ))}
                </Relations>
              )}
            </div>

            {described.node.kind === "missing" && (
              <p className="mt-5 border border-line bg-surface-2 p-4 text-[14px]">
                Upload a file for <b>{ROLE_LABEL[described.node.role ?? ""] ?? described.node.role}</b> on
                Books to close this gap. {ROLE_PURPOSE[described.node.role ?? ""] ?? ""}
              </p>
            )}

            {error && <p role="alert" className="mt-4 bg-red-50 p-3 text-[13px] text-accent-bad">{error}</p>}

            {source && (
              <section className="mt-5">
                <div className="flex flex-wrap items-baseline gap-2">
                  <h3 className="text-[14px] font-semibold">What the agents read</h3>
                  <span className="font-accent text-[12.5px] text-ink-dim">
                    {source.line_count} {source.line_count === 1 ? "line" : "lines"}
                  </span>
                </div>
                <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap border border-line bg-surface-2 p-3 text-[12.5px] leading-relaxed">
                  {source.lines.map((l) => `${String(l.number).padStart(4, " ")}  ${l.text}`).join("\n")}
                </pre>
                <a
                  href={`${API_URL}/api/workspaces/${encodeURIComponent(ws)}/sources/${encodeURIComponent(source.id)}/download`}
                  className="mt-3 inline-block border border-line px-3 py-2 text-[13px] hover:bg-surface-2"
                >
                  Download the original
                </a>
              </section>
            )}
          </article>
        )}
      </div>
    </>
  );
}

function Relations({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="text-[14px] font-semibold">{title}</h3>
      <p className="mb-2 text-[12.5px] text-ink-dim">{note}</p>
      <ul className="grid gap-1">{children}</ul>
    </section>
  );
}

function Row({ label, missing, onClick }: { label: string; missing?: boolean; onClick: () => void }) {
  return (
    <li>
      <button
        onClick={onClick}
        className="w-full border border-line p-2 text-left text-[13px] hover:bg-surface-2"
      >
        {missing && <span className="mr-2 font-semibold text-accent-bad">missing</span>}
        {label}
      </button>
    </li>
  );
}
