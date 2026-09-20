"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";

import { Pill } from "@/components/ui";
import { API_URL, intakeApi } from "@/lib/data";
import { displayLabel } from "@/lib/format";
import type { FileNode } from "@/lib/fileLibrary";
import type { SourceDetail } from "@/lib/types";

/** A file the open one is joined to, and which way the join runs. */
export interface PreviewJoin { node: FileNode; label: string; direction: "from" | "to" }

function shortHash(sha: string) {
  return sha ? sha.slice(0, 8) : "";
}

function uploadedOn(value: string | null) {
  if (!value) return null;
  const at = new Date(value);
  return Number.isNaN(at.getTime())
    ? null
    : at.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/**
 * One file, opened over the library.
 *
 * What it holds is the point: a citation names a file and a line, so the lines
 * are here with their numbers, exactly as the agents read them. Everything else
 * — what it is, whether it is still in use, where it came from — sits above
 * them rather than on a separate screen.
 */
export function FilePreview({
  ws,
  file,
  joins,
  onSelect,
  onClose,
}: {
  ws: string;
  file: FileNode;
  joins: PreviewJoin[];
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [detail, setDetail] = useState<{ id: string; source: SourceDetail | null; error: string } | null>(null);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (node && !node.open) node.showModal();
  }, []);

  /**
   * Plays the exit before unmounting.
   *
   * The parent drops this component the moment it closes, so an exit animation
   * has to finish first: `leaving` runs it, and onClose is called after. The
   * timeout matches the transition below, and prefers-reduced-motion collapses
   * the transition to nothing, so the wait is the only part left — short enough
   * not to read as lag.
   */
  const requestClose = useCallback(() => {
    if (leaving) return;
    setLeaving(true);
    window.setTimeout(onClose, 160);
  }, [leaving, onClose]);

  // Documents are not parsed into lines, so only a committed source is read.
  useEffect(() => {
    if (file.kind === "document") return;
    const id = file.id;
    let mounted = true;
    intakeApi<SourceDetail>(`/api/workspaces/${encodeURIComponent(ws)}/sources/${encodeURIComponent(id.slice(4))}`)
      .then((source) => { if (mounted) setDetail({ id, source, error: "" }); })
      .catch((e) => {
        if (mounted) setDetail({ id, source: null, error: e instanceof Error ? e.message : "This file could not be read." });
      });
    return () => { mounted = false; };
  }, [file.id, file.kind, ws]);

  const current = detail && detail.id === file.id ? detail : null;
  const source = current?.source ?? null;
  const original = file.kind === "document"
    ? `${API_URL}/api/workspaces/${encodeURIComponent(ws)}/extraction/documents/${file.id.slice(4)}/original`
    : `${API_URL}/api/workspaces/${encodeURIComponent(ws)}/sources/${file.id.slice(4)}/download`;

  return (
    <dialog
      ref={ref}
      onCancel={(e) => { e.preventDefault(); requestClose(); }}
      onClick={(e) => { if (e.target === ref.current) requestClose(); }}
      aria-label={file.name}
      // The dialog is only the layer: it carries the backdrop and centres the
      // panel, so the panel itself is free to move without fighting the
      // element's own top-layer placement.
      className="fixed inset-0 m-0 h-full max-h-none w-full max-w-none bg-transparent p-4 backdrop:animate-fade-in backdrop:bg-ink/30"
    >
      <motion.div
        initial={{ opacity: 0, y: -10, scale: 0.97 }}
        animate={leaving ? { opacity: 0, y: -6, scale: 0.98 } : { opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: leaving ? 0.16 : 0.2, ease: "easeOut" }}
        className="mx-auto max-h-[86vh] w-[min(940px,95vw)] overflow-auto border border-line bg-surface p-6 shadow-xl"
      >
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="truncate text-[19px] font-semibold">{file.name}</h2>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Pill tone={file.current ? "green" : "gray"}>{file.current ? "In use" : "Superseded"}</Pill>
            <Pill tone="gray">{file.kind === "document" ? "Uploaded document" : "Committed file"}</Pill>
            <Pill tone="gray">{displayLabel(file.role)}</Pill>
            <Pill tone="gray">Version {file.version}</Pill>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <a
            href={original}
            target="_blank"
            rel="noreferrer"
            className="border border-line bg-ink px-3 py-2 text-[13px] font-semibold text-white hover:bg-ink-dim"
          >
            Download
          </a>
          <button type="button" onClick={requestClose} className="border border-line px-3 py-2 text-[13px] hover:bg-surface-2">
            Close
          </button>
        </div>
      </header>

      {!file.current && (
        <p className="mt-4 border border-line bg-surface-2 p-3 text-[13px]">
          A later upload replaced this file. It is kept because a finding raised against it still
          points here.
        </p>
      )}

      <dl className="mt-5 grid gap-x-8 gap-y-2 text-[13px] sm:grid-cols-2">
        <div className="flex gap-2"><dt className="text-ink-dim">Checksum</dt><dd className="font-mono">{shortHash(file.sha256)}</dd></div>
        {uploadedOn(file.uploadedAt) && (
          <div className="flex gap-2"><dt className="text-ink-dim">Uploaded</dt><dd>{uploadedOn(file.uploadedAt)}</dd></div>
        )}
        {file.pageCount !== null && (
          <div className="flex gap-2"><dt className="text-ink-dim">Pages read</dt><dd className="font-num">{file.pageCount}</dd></div>
        )}
        {file.recordCount !== null && (
          <div className="flex gap-2"><dt className="text-ink-dim">Live records</dt><dd className="font-num">{file.recordCount}</dd></div>
        )}
      </dl>

      <section className="mt-6">
        <div className="flex flex-wrap items-baseline gap-3">
          <h3 className="text-[14px] font-semibold">What it holds</h3>
          {source && (
            <span className="font-accent text-[12.5px] text-ink-dim">
              {source.line_count} {source.line_count === 1 ? "line" : "lines"}
              {source.lines.length < source.line_count ? `, showing the first ${source.lines.length}` : ""}
            </span>
          )}
        </div>

        {file.kind === "document" ? (
          <p className="mt-2 border border-line bg-surface-2 p-4 text-[13.5px]">
            This is the document as it was uploaded, not a parsed table. Open the original to read
            it; the records taken from it appear as their own committed files.
          </p>
        ) : current?.error ? (
          <p role="alert" className="mt-2 bg-red-50 p-3 text-[13px] text-accent-bad">{current.error}</p>
        ) : !source ? (
          <p className="mt-2 text-[13px] text-ink-dim">Reading the file…</p>
        ) : (
          <pre className="mt-2 max-h-[22rem] overflow-auto whitespace-pre border border-line bg-surface-2 p-3 text-[12.5px] leading-relaxed">
            {source.lines.map((l) => `${String(l.number).padStart(4, " ")}  ${l.text}`).join("\n")}
          </pre>
        )}
      </section>

      {joins.length > 0 && (
        <section className="mt-6">
          <h3 className="text-[14px] font-semibold">How it connects</h3>
          <ul className="mt-2 space-y-1 text-[13px]">
            {joins.map((join) => (
              <li key={`${join.direction}:${join.node.id}`}>
                <span className="text-ink-dim">{join.direction === "to" ? `${join.label} → ` : `← ${join.label} `}</span>
                <button type="button" className="underline hover:no-underline" onClick={() => onSelect(join.node.id)}>
                  {join.node.name}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      </motion.div>
    </dialog>
  );
}
