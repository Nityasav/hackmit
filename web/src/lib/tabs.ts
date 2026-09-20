/**
 * The whole navigation. Three destinations, in the order the work happens:
 * put the books in, let the agents investigate them, hand over the briefing.
 *
 * Nothing else is a destination. If a screen is worth reaching, it belongs
 * inside one of these three.
 */
export type NavId = "books" | "investigation" | "briefing";

export interface NavItem {
  id: NavId;
  label: string;
  href: string;
  /** One plain line: what you do here. Used as the link's title. */
  hint: string;
}

export const NAV: NavItem[] = [
  { id: "books", label: "Books", href: "/", hint: "Add this school's records" },
  { id: "investigation", label: "Investigation", href: "/investigation", hint: "Watch the five agents check them" },
  { id: "briefing", label: "Briefing", href: "/briefing", hint: "Hand the director the result" },
];
