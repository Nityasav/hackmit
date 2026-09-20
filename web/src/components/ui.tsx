"use client";

import { cn } from "@/lib/utils";
import { InteractiveHoverButton } from "@/components/ui/interactive-hover-button";
import type { AgentId } from "@/lib/types";

/**
 * The shared pieces, and only the shared pieces.
 *
 * Every export here is used by a screen someone can reach. A component that
 * nothing renders is not a building block, it is a thing to maintain, so it
 * comes out rather than waiting for a use that never arrives.
 */

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
export function Figure({ label, value, note }: { label: string; value: React.ReactNode; note?: string }) {
  return (
    <div className="px-5 first:pl-0 last:pr-0">
      <div className="text-[12.5px] text-ink-dim">{label}</div>
      <div className="mt-1.5 font-num text-[26px] font-semibold leading-none tracking-tight tabular-nums">{value}</div>
      {note && <div className="mt-2 font-accent text-[13px] text-ink-dim">{note}</div>}
    </div>
  );
}

/** Three tones, because a status is either bad, fine, or neither. */
type Tone = "red" | "green" | "gray";

const TONE: Record<Tone, string> = {
  red: "bg-red-50 text-red-800 ring-1 ring-red-200",
  green: "bg-green-50 text-green-800 ring-1 ring-green-200",
  gray: "bg-surface-2 text-ink-dim ring-1 ring-line",
};

export function Pill({ tone = "gray", children, className = "" }: { tone?: Tone; children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-none px-2.5 py-1 text-[12px] font-semibold ${TONE[tone]} ${className}`}>
      {children}
    </span>
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
