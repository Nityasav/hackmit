"use client";

import { useEffect, useState } from "react";

import type { Workflow } from "@/lib/types";

const VIEW_W = 1200;
const VIEW_H = 340;
const PAD_L = 40;
const PAD_R = 8;
const PAD_T = 16;
const PAD_B = 56;

const PLOT_W = VIEW_W - PAD_L - PAD_R;
const PLOT_H = VIEW_H - PAD_T - PAD_B;

/** "Month-end close · September" reads as "Month-end close" under a column. */
function shortName(name: string) {
  return name.split("·")[0].trim();
}

/**
 * The close, as columns. Each workflow is a category rather than a point in
 * time, so the bars stay separate instead of being joined into a line.
 */
export function CloseProgressChart({ workflows }: { workflows: Workflow[] }) {
  const [drawn, setDrawn] = useState(false);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const id = setTimeout(() => setDrawn(true), 60);
    return () => clearTimeout(id);
  }, []);

  if (workflows.length === 0) return null;

  const slot = PLOT_W / workflows.length;
  const barW = Math.min(72, slot * 0.46);

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        className="w-full"
        role="img"
        aria-label={`Progress through ${workflows.length} workflows this close`}
      >
        {/* Four gridlines and the axis, so a column can be read without a tooltip. */}
        {[0, 25, 50, 75, 100].map((tick) => {
          const y = PAD_T + PLOT_H - (tick / 100) * PLOT_H;
          return (
            <g key={tick}>
              <line
                x1={PAD_L}
                x2={VIEW_W - PAD_R}
                y1={y}
                y2={y}
                stroke="var(--color-line)"
                strokeWidth={tick === 0 ? 1.5 : 1}
              />
              <text
                x={PAD_L - 10}
                y={y + 4}
                textAnchor="end"
                className="fill-ink-faint font-num"
                fontSize="12"
              >
                {tick}
              </text>
            </g>
          );
        })}

        {workflows.map((w, i) => {
          const x = PAD_L + i * slot + (slot - barW) / 2;
          const full = (w.progress / 100) * PLOT_H;
          const h = drawn ? full : 0;
          const active = hover === i;

          return (
            <g
              key={w.id}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              className="cursor-default"
            >
              {/* Full-height target so the hover area is the whole column. */}
              <rect x={PAD_L + i * slot} y={PAD_T} width={slot} height={PLOT_H} fill="transparent" />

              {/* The remainder, so 0% still reads as a column rather than nothing. */}
              <rect
                x={x}
                y={PAD_T}
                width={barW}
                height={PLOT_H}
                fill="var(--color-surface-2)"
              />

              <rect
                x={x}
                y={PAD_T + PLOT_H - h}
                width={barW}
                height={h}
                fill={active ? "var(--color-ink-dim)" : "var(--color-ink)"}
                style={{ transition: "height 900ms cubic-bezier(0.22, 1, 0.36, 1), y 900ms cubic-bezier(0.22, 1, 0.36, 1), fill 150ms" }}
              />

              <text
                x={x + barW / 2}
                y={PAD_T + PLOT_H - h - 10}
                textAnchor="middle"
                className="fill-ink font-num"
                fontSize="15"
                fontWeight="600"
                style={{ transition: "y 900ms cubic-bezier(0.22, 1, 0.36, 1)", opacity: drawn ? 1 : 0 }}
              >
                {w.progress}%
              </text>

              <text
                x={PAD_L + i * slot + slot / 2}
                y={VIEW_H - PAD_B + 24}
                textAnchor="middle"
                className={active ? "fill-ink" : "fill-ink-dim"}
                fontSize="13"
              >
                {shortName(w.name)}
              </text>
            </g>
          );
        })}
      </svg>

      {/* The full name and owner, read out under the chart on hover. */}
      <figcaption className="mt-2 min-h-[20px] font-accent text-[13px] text-ink-dim">
        {hover !== null ? `${workflows[hover].name} · ${workflows[hover].progress}% complete` : ""}
      </figcaption>
    </figure>
  );
}
