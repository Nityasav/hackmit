/**
 * The whole navigation, in the order the work happens: put the books in, read
 * what went in, let the agents investigate it, watch them do it, hand over the
 * briefing.
 *
 * Nothing else is a destination. If a screen is worth reaching, it belongs
 * inside one of these five.
 *
 * Agents is its own destination rather than a section of Investigation because it
 * is the answer to "what is happening right now", and that question is asked while
 * a run is in flight — not after scrolling past the box that started it.
 */
export type NavId = "books" | "files" | "investigation" | "agents" | "briefing";

export interface NavItem {
  id: NavId;
  label: string;
  href: string;
  /** One plain line: what you do here. Used as the link's title. */
  hint: string;
}

export const NAV: NavItem[] = [
  { id: "books", label: "Books", href: "/", hint: "Add this company's records" },
  { id: "files", label: "Files", href: "/files", hint: "Read the files the agents read" },
  { id: "investigation", label: "Investigation", href: "/investigation", hint: "Run and review investigations" },
  { id: "agents", label: "Agents", href: "/agents", hint: "Watch the agents work, step by step" },
  { id: "briefing", label: "Briefing", href: "/briefing", hint: "Review and export results" },
];
