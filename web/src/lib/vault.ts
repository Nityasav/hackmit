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

/**
 * The ecosystem's own shape, mirroring `api/app/agents/registry.py`: four
 * domains, each with its numbered subagents.
 *
 * Only ids, names and colours live here. Which records a subagent reads is
 * never restated — it is read from `coverage.requirements`, where the server
 * publishes `needed_by` for every input. Change registry.py and change this
 * list with it; nothing else here moves.
 */
export type VaultCategory = "A" | "B" | "C" | "D";

/** `colour` draws borders, folders and edges; `ink` writes the small text. The
 *  600-weight hue is about 3.6:1 on white, which fails WCAG AA at 9–10px, so
 *  text takes the 800 weight of the same hue. */
export const CATEGORY: Record<VaultCategory, { code: string; label: string; colour: string; ink: string }> = {
  A: { code: "A", label: "Treasury & operational cash", colour: "#d97706", ink: "#92400e" },
  B: { code: "B", label: "Core accounting (controllership)", colour: "#ea580c", ink: "#9a3412" },
  C: { code: "C", label: "Financial planning & analysis", colour: "#059669", ink: "#065f46" },
  D: { code: "D", label: "Audit, controls & compliance", colour: "#7c3aed", ink: "#5b21b6" },
};

export const CATEGORY_ORDER: VaultCategory[] = ["A", "B", "C", "D"];

export interface Subsystem {
  id: string;
  code: string;
  label: string;
  category: VaultCategory;
}

/** The subagents, in registry order. Order decides which one owns a record
 *  that several of them read. */
export const SUBSYSTEMS: Subsystem[] = [
  { id: "A1", code: "A.1", label: "Accounts payable", category: "A" },
  { id: "A2", code: "A.2", label: "Accounts receivable", category: "A" },
  { id: "A3", code: "A.3", label: "Bank reconciliation", category: "A" },
  { id: "A4", code: "A.4", label: "Cash management", category: "A" },
  { id: "B1", code: "B.1", label: "Month-end close", category: "B" },
  { id: "B2", code: "B.2", label: "Accruals & adjustments", category: "B" },
  { id: "B3", code: "B.3", label: "Financial reporting", category: "B" },
  { id: "B4", code: "B.4", label: "Close review", category: "B" },
  { id: "C1", code: "C.1", label: "Budgeting", category: "C" },
  { id: "C2", code: "C.2", label: "Forecasting", category: "C" },
  { id: "C3", code: "C.3", label: "Variance analysis", category: "C" },
  { id: "C4", code: "C.4", label: "Strategic planning", category: "C" },
  { id: "C5", code: "C.5", label: "Board reporting", category: "C" },
  { id: "D1", code: "D.1", label: "Audit", category: "D" },
  { id: "D2", code: "D.2", label: "Controls testing", category: "D" },
  { id: "D3", code: "D.3", label: "Audit evidence", category: "D" },
  { id: "D4", code: "D.4", label: "Reporting & filing", category: "D" },
];

const BY_ID = new Map(SUBSYSTEMS.map((s) => [s.id, s]));
const ORDER = new Map(SUBSYSTEMS.map((s, i) => [s.id, i]));

export function subsystemOf(id: string): Subsystem {
  return BY_ID.get(id) ?? SUBSYSTEMS[0];
}

/**
 * Which subagent owns a record: the earliest one the server says needs it.
 *
 * A record several subagents read is drawn once, beside the one whose job it
 * most belongs to; the others reach it with a line. Drawing it in every card
 * that reads it would multiply the same file across the map.
 */
function owner(neededBy: string[]): Subsystem {
  const subagents = neededBy.filter((id) => BY_ID.has(id));
  if (subagents.length === 0) return SUBSYSTEMS[0];
  return subsystemOf(subagents.reduce((best, id) => ((ORDER.get(id) ?? 99) < (ORDER.get(best) ?? 99) ? id : best)));
}

