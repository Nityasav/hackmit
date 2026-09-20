"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";

import type { VaultGraph as Graph, VaultKind } from "@/lib/vault";

// three.js needs a window, so the canvas is client-only.
const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), {
  ssr: false,
  loading: () => <p className="p-6 text-[14px] text-ink-dim">Loading the map…</p>,
});

/** Black for the records, grey for the machinery, red for what is missing. */
const COLOUR: Record<VaultKind, string> = {
  file: "#09090b",
  check: "#52525b",
  finding: "#b45309",
  missing: "#dc2626",
};

export const KIND_LABEL: Record<VaultKind, string> = {
  file: "File you uploaded",
  check: "Check that reads it",
  finding: "What a check raised",
  missing: "Required, not supplied",
};

export function VaultGraph({
  graph,
  selected,
  onSelect,
}: {
  graph: Graph;
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 520 });

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const measure = () => setSize({ width: el.clientWidth, height: Math.max(420, Math.round(window.innerHeight * 0.55)) });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // react-force-graph mutates the objects it is given, so it gets copies.
  const data = useMemo(
    () => ({
      nodes: graph.nodes.map((n) => ({ ...n })),
      links: graph.links.map((l) => ({ ...l })),
    }),
    [graph],
  );

  const neighbours = useMemo(() => {
    if (!selected) return null;
    const set = new Set<string>([selected]);
    for (const l of graph.links) {
      if (l.source === selected) set.add(l.target);
      if (l.target === selected) set.add(l.source);
    }
    return set;
  }, [graph, selected]);

  return (
    <div ref={wrap} className="border border-line bg-surface">
      {data.nodes.length === 0 ? (
        <p className="p-6 text-[14px] text-ink-dim">
          Nothing to map yet. Commit this school&rsquo;s records on Books and the files, the checks
          that read them and anything still missing appear here.
        </p>
      ) : (
        <ForceGraph3D
          width={size.width}
          height={size.height}
          graphData={data}
          backgroundColor="#ffffff"
          showNavInfo={false}
          nodeLabel={(n: object) => (n as { label: string }).label}
          nodeVal={(n: object) => 1 + (n as { weight: number }).weight}
          nodeColor={(n: object) => {
            const node = n as { id: string; kind: VaultKind };
            if (neighbours && !neighbours.has(node.id)) return "#d8d8dd";
            return COLOUR[node.kind];
          }}
          nodeOpacity={0.95}
          linkColor={(l: object) => {
            const link = l as { source: { id?: string } | string; target: { id?: string } | string; relation: string };
            const s = typeof link.source === "string" ? link.source : link.source.id;
            const t = typeof link.target === "string" ? link.target : link.target.id;
            if (neighbours && !(neighbours.has(s ?? "") && neighbours.has(t ?? ""))) return "#ececef";
            return link.relation === "absent" ? "#dc2626" : link.relation === "cites" ? "#b45309" : "#9b9ba3";
          }}
          linkWidth={(l: object) => ((l as { relation: string }).relation === "absent" ? 1.4 : 0.6)}
          linkDirectionalParticles={(l: object) => ((l as { relation: string }).relation === "absent" ? 0 : 2)}
          linkDirectionalParticleWidth={1.2}
          onNodeClick={(n: object) => onSelect((n as { id: string }).id)}
          onBackgroundClick={() => onSelect(null)}
          enableNodeDrag={false}
        />
      )}
    </div>
  );
}
