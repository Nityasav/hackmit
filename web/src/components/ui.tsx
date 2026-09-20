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

// Colour by domain rather than by agent: A1 and A3 are both Treasury, and giving
// twenty-two agents twenty-two colours would carry no information. The domain letter
// is the first character of every id, and the orchestrator is its own case.
const DOMAIN_BG: Record<string, string> = {
  orchestrator: "bg-agent-cfo",
  A: "bg-agent-ap",
  B: "bg-agent-py",
  C: "bg-agent-gr",
  D: "bg-agent-au",
};

const AGENT_BG = new Proxy({} as Record<AgentId, string>, {
  get: (_target, id: string) =>
    DOMAIN_BG[id] ?? DOMAIN_BG[id.charAt(0)] ?? "bg-agent-cfo",
});

const AGENT_SHORT = new Proxy({} as Record<AgentId, string>, {
  get: (_target, id: string) => (id === "orchestrator" ? "CF" : id.toUpperCase()),
});

/** Display names, mirroring the charters in api/app/agents/registry.py. */
export const AGENT_NAME: Record<AgentId, string> = {
  orchestrator: "Chief Financial Agent",
  A: "Treasurer",
  B: "Controller",
  C: "FP&A",
  D: "Audit & Controls",
  A1: "Accounts Payable",
  A2: "Accounts Receivable",
  A3: "Bank Reconciliation",
  A4: "Cash Management",
  B1: "Month-End Close",
  B2: "Accruals & Adjustments",
  B3: "Financial Reporting",
  B4: "Close Review",
  C1: "Budgeting",
  C2: "Forecasting",
  C3: "Variance Analysis",
  C4: "Strategic Planning",
  C5: "Board Reporting",
  D1: "Audit",
  D2: "Controls Testing",
  D3: "Audit Evidence",
  D4: "Reporting & Filing",
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

/** How far through its steps a task is, as the run reports it. */
export function ProgressBar({ value, className = "h-1.5" }: { value: number; className?: string }) {
  return (
    <div className={`overflow-hidden bg-surface-2 ${className}`}>
      <div className="h-full bg-ink transition-[width] duration-700" style={{ width: `${value}%` }} />
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