export interface VaultNode {
  id: string;
  kind: VaultKind;
  label: string;
  /** Plain-language line for the detail panel. */
  detail: string;
  /** Larger for things more of the review leans on. */
  weight: number;
  /** Id of the subagent that owns it; the category follows from that. */
  subsystem: string;
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
 * Builds the graph from what the server publishes: the requirement registry,
 * the committed sources and the findings a scan raised.
 *
 * Nothing is inferred. A subagent is joined to a record because
 * `requirements[].needed_by` names it, a gap is drawn because the server said
 * the requirement is unsatisfied, and a finding is joined to a record because
 * it cited that record by id.
 */
export function buildVault(coverage: Coverage | null, findings: ReviewFinding[]): VaultGraph {
  if (!coverage) return { nodes: [], links: [] };

  const nodes: VaultNode[] = [];
  const links: VaultLink[] = [];
  const byRole = new Map<string, string[]>();
  const ownerOfRole = new Map<string, Subsystem>();
  for (const requirement of coverage.requirements) {
    if (requirement.role) ownerOfRole.set(requirement.role, owner(requirement.needed_by));
  }

  for (const source of coverage.sources.filter((s) => s.active)) {
    const id = `file:${source.id}`;
    const requirement = coverage.requirements.find((r) => r.role === source.role);
    nodes.push({
      id,
      kind: "file",
      label: source.name,
      detail: requirement?.unlocks ?? `Supplied as ${ROLE_LABEL[source.role] ?? source.role}.`,
      weight: 1,
      subsystem: (ownerOfRole.get(source.role) ?? SUBSYSTEMS[0]).id,
      role: source.role,
      sourceId: source.id,
    });
    byRole.set(source.role, [...(byRole.get(source.role) ?? []), id]);
  }

  // One node per subagent that reads something here, joined to every record it
  // reads and every input it is still waiting for.
  const agents = new Map<string, { needs: string[]; missing: string[] }>();
  for (const requirement of coverage.requirements) {
    if (requirement.kind === "setting" || !requirement.role) continue;
    for (const id of requirement.needed_by) {
      if (!BY_ID.has(id)) continue;
      const entry = agents.get(id) ?? { needs: [], missing: [] };
      (requirement.satisfied ? entry.needs : entry.missing).push(requirement.role);
      agents.set(id, entry);
    }
  }

  for (const [id, { needs, missing }] of agents) {
    const subsystem = subsystemOf(id);
    const agentId = `check:${id}`;
    const blocked = coverage.blocked_agents?.[id] ?? [];
    nodes.push({
      id: agentId,
      kind: "check",
      label: subsystem.label,
      detail: blocked.length
        ? `Waiting on ${blocked.length} ${blocked.length === 1 ? "input" : "inputs"}: ${blocked.join(", ")}.`
        : "Every input this agent requires has been supplied.",
      weight: 1,
      subsystem: subsystem.id,
      status: blocked.length ? "blocked" : "ready",
    });

    for (const role of new Set(needs)) {
      for (const file of byRole.get(role) ?? []) links.push({ source: agentId, target: file, relation: "requires" });
    }
    for (const role of new Set(missing)) {
      const gap = `missing:${role}`;
      if (!nodes.some((n) => n.id === gap)) {
        const requirement = coverage.requirements.find((r) => r.role === role);
        nodes.push({
          id: gap,
          kind: "missing",
          label: requirement?.label ?? ROLE_LABEL[role] ?? role,
          detail: `${requirement?.unlocks ?? "Required by an agent."} Nothing has been uploaded for it.`,
          weight: 1,
          subsystem: (ownerOfRole.get(role) ?? subsystem).id,
          role,
        });
      }
      links.push({ source: agentId, target: gap, relation: "absent" });
    }
  }

  const fileBySourceId = new Map(
    nodes.filter((n) => n.kind === "file").map((n) => [n.sourceId as string, n.id]),
  );

  for (const finding of findings.filter((f) => !f.stale)) {
    const cited = [...new Set((finding.evidence ?? []).map((e) => e.source_id).filter(Boolean))];
    const reachable = cited.map((s) => fileBySourceId.get(s as string)).filter(Boolean) as string[];
    if (reachable.length === 0) continue;

    // A finding sits with the records it read, so it never floats away from
    // its own evidence.
    const home = nodes.find((n) => n.id === reachable[0])?.subsystem ?? SUBSYSTEMS[0].id;
    nodes.push({
      id: `finding:${finding.id}`,
      kind: "finding",
      label: finding.title,
      detail: `Raised by a check, citing ${reachable.length} ${reachable.length === 1 ? "file" : "files"}.`,
      weight: 1,
      subsystem: home,
      status: finding.status,
    });
    for (const file of reachable) links.push({ source: `finding:${finding.id}`, target: file, relation: "cites" });
  }

  // An agent with nothing to point at has no dependency to draw.
  const attached = new Set(links.flatMap((l) => [l.source, l.target]));
  const kept = nodes.filter((n) => n.kind !== "check" || attached.has(n.id));

  const degree = new Map<string, number>();
  for (const link of links) {
    degree.set(link.source, (degree.get(link.source) ?? 0) + 1);
    degree.set(link.target, (degree.get(link.target) ?? 0) + 1);
  }
  for (const node of kept) node.weight = degree.get(node.id) ?? 0;

  return { nodes: kept, links };
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


/** Any edge that leaves its category — real, and drawn dashed to say so. */
export function crossCategoryLinks(graph: VaultGraph): VaultLink[] {
  const category = new Map(graph.nodes.map((n) => [n.id, subsystemOf(n.subsystem).category]));
  return graph.links.filter((l) => category.get(l.source) !== category.get(l.target));
}

/* ── Layout ──────────────────────────────────────────────────────────────
 *
 * Positions for a React Flow canvas: category cards, the subsystem cards
 * inside them, and the records inside those. Pure and deterministic, so the
 * same records always draw the same picture and the layout can be checked
 * without a browser.
 *
 * Every card is sized to its own contents and then flowed with wrapping, which
 * is the fix for the empty bands: a category holding one subsystem is as wide
 * as that subsystem and sits beside its neighbour instead of reserving a
 * full-width row and leaving the rest blank.
 */

export type Side = "t" | "b" | "l" | "r";

export interface FlowBox {
  id: string;
  parentId?: string;
  kind: "category" | "subsystem";
  code: string;
  label: string;
  colour: string;
  ink: string;
  /** Relative to the parent, as React Flow wants it. */
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FlowNode extends VaultNode {
  parentId: string;
  colour: string;
  ink: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  sourceSide: Side;
  targetSide: Side;
  relation: VaultLink["relation"];
  colour: string;
  inside: boolean;
  cross: boolean;
}

export interface EcosystemLayout {
  boxes: FlowBox[];
  nodes: FlowNode[];
  edges: FlowEdge[];
  width: number;
  height: number;
}

const FILE_W = 74;
// Folder, gap, and two lines of caption. Too short and the second line of a
// name like opening-trial-balance.csv is clipped.
const FILE_H = 66;
const CHIP_H = 24;
const CHIP_MIN = 104;
const CHIP_MAX = 224;
const GAP = 8;
const BOX_PAD = 10;
// Two lines: a title like A.4 BANK RECONCILIATION wraps in a narrow card,
// and a one-line reservation puts it on top of the first folder.
const BOX_HEAD = 32;
const CAT_PAD = 12;
const CAT_HEAD = 30;
const CAT_GAP = 14;

/** Two columns of pills once a list gets long, so a box grows wide, not tall. */
function chipColumns(count: number): number {
  return count > 5 ? 2 : 1;
}

interface BoxPlan {
  subsystem: Subsystem;
  files: VaultNode[];
  chips: VaultNode[];
  columns: number;
  chipWidth: number;
  width: number;
  height: number;
}

function planBox(subsystem: Subsystem, members: VaultNode[], budget: number): BoxPlan | null {
  const files = members.filter((n) => n.kind === "file" || n.kind === "missing");
  const chips = members.filter((n) => n.kind === "check" || n.kind === "finding");
  if (files.length + chips.length === 0) return null;

  const columns = chipColumns(chips.length);
  const fileRowWidth = files.length * FILE_W;
  const chipRowWidth = columns * CHIP_MIN + (columns - 1) * GAP;
  const inner = Math.min(budget - 2 * BOX_PAD, Math.max(CHIP_MIN, fileRowWidth, chipRowWidth));
  const chipWidth = Math.min(CHIP_MAX, (inner - (columns - 1) * GAP) / columns);
  const rows = Math.ceil(chips.length / columns);

  return {
    subsystem,
    files,
    chips,
    columns,
    chipWidth,
    width: inner + 2 * BOX_PAD,
    height:
      BOX_HEAD +
      (files.length ? FILE_H + (rows ? GAP : 0) : 0) +
      rows * (CHIP_H + GAP) -
      (rows ? GAP : 0) +
      BOX_PAD,
  };
}

/** Greedy flow of sized items into rows no wider than the budget. */
function flow<T extends { width: number; height: number }>(items: T[], budget: number, gap: number): T[][] {
  const rows: T[][] = [];
  let row: T[] = [];
  let used = 0;
  for (const item of items) {
    if (row.length && used + gap + item.width > budget) {
      rows.push(row);
      row = [];
      used = 0;
    }
    row.push(item);
    used += (row.length > 1 ? gap : 0) + item.width;
  }
  if (row.length) rows.push(row);
  return rows;
}

export function layoutEcosystem(graph: VaultGraph, canvas: number): EcosystemLayout {
  const width = Math.max(560, canvas);
  const boxes: FlowBox[] = [];
  const nodes: FlowNode[] = [];
  const placed = new Map<string, FlowNode>();
  // A category may use the full canvas, but a subsystem is capped so one long
  // list cannot stretch a card across the whole screen.
  const boxBudget = Math.min(520, width - 2 * CAT_PAD);

  interface CategoryPlan { category: VaultCategory; plans: BoxPlan[]; rows: BoxPlan[][]; width: number; height: number }
  const categories: CategoryPlan[] = [];

  for (const category of CATEGORY_ORDER) {
    const plans = SUBSYSTEMS.filter((sub) => sub.category === category)
      .map((sub) => planBox(sub, graph.nodes.filter((n) => n.subsystem === sub.id), boxBudget))
      .filter((p): p is BoxPlan => p !== null);
    if (plans.length === 0) continue;

    const rows = flow(plans, width - 2 * CAT_PAD, GAP);
    // Bold 9px uppercase with letter-spacing: measured, not guessed low, or the
    // title wraps and the second line lands under the first subsystem card.
    const title = `${CATEGORY[category].code} · ${CATEGORY[category].label}`.length * 6.6 + 16;
    const inner = Math.max(title, ...rows.map((row) => row.reduce((n, p) => n + p.width, 0) + GAP * (row.length - 1)));
    for (const row of rows) {
      if (row.length === 1 && row[0].width < inner) {
        const only = row[0];
        only.chipWidth = Math.min(CHIP_MAX, (inner - 2 * BOX_PAD - (only.columns - 1) * GAP) / only.columns);
        only.width = inner;
      }
    }
    const height = CAT_HEAD + rows.reduce((n, row) => n + Math.max(...row.map((p) => p.height)) + GAP, 0) - GAP + CAT_PAD;
    categories.push({ category, plans, rows, width: inner + 2 * CAT_PAD, height });
  }

  // Category cards wrap like cards in a grid: a narrow one sits beside its
  // neighbour rather than owning a row.
  let y = 0;
  for (const line of flow(categories, width, CAT_GAP)) {
    let x = 0;
    const lineHeight = Math.max(...line.map((c) => c.height));
    for (const plan of line) {
      const colour = CATEGORY[plan.category].colour;
      const ink = CATEGORY[plan.category].ink;
      boxes.push({
        id: plan.category, kind: "category", code: CATEGORY[plan.category].code,
        label: CATEGORY[plan.category].label, colour, ink, x, y, width: plan.width, height: plan.height,
      });

      let boxY = CAT_HEAD;
      for (const row of plan.rows) {
        const rowHeight = Math.max(...row.map((p) => p.height));
        let boxX = CAT_PAD;
        for (const p of row) {
          boxes.push({
            id: p.subsystem.id, parentId: plan.category, kind: "subsystem", code: p.subsystem.code,
            label: p.subsystem.label, colour, ink, x: boxX, y: boxY, width: p.width, height: p.height,
          });

          const inner = p.width - 2 * BOX_PAD;
          let cursor = BOX_HEAD;
          if (p.files.length) {
            const slot = inner / p.files.length;
            p.files.forEach((node, index) => {
              const node_ = { ...node, parentId: p.subsystem.id, colour, ink, x: BOX_PAD + slot * index + (slot - FILE_W) / 2, y: cursor, width: Math.min(FILE_W, slot), height: FILE_H };
              placed.set(node.id, node_);
              nodes.push(node_);
            });
            cursor += FILE_H + GAP;
          }
          p.chips.forEach((node, index) => {
            const column = index % p.columns;
            const row_ = Math.floor(index / p.columns);
            const node_ = {
              ...node, parentId: p.subsystem.id, colour, ink,
              x: BOX_PAD + column * (p.chipWidth + GAP),
              y: cursor + row_ * (CHIP_H + GAP),
              width: p.chipWidth, height: CHIP_H,
            };
            placed.set(node.id, node_);
            nodes.push(node_);
          });

          boxX += p.width + GAP;
        }
        boxY += rowHeight + GAP;
      }
      x += plan.width + CAT_GAP;
    }
    y += lineHeight + CAT_GAP;
  }

  // Absolute centres, only so the edges can pick which side to leave from.
  const origin = new Map<string, { x: number; y: number }>();
  for (const box of boxes) {
    const parent = box.parentId ? origin.get(box.parentId)! : { x: 0, y: 0 };
    origin.set(box.id, { x: parent.x + box.x, y: parent.y + box.y });
  }
  const centre = (node: FlowNode) => {
    const parent = origin.get(node.parentId)!;
    return { x: parent.x + node.x + node.width / 2, y: parent.y + node.y + node.height / 2 };
  };

  const edges: FlowEdge[] = [];
  graph.links.forEach((link, index) => {
    const source = placed.get(link.source);
    const target = placed.get(link.target);
    if (!source || !target) return;
    const a = centre(source);
    const b = centre(target);
    // Leave by whichever face actually points at the other node, so React Flow
    // never has to double back on itself to reach a handle.
    const horizontal = Math.abs(b.x - a.x) > Math.abs(b.y - a.y);
    const sourceSide: Side = horizontal ? (b.x > a.x ? "r" : "l") : b.y > a.y ? "b" : "t";
    const targetSide: Side = horizontal ? (b.x > a.x ? "l" : "r") : b.y > a.y ? "t" : "b";
    const from = subsystemOf(source.subsystem);
    const to = subsystemOf(target.subsystem);
    edges.push({
      id: `e${index}`, source: link.source, target: link.target, sourceSide, targetSide,
      relation: link.relation, colour: CATEGORY[from.category].colour,
      inside: from.id === to.id, cross: from.category !== to.category,
    });
  });

  return { boxes, nodes, edges, width, height: Math.max(0, y - CAT_GAP) };
}
