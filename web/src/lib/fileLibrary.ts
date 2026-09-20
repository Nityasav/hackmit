import type { Coverage, CoverageSource } from "@/lib/types";
import { fileFormat } from "@/lib/fileFormat";
import type { FormatFileProps } from "@/components/ui/file-card-collections";

/**
 * Every file this workspace holds, and the joins between them that the server
 * actually recorded.
 *
 * Files arrive through two doors and the screen has to show both: a *document*
 * is what someone uploaded to be read (a PDF, a scanned invoice), and a *source*
 * is a committed file the records were parsed out of. A document that has been
 * reviewed and staged produces sources, which is the one relationship worth
 * drawing — it is how a number in the books traces back to a page.
 *
 * Three kinds of join exist in the data and no others are drawn:
 *
 *   revision  document -> document, when the newer one replaced the older
 *   revision  source   -> source,   consecutive versions of the same evidence
 *   derived   document -> source,   the source was staged from that document
 *
 * The third is read from `source_system === "reviewed-extraction"` and
 * `external_id === document.lineage_id`, both written by the staging endpoint.
 * A file uploaded straight into the books has no `external_id` and is joined to
 * nothing: it is shown as unconnected rather than guessed at. Two files are
 * never joined because they share a role, a name or an upload time — that would
 * draw a relationship the server never claimed.
 */

/** The staged shape of a document, as `GET /api/workspaces/{ws}/extraction` returns it. */
export interface LibraryDocument {
  id: string;
  name: string;
  role: string;
  sha256: string;
  suffix: string;
  version: number;
  lineage_id: string;
  replaces_id?: string | null;
  pages: { page: number }[];
}

export type FileNodeKind = "document" | "source";

export interface FileNode {
  /** Namespaced, because a document id and a source id are drawn from different tables. */
  id: string;
  kind: FileNodeKind;
  name: string;
  format: FormatFileProps;
  role: string;
  version: number;
  /** A source still answering for live records, or the newest document in its chain. */
  current: boolean;
  /** What ties revisions together: a document's lineage, a source's external id. */
  lineage: string;
  uploadedAt: string | null;
  /** Live records drawn from this file; null for a document, which holds none itself. */
  recordCount: number | null;
  pageCount: number | null;
  sha256: string;
}

export type FileEdgeKind = "revision" | "derived";

export interface FileEdge {
  from: string;
  to: string;
  kind: FileEdgeKind;
  /** Said in words on the screen, so an edge never has to be guessed from its shape. */
  label: string;
}

export interface FileLibrary {
  nodes: FileNode[];
  edges: FileEdge[];
}

const STAGED_BY_EXTRACTION = "reviewed-extraction";

export const documentNodeId = (id: string) => `doc:${id}`;
export const sourceNodeId = (id: string) => `src:${id}`;

function documentNode(doc: LibraryDocument, newest: boolean): FileNode {
  return {
    id: documentNodeId(doc.id),
    kind: "document",
    name: doc.name,
    format: fileFormat(doc.suffix || doc.name),
    role: doc.role,
    version: doc.version ?? 1,
    current: newest,
    lineage: doc.lineage_id || doc.id,
    // The extraction service does not timestamp a document, and inventing one
    // from the position in the list would read as fact on the card.
    uploadedAt: null,
    recordCount: null,
    pageCount: doc.pages?.length ?? null,
    sha256: doc.sha256,
  };
}

function sourceNode(source: CoverageSource): FileNode {
  return {
    id: sourceNodeId(source.id),
    kind: "source",
    name: source.name,
    format: fileFormat(source.name),
    role: source.role,
    version: source.source_version ?? 1,
    current: source.active,
    lineage: source.external_id || source.id,
    uploadedAt: source.uploaded_at || null,
    recordCount: source.record_count ?? 0,
    pageCount: null,
    sha256: source.sha256,
  };
}

