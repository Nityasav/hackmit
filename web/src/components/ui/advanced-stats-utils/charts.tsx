"use client";

import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { money } from "@/lib/format";

export interface ClippedAreaPoint {
  label: string;
  /** Money still unexplained at this point in the close, in cents. */
  open_cents: number;
  /** Money an approved correction has already cleared, in cents. */
  cleared_cents: number;
}

const config = {
  open_cents: { label: "Open exposure", color: "var(--color-accent-bad)" },
  cleared_cents: { label: "Cleared", color: "var(--color-accent-good)" },
} satisfies ChartConfig;

/**
 * Exposure over the close: what the agents have cleared against what is still
 * open. Both series are integer cents; only this component formats them.
 */
export function ClippedAreaChart({ data }: { data: ClippedAreaPoint[] }) {
  return (
    <ChartContainer config={config} className="aspect-auto h-[220px] w-full">
      <AreaChart data={data} margin={{ left: 4, right: 4, top: 4, bottom: 0 }}>
        <defs>
          <linearGradient id="fill-open" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent-bad)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="var(--color-accent-bad)" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="fill-cleared" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent-good)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="var(--color-accent-good)" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="var(--color-line)" />
        <XAxis
          dataKey="label"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          minTickGap={16}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={56}
          tickFormatter={(v: number) => `$${Math.round(v / 100000)}k`}
        />
        <ChartTooltip
          content={
            <ChartTooltipContent
              formatter={(value, name) => (
                <span className="flex w-full justify-between gap-3">
                  <span className="text-muted-foreground">
                    {config[name as keyof typeof config]?.label ?? name}
                  </span>
                  <span className="font-mono font-num tabular-nums text-foreground">
                    {money(Number(value))}
                  </span>
                </span>
              )}
            />
          }
        />
        <Area
          dataKey="cleared_cents"
          type="monotone"
          stackId="a"
          stroke="var(--color-accent-good)"
          strokeWidth={1.5}
          fill="url(#fill-cleared)"
        />
        <Area
          dataKey="open_cents"
          type="monotone"
          stackId="a"
          stroke="var(--color-accent-bad)"
          strokeWidth={1.5}
          fill="url(#fill-open)"
        />
      </AreaChart>
    </ChartContainer>
  );
}
