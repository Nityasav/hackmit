"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import {
  layoutEcosystem,
  type FlowBox,
  type FlowNode,
  type Side,
  type VaultGraph as Graph,
  type VaultKind,
} from "@/lib/vault";

export const KIND_LABEL: Record<VaultKind, string> = {
  file: "File you uploaded",
  check: "Check that reads it",
  finding: "What a check raised",
  missing: "Required, not supplied",
};

const MISSING = "#dc2626";
const SIDE: Record<Side, Position> = { t: Position.Top, b: Position.Bottom, l: Position.Left, r: Position.Right };

/** Every node carries handles on all four faces; the layout picks the pair. */
function Faces({ colour }: { colour: string }) {
  const style = { opacity: 0, width: 1, height: 1, minWidth: 1, minHeight: 1, border: "none", background: colour };
  return (
    <>
      {(["t", "b", "l", "r"] as Side[]).map((side) => (
        <span key={side}>
          <Handle type="source" id={side} position={SIDE[side]} style={style} isConnectable={false} />
          <Handle type="target" id={side} position={SIDE[side]} style={style} isConnectable={false} />
        </span>
      ))}
    </>
  );
}

type Data = FlowNode & { dimmed: boolean; active: boolean } & Record<string, unknown>;

/** A file, as a folder over its name. */
function FileCard({ data }: NodeProps<Node<Data>>) {
  const gone = data.kind === "missing";
  const colour = gone ? MISSING : data.colour;
  return (
    <div
      className="flex h-full w-full cursor-pointer flex-col items-center justify-start gap-1 transition-opacity duration-150"
      style={{ opacity: data.dimmed ? 0.25 : 1 }}
      title={`${data.label} — ${KIND_LABEL[data.kind]}`}
    >
      <Faces colour={colour} />
      <svg width={38} height={28} viewBox="0 0 38 28" aria-hidden>
        <path
          d="M1 5a3 3 0 0 1 3-3h9l3 4h18a3 3 0 0 1 3 3v16a3 3 0 0 1-3 3H4a3 3 0 0 1-3-3z"
          fill={gone ? "#fff" : colour}
          fillOpacity={gone ? 1 : 0.12}
          stroke={colour}
          strokeWidth={data.active ? 1.8 : 1.2}
          strokeDasharray={gone ? "3.5 2.5" : undefined}
        />
        {gone ? (
          <path d="M14 11l10 9M24 11l-10 9" stroke={MISSING} strokeWidth={1.6} strokeLinecap="round" />
        ) : (
          <g stroke={colour} strokeOpacity={0.55} strokeWidth={1.1} strokeLinecap="round">
            <path d="M9 14h20" />
            <path d="M9 19h13" />
          </g>
        )}
      </svg>
      <span
        className="line-clamp-2 px-0.5 text-center text-[9px] leading-[1.15] tracking-tight"
        style={{ color: data.active ? "#18181b" : "#52525b", fontWeight: data.active ? 600 : 400 }}
      >
        {data.label}
      </span>
    </div>
  );
}

/** A check or a finding, as a pill. */
function ChipCard({ data }: NodeProps<Node<Data>>) {
  const finding = data.kind === "finding";
  return (
    <div
      className="flex h-full w-full cursor-pointer items-center rounded-md border px-2 transition-[background-color,box-shadow,opacity] duration-150"
      style={{
        opacity: data.dimmed ? 0.25 : 1,
        borderColor: data.colour,
        borderStyle: finding ? "solid" : "solid",
        borderRadius: finding ? 6 : 999,
        borderWidth: data.active ? 1.6 : 1,
        background: finding ? "#fff" : `color-mix(in srgb, ${data.colour} 10%, #fff)`,
        boxShadow: data.active ? `0 0 0 3px color-mix(in srgb, ${data.colour} 18%, transparent)` : "none",
      }}
      title={`${data.label} — ${KIND_LABEL[data.kind]}`}
    >
      <Faces colour={data.colour} />
      <span className="truncate text-[10px] font-medium leading-none" style={{ color: data.ink }}>
        {data.label}
      </span>
    </div>
  );
}

/** A category card, or a subsystem card inside one. */
type ShellData = FlowBox & { dimmed: boolean } & Record<string, unknown>;

function Shell({ data }: NodeProps<Node<ShellData>>) {
  const category = data.kind === "category";
  return (
    <div
      className="h-full w-full rounded-lg border transition-opacity duration-150"
      style={{
        opacity: data.dimmed ? 0.55 : 1,
        borderColor: `color-mix(in srgb, ${data.colour} ${category ? 30 : 42}%, transparent)`,
        background: category ? `color-mix(in srgb, ${data.colour} 4%, #fff)` : "#fff",
        boxShadow: category ? "none" : "0 1px 2px rgb(16 24 40 / 0.04)",
      }}
    >
      <p
        className="line-clamp-2 px-3 pt-2 text-[9px] font-bold uppercase leading-[1.25] tracking-[0.09em]"
        style={{ color: data.ink }}
      >
        {category ? `${data.code} · ${data.label}` : `${data.code}  ${data.label}`}
      </p>
    </div>
  );
}

