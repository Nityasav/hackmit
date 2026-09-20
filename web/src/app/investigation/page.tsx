"use client";

import { Investigation } from "@/components/investigation/Investigation";
import { useData } from "@/lib/data";

/**
 * The product: the agent organization investigates one company's committed books, cites the
 * exact lines, re-check each other, and hand back a decision to make.
 */
export default function InvestigationPage() {
  const { ws } = useData();
  // Keyed on the workspace, so switching never shows the previous one's run.
  return <Investigation key={ws} ws={ws} />;
}
