"use client";

import { useMemo } from "react";

import { connectedGroups, depths, type FileEdge, type FileLibrary, type FileNode } from "@/lib/fileLibrary";

const BOX_W = 168;
const BOX_H = 44;
const COL_GAP = 76;
const ROW_GAP = 14;

interface Placed {
  node: FileNode;
  x: number;
  y: number;
}

/** One group laid out left to right by depth, each column stacked in order. */
function place(group: FileNode[], edges: FileEdge[]): { placed: Placed[]; width: number; height: number } {
  const depth = depths(group, edges);
  const columns = new Map<number, FileNode[]>();
  // Sorted so the layout is the same on every render for the same data: a graph
  // that reshuffles itself looks like the data changed when it did not.
  const ordered = [...group].sort((a, b) => (depth.get(a.id) ?? 0) - (depth.get(b.id) ?? 0) || a.name.localeCompare(b.name));
  for (const node of ordered) {
    const d = depth.get(node.id) ?? 0;
    columns.set(d, [...(columns.get(d) ?? []), node]);
  }
  const placed: Placed[] = [];
  let rows = 0;
  for (const [d, column] of columns) {
    rows = Math.max(rows, column.length);
    column.forEach((node, i) => {
      placed.push({ node, x: d * (BOX_W + COL_GAP), y: i * (BOX_H + ROW_GAP) });
    });
  }
  const maxDepth = Math.max(...[...columns.keys()]);
  return {
    placed,
    width: maxDepth * (BOX_W + COL_GAP) + BOX_W,
    height: Math.max(1, rows) * (BOX_H + ROW_GAP) - ROW_GAP,
  };
}

function Group({ group, edges, selected, onSelect }: {
  group: FileNode[];
  edges: FileEdge[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const { placed, width, height } = useMemo(() => place(group, edges), [group, edges]);
  const at = new Map(placed.map((p) => [p.node.id, p]));
  const inside = edges.filter((e) => at.has(e.from) && at.has(e.to));

  return (
    <svg
      role="img"
      aria-label={`${group.length} connected files`}
      viewBox={`-8 -8 ${width + 16} ${height + 16}`}
      width={width + 16}
      height={height + 16}
      className="max-w-full"
    >
      <defs>
        <marker id="file-graph-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0 L8 4 L0 8 z" className="fill-ink-faint" />
        </marker>
      </defs>
      {inside.map((edge) => {
        const from = at.get(edge.from)!;
        const to = at.get(edge.to)!;
        const x1 = from.x + BOX_W;
        const y1 = from.y + BOX_H / 2;
        const x2 = to.x;
        const y2 = to.y + BOX_H / 2;
        const bend = Math.max(24, (x2 - x1) / 2);
        return (
          <g key={`${edge.from}->${edge.to}`}>
            <path
              d={`M${x1} ${y1} C${x1 + bend} ${y1} ${x2 - bend} ${y2} ${x2} ${y2}`}
              fill="none"
              strokeWidth={1.25}
              // A derivation is a solid line because it is how a record traces to a
              // page; a revision is dashed because it replaces rather than feeds.
              strokeDasharray={edge.kind === "revision" ? "4 3" : undefined}
              className="stroke-ink-faint"
              markerEnd="url(#file-graph-arrow)"
            />
            <text
              x={(x1 + x2) / 2}
              y={(y1 + y2) / 2 - 5}
              textAnchor="middle"
              className="fill-ink-dim text-[9px]"
            >
              {edge.label}
            </text>
          </g>
        );
      })}
      {placed.map(({ node, x, y }) => {
        const isSelected = node.id === selected;
        return (
          <g
            key={node.id}
            transform={`translate(${x} ${y})`}
            onClick={() => onSelect(node.id)}
            className="cursor-pointer"
          >
            <title>{`${node.name} · ${node.kind === "document" ? "uploaded document" : "committed file"}`}</title>
            <rect
              width={BOX_W}
              height={BOX_H}
              rx={6}
              className={isSelected ? "fill-surface-2 stroke-ink" : "fill-surface stroke-line"}
              strokeWidth={isSelected ? 1.5 : 1}
            />
            <text x={10} y={18} className="fill-ink text-[11px] font-medium">
              {node.name.length > 24 ? `${node.name.slice(0, 23)}…` : node.name}
            </text>
            <text x={10} y={32} className="fill-ink-dim text-[9.5px]">
              {node.format.toUpperCase()} · {node.kind === "document" ? "document" : "records"} · v{node.version}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/**
 * How the files hold each other up.
 *
 * Only groups of two or more are drawn, because a single box joined to nothing
 * is a picture of nothing. The count of unconnected files is stated in words
 * instead — most uploads are unconnected until they are reviewed and staged,
 * and that is worth saying plainly rather than implying with an empty canvas.
 */
export function FileGraph({ library, selected, onSelect }: {
  library: FileLibrary;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const groups = useMemo(() => connectedGroups(library), [library]);
  const connected = groups.filter((g) => g.length > 1);
  const alone = groups.length - connected.length;

  if (connected.length === 0) {
    return (
      <p className="text-[13px] text-ink-dim">
        {library.nodes.length === 0
          ? "No files yet, so nothing to connect."
          : `None of these ${library.nodes.length} files is joined to another yet. A document joins to a file once you review its values and stage them.`}
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <div className="space-y-6 overflow-x-auto">
        {connected.map((group) => (
          <Group
            key={group.map((n) => n.id).sort().join("|")}
            group={group}
            edges={library.edges}
            selected={selected}
            onSelect={onSelect}
          />
        ))}
      </div>
      <p className="text-[12px] text-ink-dim">
        Solid: the file was staged from that document. Dashed: the newer one replaced the older.
        {alone > 0 && ` ${alone} file${alone === 1 ? " is" : "s are"} not joined to anything yet.`}
      </p>
    </div>
  );
}
