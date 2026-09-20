"use client";

import { useEffect, useMemo, useState } from "react";

import { FileCard } from "@/components/ui/file-card-collections";
import { AnimatedDropdown } from "@/components/ui/animated-dropdown";
import { Section } from "@/components/ui";
import { intakeApi, useData } from "@/lib/data";
import { displayLabel } from "@/lib/format";
import { buildFileLibrary, type LibraryDocument } from "@/lib/fileLibrary";
import type { Coverage } from "@/lib/types";
import { FileGraph } from "./FileGraph";
import { FilePreview, type PreviewJoin } from "./FilePreview";

/** Only the part of the extraction payload this screen reads. */
interface ExtractionState { documents: LibraryDocument[] }

/** One state object, so each path through the effect makes exactly one update. */
interface Loaded { coverage: Coverage | null; documents: LibraryDocument[] }

type Filter = "all" | "document" | "source";

/**
 * Everything this institution holds, as files.
 *
 * Two stores feed it and both are shown: documents someone uploaded to be read,
 * and the committed files the records were parsed out of. Nothing here is
 * generated for display — a file appears because the server listed it, and two
 * files are joined only where the server recorded the join.
 */
export function FileLibrary({ ws }: { ws: string }) {
  const { apiError } = useData();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [role, setRole] = useState("");

  useEffect(() => {
    if (!ws) return;
    let mounted = true;
    const at = encodeURIComponent(ws);
    Promise.all([
      intakeApi<Coverage>(`/api/workspaces/${at}/coverage`),
      // A workspace with no documents still answers here, so a failure is a real
      // outage rather than an empty shelf; the shared status line reports it.
      intakeApi<ExtractionState>(`/api/workspaces/${at}/extraction`).catch(() => ({ documents: [] })),
    ])
      .then(([coverage, extraction]) => {
        if (mounted) setLoaded({ coverage, documents: extraction.documents ?? [] });
      })
      .catch(() => { /* Reported by the status line in the top bar. */ });
    return () => { mounted = false; };
  }, [ws]);

  const library = useMemo(
    () => buildFileLibrary(loaded?.coverage ?? null, loaded?.documents ?? []),
    [loaded],
  );

  const roles = useMemo(
    () => [...new Set(library.nodes.map((n) => n.role))].sort(),
    [library],
  );

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return library.nodes.filter((n) =>
      (filter === "all" || n.kind === filter) &&
      (!role || n.role === role) &&
      (!needle || n.name.toLowerCase().includes(needle) || n.role.toLowerCase().includes(needle)));
  }, [library, query, filter, role]);

  const open = useMemo(() => library.nodes.find((n) => n.id === selected) ?? null, [library, selected]);

  const joins = useMemo(() => {
    const found: PreviewJoin[] = [];
    if (!open) return found;
    const byId = new Map(library.nodes.map((n) => [n.id, n]));
    for (const edge of library.edges) {
      const other = edge.from === open.id ? byId.get(edge.to) : edge.to === open.id ? byId.get(edge.from) : undefined;
      if (!other) continue;
      found.push({ node: other, label: edge.label, direction: edge.from === open.id ? "to" : "from" });
    }
    return found;
  }, [library, open]);

  if (!ws) {
    return <p className="border border-line bg-surface p-5 text-[13px] text-ink-dim">Create an institution to see its files.</p>;
  }
  if (!loaded) {
    return <p className="text-[13px] text-ink-dim">{apiError ? "" : "Opening this institution’s files…"}</p>;
  }

  const documents = library.nodes.filter((n) => n.kind === "document").length;
  const sources = library.nodes.length - documents;

  return (
    <div>
      <Section first>
        <div className="flex flex-wrap items-center gap-3">
          <input
            className="min-w-56 flex-1 border border-line bg-white p-2 text-sm"
            placeholder="Search by name or kind"
            aria-label="Search files"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <AnimatedDropdown
            aria-label="Show"
            value={filter}
            onChange={(value) => setFilter(value as Filter)}
            options={[
              { value: "all", label: `Everything (${library.nodes.length})` },
              { value: "document", label: `Uploaded documents (${documents})` },
              { value: "source", label: `Committed files (${sources})` },
            ]}
          />
          <AnimatedDropdown
            aria-label="Kind of record"
            value={role}
            onChange={setRole}
            // "Every kind" is the way back to an unfiltered list, not a placeholder, so it
            // stays a choosable row.
            options={[{ value: "", label: "Every kind" }, ...roles.map((r) => ({ value: r, label: displayLabel(r) }))]}
          />
        </div>

        {shown.length === 0 ? (
          <p className="mt-6 text-[13px] text-ink-dim">
            {library.nodes.length === 0
              ? "Nothing uploaded to this institution yet. Add records or a document on Books and they will appear here."
              : "No file matches that search."}
          </p>
        ) : (
          <ul className="mt-6 flex flex-wrap gap-x-4 gap-y-7">
            {shown.map((node) => (
              <li key={node.id}>
                <button
                  type="button"
                  title={node.name}
                  aria-pressed={node.id === selected}
                  onClick={() => setSelected(node.id === selected ? null : node.id)}
                  className={`flex w-32 flex-col items-center gap-2 rounded-md border p-3 text-center transition-colors hover:bg-surface-2 ${node.id === selected ? "border-ink bg-surface-2" : "border-transparent"}`}
                >
                  <FileCard formatFile={node.format} />
                  <span className="mt-1 w-full truncate text-[12px] font-medium text-ink">{node.name}</span>
                  <span className="w-full truncate text-[11px] text-ink-dim">
                    {displayLabel(node.role)} · v{node.version}
                  </span>
                  {!node.current && <span className="text-[10.5px] uppercase tracking-wide text-ink-faint">superseded</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {open && (
        <FilePreview
          ws={ws}
          file={open}
          joins={joins}
          onSelect={setSelected}
          onClose={() => setSelected(null)}
        />
      )}

      <Section title="How these files connect" right={`${library.edges.length} link${library.edges.length === 1 ? "" : "s"}`}>
        <FileGraph library={library} selected={selected} onSelect={(id) => setSelected(id === selected ? null : id)} />
      </Section>
    </div>
  );
}
