/**
 * The whole navigation, in the order the work happens: put the books in, read
 * what went in, let the agents investigate it, hand over the briefing.
 *
 * Nothing else is a destination. If a screen is worth reaching, it belongs
 * inside one of these four.
 */
export type NavId = "books" | "files" | "investigation" | "briefing";

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
  { id: "briefing", label: "Briefing", href: "/briefing", hint: "Review and export results" },
];
