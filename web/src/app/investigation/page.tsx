"use client";

import { Investigation } from "@/components/investigation/Investigation";
import { useData } from "@/lib/data";

/**
 * The product: five agents investigate one school's committed books, cite the
 * exact lines, re-check each other, and hand back a decision to make.
 */
export default function InvestigationPage() {
  const { ws } = useData();
  // Keyed on the school, so switching never shows the previous school's run.
  return <Investigation key={ws} ws={ws} />;
}
