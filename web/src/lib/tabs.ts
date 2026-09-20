import type { TabId } from "./types";

export interface TabDef {
  id: TabId;
  label: string;
  href: string;
  group: "Review" | "Work product";
}

/**
 * Only sections backed by the review pipeline appear here. Workflows,
 * Approvals and Learning were removed: the bundle never carried rows for them
 * outside the retired demo workspaces.
 */
export const TABS: TabDef[] = [
  { id: "command", label: "Records & overview", href: "/command", group: "Review" },
  { id: "findings", label: "Findings", href: "/findings", group: "Review" },
  { id: "board", label: "Follow-up", href: "/board", group: "Work product" },
  { id: "reports", label: "Director briefing", href: "/reports", group: "Work product" },
  { id: "reasoning", label: "Reasoning log", href: "/reasoning", group: "Work product" },
];

export const TAB_HREF = Object.fromEntries(TABS.map((t) => [t.id, t.href])) as Record<TabId, string>;
