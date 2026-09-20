"use client";

import { useEffect } from "react";

import { cn } from "@/lib/utils";
import { InteractiveHoverButton } from "@/components/ui/interactive-hover-button";
import type { AgentId, FindingStatus } from "@/lib/types";

const AGENT_BG: Record<AgentId, string> = {
  cfo: "bg-agent-cfo",
  ap: "bg-agent-ap",
  py: "bg-agent-py",
  gr: "bg-agent-gr",
  au: "bg-agent-au",
};

const AGENT_SHORT: Record<AgentId, string> = { cfo: "CF", ap: "AP", py: "PY", gr: "GR", au: "AU" };

export const AGENT_NAME: Record<AgentId, string> = {
  cfo: "CFO Agent",
  ap: "AP & Payments",
  py: "Payroll & Budget",
  gr: "Grants & Compliance",
  au: "Internal Auditor",
};

export function AgentAvatar({ id, size = "md" }: { id: AgentId; size?: "sm" | "md" | "lg" }) {
  const dims = size === "sm" ? "h-5 w-5 text-[10.5px]" : size === "lg" ? "h-8 w-8 text-[13px]" : "h-6 w-6 text-[11px]";
  return (
    <span
      title={AGENT_NAME[id]}
      className={`${AGENT_BG[id]} ${dims} inline-flex flex-none items-center justify-center rounded-none font-bold text-white`}
    >
      {AGENT_SHORT[id]}
    </span>
  );
}

export function Pulse({ className = "" }: { className?: string }) {
  return <span className={`inline-block h-[7px] w-[7px] flex-none animate-ping-soft rounded-none bg-ink ${className}`} />;
}

export function Card({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return <div className={`rounded-none border border-line bg-surface p-4 ${className}`}>{children}</div>;
}

export function CardTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-2 text-[15px] font-semibold">
      {children}
      {right && <span className="ml-auto font-accent text-[13px] font-normal text-ink-dim">{right}</span>}
    </div>
  );
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-3">
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      {subtitle && <span className="ml-1 font-accent text-[15px] text-ink-dim">{subtitle}</span>}
      {right && <span className="ml-auto">{right}</span>}
    </div>
  );
}

/** A top-level band. Sections are told apart by space and one hairline rule,
 *  not by giving every group its own box. */
export function Section({
  title,
  right,
  children,
  first,
  className = "",
}: {
  title?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  first?: boolean;
  className?: string;
}) {
  return (
    <section className={`${first ? "" : "mt-8 border-t border-line pt-8"} ${className}`}>
      {title && (
        <div className="mb-4 flex items-baseline gap-3">
          <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
          {right && <span className="ml-auto font-accent text-[13px] text-ink-dim">{right}</span>}
        </div>
      )}
      {children}
    </section>
  );
}

/** One figure in the numbers strip: label above, figure, accent note under. */
export function Figure({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  note?: string;
  tone?: "warn" | "good";
}) {
  return (
    <div className="px-5 first:pl-0 last:pr-0">
      <div className="text-[12.5px] text-ink-dim">{label}</div>
      <div className="mt-1.5 font-num text-[26px] font-semibold leading-none tracking-tight tabular-nums">{value}</div>
      {note && (
        <div className={`mt-2 font-accent text-[13px] ${tone === "warn" ? "text-ink-dim" : "text-ink-dim"}`}>
          {note}
        </div>
      )}
    </div>
  );
}

export function ProgressBar({ value, className = "h-1.5" }: { value: number; className?: string }) {
  return (
    <div className={`overflow-hidden rounded bg-surface-2 ${className}`}>
      <div className="h-full rounded bg-ink transition-[width] duration-700" style={{ width: `${value}%` }} />
    </div>
  );
}

type Tone = "red" | "green" | "amber" | "indigo" | "teal" | "gray" | "blue";

const TONE: Record<Tone, string> = {
  red: "bg-red-50 text-red-800 ring-1 ring-red-200",
  green: "bg-green-50 text-green-800 ring-1 ring-green-200",
  amber: "bg-surface-2 text-ink-dim ring-1 ring-line",
  indigo: "bg-surface-2 text-ink-dim ring-1 ring-line",
  teal: "bg-surface-2 text-ink-dim ring-1 ring-line",
  gray: "bg-surface-2 text-ink-dim ring-1 ring-line",
  blue: "bg-surface-2 text-ink-dim ring-1 ring-line",
};

export function Pill({ tone = "gray", children, className = "" }: { tone?: Tone; children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-none px-2.5 py-1 text-[12px] font-semibold ${TONE[tone]} ${className}`}>
      {children}
    </span>
  );
}

export function AiTag({ children = "AI" }: { children?: React.ReactNode }) {
  return <Pill tone="teal">✦ {children}</Pill>;
}

const FINDING_STATUS: Record<FindingStatus, [string, Tone]> = {
  substantiated: ["Substantiated", "red"],
  hypothesized: ["Hypothesis · unreviewed", "amber"],
  cleared: ["Cleared", "green"],
  explained: ["Explained", "indigo"],
  needs_evidence: ["Needs evidence", "amber"],
  none_reported: ["None reported", "green"],
  ties: ["Ties", "green"],
};

export function FindingStatusPill({ status }: { status: FindingStatus }) {
  const [label, tone] = FINDING_STATUS[status];
  return <Pill tone={tone}>{label}</Pill>;
}



export function EmptyState({ icon = "✓", title, children }: { icon?: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 px-4 py-8 text-center">
      <div className="text-2xl text-ink-faint">{icon}</div>
      <div className="font-semibold text-ink-dim">{title}</div>
      {children && <p className="max-w-xs text-[13.5px] text-ink-faint">{children}</p>}
    </div>
  );
}

/** Confirms a decision landed. Disappears on its own. */
export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!message) return;
    const id = setTimeout(onDone, 2600);
    return () => clearTimeout(id);
  }, [message, onDone]);
  if (!message) return null;
  return (
    <div
      role="status"
      className="fixed bottom-5 left-1/2 z-30 -translate-x-1/2 animate-rise rounded-lg bg-ink px-4 py-2.5 text-[14px] font-medium text-white shadow-lg"
    >
      {message}
    </div>
  );
}

export function Button({
  children,
  primary,
  onClick,
  disabled,
  title,
}: {
  children: string;
  primary?: boolean;
  onClick?: () => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <InteractiveHoverButton
      text={children}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "w-auto px-11 text-[13.5px] [&_svg]:h-4 [&_svg]:w-4",
        // The reveal layer is absolute with no left, so it lays out from its static
        // position (after the label and the padding) and drifts right, clipping the
        // arrow. Anchor it to the edge so w-full + justify-center actually centres.
        "[&>div:nth-child(2)]:left-0",
        // The resting dot sits at 20% from the left, which drifts into the label once a
        // button is wider than the 8rem the component assumes. Pin it near the edge.
        // On hover the component's scale-[1.8] still covers the pill from there.
        "[&>div:last-child]:left-6",
        "[&>span:first-child]:relative [&>span:first-child]:z-20",
        "disabled:pointer-events-none disabled:opacity-50",
        primary
          // Primary rests filled and inverts on hover; secondary does the reverse.
          ? "border-ink bg-ink text-white [&>div:last-child]:bg-white [&>div:nth-child(2)]:text-ink"
          : "border-ink text-ink",
      )}
    />
  );
}
