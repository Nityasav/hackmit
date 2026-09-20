import type { TabId } from "./types";

export interface TabDef {
  id: TabId;
  label: string;
  href: string;
  group: "Office of the CFO" | "Work product" | "Agent brain";
  tag?: string;
}

export const TABS: TabDef[] = [
  { id: "command", label: "Records & overview", href: "/command", group: "Office of the CFO" },
  { id: "board", label: "Agent board", href: "/board", group: "Office of the CFO" },
  { id: "workflows", label: "Workflows", href: "/workflows", group: "Office of the CFO" },
  { id: "findings", label: "Findings", href: "/findings", group: "Work product" },
  { id: "approvals", label: "Approvals", href: "/approvals", group: "Work product" },
  { id: "reports", label: "Reports", href: "/reports", group: "Work product" },
  { id: "reasoning", label: "Reasoning log", href: "/reasoning", group: "Agent brain" },
  { id: "learning", label: "Learning", href: "/learning", group: "Agent brain", tag: "RSI" },
];

export const TAB_HREF = Object.fromEntries(TABS.map((t) => [t.id, t.href])) as Record<TabId, string>;