const NODE_TYPES = { file: FileCard, chip: ChipCard, shell: Shell };

/**
 * The ecosystem map.
 *
 * Categories hold their numbered subsystems, and a subsystem holds the records
 * it owns. Every card is sized to its contents and the cards wrap, so a
 * category with one subsystem sits next to its neighbour instead of leaving a
 * band of empty page. Edges are React Flow's rounded step edges between real
 * handles, which is what makes a line arrive at a card instead of stopping
 * near it.
 */
export function VaultGraph({
  graph,
  selected,
  onSelect,
}: {
  graph: Graph;
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const [width, setWidth] = useState(1040);

  useEffect(() => {
    const measure = () => setWidth(Math.min(1400, Math.max(560, window.innerWidth - 220)));
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  const layout = useMemo(() => layoutEcosystem(graph, width), [graph, width]);

  const neighbours = useMemo(() => {
    if (!selected) return null;
    const set = new Set<string>([selected]);
    for (const l of graph.links) {
      if (l.source === selected) set.add(l.target);
      if (l.target === selected) set.add(l.source);
    }
    return set;
  }, [graph, selected]);

  const nodes = useMemo<Node[]>(() => {
    const dimmed = (id: string) => Boolean(neighbours && !neighbours.has(id));
    const shells: Node[] = layout.boxes.map((box) => ({
      id: `box:${box.id}`,
      type: "shell",
      position: { x: box.x, y: box.y },
      parentId: box.parentId ? `box:${box.parentId}` : undefined,
      extent: box.parentId ? ("parent" as const) : undefined,
      draggable: false,
      selectable: false,
      data: { ...box, dimmed: Boolean(neighbours) },
      style: { width: box.width, height: box.height, pointerEvents: "none" as const },
      zIndex: box.kind === "category" ? 0 : 1,
    }));
    const leaves: Node[] = layout.nodes.map((node) => ({
      id: node.id,
      type: node.kind === "file" || node.kind === "missing" ? "file" : "chip",
      position: { x: node.x, y: node.y },
      parentId: `box:${node.parentId}`,
      extent: "parent" as const,
      draggable: false,
      data: { ...node, dimmed: dimmed(node.id), active: node.id === selected },
      style: { width: node.width, height: node.height },
      zIndex: 2,
    }));
    return [...shells, ...leaves];
  }, [layout, neighbours, selected]);

  const edges = useMemo<Edge[]>(
    () =>
      layout.edges.map((edge) => {
        const lit = edge.source === selected || edge.target === selected;
        const faded = Boolean(neighbours) && !lit;
        const absent = edge.relation === "absent";
        const colour = absent ? MISSING : edge.colour;
        return {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          sourceHandle: edge.sourceSide,
          targetHandle: edge.targetSide,
          type: "smoothstep",
          pathOptions: { borderRadius: 10 },
          zIndex: lit ? 3 : 0,
          markerEnd: lit || absent ? { type: MarkerType.ArrowClosed, width: 12, height: 12, color: colour } : undefined,
          style: {
            stroke: colour,
            strokeWidth: lit ? 1.7 : 1.1,
            strokeOpacity: faded ? 0.08 : lit ? 1 : absent ? 0.8 : edge.inside ? 0.5 : edge.cross ? 0.28 : 0.4,
            strokeDasharray: edge.inside && !absent ? undefined : absent ? "5 4" : "4 4",
          },
        };
      }),
    [layout, neighbours, selected],
  );

  if (layout.nodes.length === 0) {
    return (
      <div className="rounded-lg border border-line bg-surface p-6 text-[14px] text-ink-dim">
        Nothing to map yet. Commit this school&rsquo;s records on Books and the files, the checks
        that read them and anything still missing appear here.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-line bg-surface" style={{ height: Math.min(720, layout.height + 90) }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodeClick={(_, node) => onSelect(node.id.startsWith("box:") ? null : node.id)}
        onPaneClick={() => onSelect(null)}
        nodesDraggable={false}
        nodesConnectable={false}
        edgesFocusable={false}
        elementsSelectable
        proOptions={{ hideAttribution: true }}
        minZoom={0.3}
        maxZoom={1.6}
        fitView
        fitViewOptions={{ padding: 0.06, maxZoom: 1 }}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#e7e7ea" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}