export function buildFileLibrary(
  coverage: Coverage | null,
  documents: LibraryDocument[],
): FileLibrary {
  const sources = coverage?.sources ?? [];

  // A lineage's newest document is the one with the highest version. Anything
  // older is kept and shown, marked as replaced rather than hidden: it is still
  // the evidence behind whatever was staged from it at the time.
  const newestOfLineage = new Map<string, number>();
  for (const doc of documents) {
    const lineage = doc.lineage_id || doc.id;
    newestOfLineage.set(lineage, Math.max(newestOfLineage.get(lineage) ?? 0, doc.version ?? 1));
  }

  const nodes: FileNode[] = [
    ...documents.map((doc) =>
      documentNode(doc, (doc.version ?? 1) === newestOfLineage.get(doc.lineage_id || doc.id))),
    ...sources.map(sourceNode),
  ];

  const edges: FileEdge[] = [];
  const present = new Set(nodes.map((n) => n.id));

  // 1. A document that replaced another. `replaces_id` names it outright; where
  //    an older record predates that field, consecutive versions of one lineage
  //    are the same statement.
  const byLineage = new Map<string, LibraryDocument[]>();
  for (const doc of documents) {
    const lineage = doc.lineage_id || doc.id;
    byLineage.set(lineage, [...(byLineage.get(lineage) ?? []), doc]);
  }
  for (const chain of byLineage.values()) {
    const ordered = [...chain].sort((a, b) => (a.version ?? 1) - (b.version ?? 1));
    for (let i = 1; i < ordered.length; i++) {
      const previous = ordered[i].replaces_id
        ? ordered.find((d) => d.id === ordered[i].replaces_id)
        : ordered[i - 1];
      if (!previous || previous.id === ordered[i].id) continue;
      edges.push({
        from: documentNodeId(previous.id),
        to: documentNodeId(ordered[i].id),
        kind: "revision",
        label: `replaced by v${ordered[i].version ?? 1}`,
      });
    }
  }

  // 2. A source staged from a reviewed document, joined on the lineage the
  //    staging endpoint wrote into the file's options.
  // A lineage id is the id of the document that started the chain, so a file
  // carrying that external id names one exact document and not a guess about
  // which version was current when it was staged. Where the first document has
  // since been deleted, the oldest surviving one is the closest true answer.
  const documentOfLineage = new Map<string, LibraryDocument>();
  for (const doc of documents) {
    const lineage = doc.lineage_id || doc.id;
    const held = documentOfLineage.get(lineage);
    if (!held || doc.id === lineage || (held.id !== lineage && (doc.version ?? 1) < (held.version ?? 1))) {
      documentOfLineage.set(lineage, doc);
    }
  }
  for (const source of sources) {
    if (source.source_system !== STAGED_BY_EXTRACTION || !source.external_id) continue;
    const doc = documentOfLineage.get(source.external_id);
    if (!doc) continue;
    // A file records the lineage it was staged from, never the version that was
    // current at the time. Where the chain has only one document those are the
    // same thing and the edge says so; where it has several, saying "staged
    // from" of one version would claim a fact the server never recorded.
    const chain = (byLineage.get(source.external_id) ?? []).length;
    edges.push({
      from: documentNodeId(doc.id),
      to: sourceNodeId(source.id),
      kind: "derived",
      label: chain > 1 ? "staged from this chain" : "staged from",
    });
  }

  // 3. Consecutive versions of the same staged evidence. Only files that share a
  //    non-empty external id and a role are versions of each other; two files
  //    that merely share a role are separate uploads.
  const revisions = new Map<string, CoverageSource[]>();
  for (const source of sources) {
    if (!source.external_id) continue;
    const key = `${source.external_id}\u0000${source.role}`;
    revisions.set(key, [...(revisions.get(key) ?? []), source]);
  }
  for (const chain of revisions.values()) {
    const ordered = [...chain].sort((a, b) => (a.source_version ?? 1) - (b.source_version ?? 1));
    for (let i = 1; i < ordered.length; i++) {
      if ((ordered[i].source_version ?? 1) === (ordered[i - 1].source_version ?? 1)) continue;
      edges.push({
        from: sourceNodeId(ordered[i - 1].id),
        to: sourceNodeId(ordered[i].id),
        kind: "revision",
        label: `revised to v${ordered[i].source_version ?? 1}`,
      });
    }
  }

  return { nodes, edges: edges.filter((e) => present.has(e.from) && present.has(e.to)) };
}

/**
 * The groups of files that are joined to each other, largest first, and then
 * everything joined to nothing.
 *
 * A file on its own is not a failure and is not hidden — most uploads start that
 * way, and the screen says so rather than leaving a gap.
 */
export function connectedGroups(library: FileLibrary): FileNode[][] {
  const parent = new Map<string, string>();
  const find = (id: string): string => {
    const seen = parent.get(id);
    if (seen === undefined || seen === id) return id;
    const root = find(seen);
    parent.set(id, root);
    return root;
  };
  for (const node of library.nodes) parent.set(node.id, node.id);
  for (const edge of library.edges) {
    const a = find(edge.from);
    const b = find(edge.to);
    if (a !== b) parent.set(a, b);
  }
  const groups = new Map<string, FileNode[]>();
  for (const node of library.nodes) {
    const root = find(node.id);
    groups.set(root, [...(groups.get(root) ?? []), node]);
  }
  return [...groups.values()].sort((a, b) => b.length - a.length);
}

/**
 * Left-to-right depth for one group: a file with nothing feeding it starts at 0,
 * and every file sits one step right of the furthest thing that feeds it. With
 * only revision and derivation edges the graph has no cycles, but the visited
 * set keeps a malformed one from hanging the screen.
 */
export function depths(group: FileNode[], edges: FileEdge[]): Map<string, number> {
  const ids = new Set(group.map((n) => n.id));
  const incoming = new Map<string, string[]>();
  for (const edge of edges) {
    if (!ids.has(edge.from) || !ids.has(edge.to)) continue;
    incoming.set(edge.to, [...(incoming.get(edge.to) ?? []), edge.from]);
  }
  const depth = new Map<string, number>();
  const of = (id: string, visiting: Set<string>): number => {
    const known = depth.get(id);
    if (known !== undefined) return known;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const feeders = incoming.get(id) ?? [];
    const value = feeders.length === 0 ? 0 : Math.max(...feeders.map((f) => of(f, visiting) + 1));
    visiting.delete(id);
    depth.set(id, value);
    return value;
  };
  for (const node of group) of(node.id, new Set());
  return depth;
}
