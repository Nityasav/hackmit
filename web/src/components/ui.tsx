import type { AgentId, FindingStatus, PlaybookStatus } from "@/lib/types";

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
  const dims = size === "sm" ? "h-5 w-5 text-[8.5px]" : size === "lg" ? "h-8 w-8 text-[11px]" : "h-6 w-6 text-[9.5px]";
  return (
    <span
      title={AGENT_NAME[id]}
      className={`${AGENT_BG[id]} ${dims} inline-flex flex-none items-center justify-center rounded-[7px] font-bold text-white`}
    >
      {AGENT_SHORT[id]}
    </span>
  );
}

export function Pulse({ className = "" }: { className?: string }) {
  return <span className={`inline-block h-[7px] w-[7px] flex-none animate-ping-soft rounded-full bg-teal-500 ${className}`} />;
}

export function Card({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return <div className={`rounded-[10px] border border-line bg-white p-3 ${className}`}>{children}</div>;
}

export function CardTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-2 flex items-center gap-1.5 text-[12.5px] font-semibold">
      {children}
      {right && <span className="ml-auto text-[11px] font-normal text-slate-500">{right}</span>}
    </div>
  );
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <h1 className="text-lg font-bold tracking-tight">{title}</h1>
      {subtitle && <span className="ml-1 text-[12.5px] text-slate-500">{subtitle}</span>}
      {right && <span className="ml-auto">{right}</span>}
    </div>
  );
}

export function ProgressBar({ value, className = "h-1.5" }: { value: number; className?: string }) {
  return (
    <div className={`overflow-hidden rounded bg-slate-100 ${className}`}>
      <div className="h-full rounded bg-teal-500 transition-[width] duration-700" style={{ width: `${value}%` }} />
    </div>
  );
}

type Tone = "red" | "green" | "amber" | "indigo" | "teal" | "gray" | "blue";

const TONE: Record<Tone, string> = {
  red: "bg-red-100 text-red-800",
  green: "bg-green-100 text-green-800",
  amber: "bg-amber-100 text-amber-800",
  indigo: "bg-indigo-100 text-indigo-800",
  teal: "bg-teal-100 text-teal-800",
  gray: "bg-slate-100 text-slate-600",
  blue: "bg-blue-100 text-blue-800",
};

export function Pill({ tone = "gray", children, className = "" }: { tone?: Tone; children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[10.5px] font-semibold ${TONE[tone]} ${className}`}>
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

const PLAYBOOK_STATUS: Record<PlaybookStatus, [string, Tone]> = {
  active: ["Active", "green"],
  needs_approval: ["Needs you", "amber"],
  retired: ["Retired", "gray"],
  blocked: ["Blocked", "red"],
};

export function PlaybookStatusPill({ status, note }: { status: PlaybookStatus; note?: string }) {
  const [label, tone] = PLAYBOOK_STATUS[status];
  return <Pill tone={tone}>{note ? `${label}: ${note}` : label}</Pill>;
}

export function Button({
  children,
  primary,
  onClick,
  disabled,
  title,
}: {
  children: React.ReactNode;
  primary?: boolean;
  onClick?: () => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex cursor-pointer items-center gap-1.5 rounded-[7px] border px-2.5 py-1.5 text-[11.5px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
        primary
          ? "border-teal-700 bg-teal-700 text-white hover:bg-teal-800"
          : "border-line bg-white text-slate-900 hover:border-teal-300"
      }`}
    >
      {children}
    </button>
  );
}
