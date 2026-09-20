import type { Coverage, SourceRole } from "@/lib/types";

/**
 * The review as a graph of what depends on what.
 *
 * Every node and every edge here is read off the API. Nothing is inferred and
 * nothing is invented: a check is joined to a file because the server said that
 * check requires that file's role, and a finding is joined to a file because the
 * finding cited that file by id. If the data does not say two things are
 * related, they are not drawn as related.
 */

export type VaultKind = "file" | "check" | "finding" | "missing";

export interface VaultNode {
  id: string;
  kind: VaultKind;
  label: string;
  /** Plain-language line for the detail panel. */
  detail: string;
  /** Larger for things more of the review leans on. */
  weight: number;
  role?: SourceRole | string;
  status?: string;
  sourceId?: string;
}

export interface VaultLink {
  source: string;
  target: string;
  relation: "requires" | "cites" | "absent";
}

export interface VaultGraph {
  nodes: VaultNode[];
  links: VaultLink[];
}

export interface ReviewFinding {
  id: string;
  title: string;
  status: string;
  stale?: boolean;
  amount_cents?: number | null;
  evidence?: { source_id?: string; line?: number }[];
}

export const ROLE_LABEL: Record<string, string> = {
  chart: "Chart of accounts", opening: "Opening balances", ledger: "General ledger",
  payroll: "Payroll", grants: "Grant register", budget: "Budget", invoice: "Invoices",
  fees: "Student fees", collections: "Collections (money received)", deposits: "Bank deposits",
  sponsorships: "Sponsorships & pledges", service: "Service records",
  policy: "Award terms / policy", document: "Document",
};

/** What a role is for, in one sentence anyone can read. */
export const ROLE_PURPOSE: Record<string, string> = {
  chart: "Names every account, so a number can be placed in the right one.",
  opening: "What each account held before the period, so movement can be measured.",
  ledger: "Every transaction in the period. Most checks start here.",
  payroll: "What people were paid, and what the school paid on top.",
  grants: "Each award, its ceiling and the dates it may be spent between.",
  budget: "What spending was approved, to compare against what happened.",
  invoice: "Bills received, checked for duplicates and for missing support.",
  fees: "What families were charged.",
  collections: "Money actually received, matched against what was charged.",
  deposits: "What reached the bank, matched against what was collected.",
  sponsorships: "Pledges promised, and whether they arrived.",
  service: "Proof that work charged to an award was actually done.",
  policy: "The award's written terms. Rules are read from here, never assumed.",
  document: "A supporting document kept beside the records it explains.",
};

/**
 * Builds the graph. `findings` may be empty: before a scan there are no
 * finding nodes, and the graph shows only what the checks need.
 */
export function buildVault(coverage: Coverage | null, findings: ReviewFinding[]): VaultGraph {
  if (!coverage) return { nodes: [], links: [] };

  const nodes: VaultNode[] = [];
  const links: VaultLink[] = [];
  const byRole = new Map<string, string[]>();

  for (const source of coverage.sources.filter((s) => s.active)) {
    const id = `file:${source.id}`;
    nodes.push({
      id,
      kind: "file",
      label: source.name,
      detail: ROLE_PURPOSE[source.role] ?? `Supplied as ${ROLE_LABEL[source.role] ?? source.role}.`,
      weight: 1,
      role: source.role,
      sourceId: source.id,
    });
    byRole.set(source.role, [...(byRole.get(source.role) ?? []), id]);
  }

  for (const capability of coverage.capabilities) {
    if (capability.status === "unsupported") continue;
    const id = `check:${capability.id}`;
    nodes.push({
      id,
      kind: "check",
      label: capability.label,
      detail: capability.note,
      weight: 1,
      status: capability.status,
    });

    const required = (capability as { requires?: string[] }).requires ?? [];
    for (const role of required) {
      const files = byRole.get(role);
      if (files?.length) {
        for (const file of files) links.push({ source: id, target: file, relation: "requires" });
        continue;
      }
      // Required, and nothing supplied for it. This is the answer to "which
      // files are necessary" — drawn so an absence is as visible as a presence.
      const gap = `missing:${role}`;
      if (!nodes.some((n) => n.id === gap)) {
        nodes.push({
          id: gap,
          kind: "missing",
          label: ROLE_LABEL[role] ?? role,
          detail: `${ROLE_PURPOSE[role] ?? "Required by a check."} Nothing has been uploaded for it.`,
          weight: 1,
          role,
        });
      }
      links.push({ source: id, target: gap, relation: "absent" });
    }
  }

  const fileBySourceId = new Map(
    nodes.filter((n) => n.kind === "file").map((n) => [n.sourceId as string, n.id]),
  );

  for (const finding of findings.filter((f) => !f.stale)) {
    const cited = [...new Set((finding.evidence ?? []).map((e) => e.source_id).filter(Boolean))];
    const reachable = cited.map((s) => fileBySourceId.get(s as string)).filter(Boolean) as string[];
    if (reachable.length === 0) continue;

    const id = `finding:${finding.id}`;
    nodes.push({
      id,
      kind: "finding",
      label: finding.title,
      detail: `Raised by a check, citing ${reachable.length} ${reachable.length === 1 ? "file" : "files"}.`,
      weight: 1,
      status: finding.status,
    });
    for (const file of reachable) links.push({ source: id, target: file, relation: "cites" });
  }

  // Weight is how much of the review leans on a node, counted from the links.
  const degree = new Map<string, number>();
  for (const link of links) {
    degree.set(link.source, (degree.get(link.source) ?? 0) + 1);
    degree.set(link.target, (degree.get(link.target) ?? 0) + 1);
  }
  for (const node of nodes) node.weight = degree.get(node.id) ?? 0;

  return { nodes, links };
}

/** Everything the graph knows about one node, for the detail panel. */
export function describeNode(graph: VaultGraph, id: string) {
  const node = graph.nodes.find((n) => n.id === id);
  if (!node) return null;
  const edges = graph.links.filter((l) => l.source === id || l.target === id);
  const other = (l: VaultLink) => (l.source === id ? l.target : l.source);
  const lookup = (nid: string) => graph.nodes.find((n) => n.id === nid);

  return {
    node,
    requiredBy: edges.filter((l) => l.relation === "requires" && l.target === id).map((l) => lookup(l.source)!),
    requires: edges.filter((l) => l.relation !== "cites" && l.source === id).map((l) => lookup(other(l))!),
    citedBy: edges.filter((l) => l.relation === "cites" && l.target === id).map((l) => lookup(l.source)!),
    cites: edges.filter((l) => l.relation === "cites" && l.source === id).map((l) => lookup(other(l))!),
  };
}
