"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";

import { track } from "@/lib/activity";

function Tracker() {
  const pathname = usePathname();
  const params = useSearchParams();
  // React runs effects twice in development; without this the same view is
  // recorded twice for every navigation.
  const last = useRef<string | null>(null);

  useEffect(() => {
    const query = params.toString();
    const key = query ? `${pathname}?${query}` : pathname;
    if (last.current === key) return;
    last.current = key;

    // The dashboard store persists under this key; reading it keeps a page view
    // attributed to the workspace being looked at without re-rendering on every change.
    let workspaceId: string | null = null;
    try {
      const saved: unknown = JSON.parse(localStorage.getItem("schooltrace.dashboard") ?? "null");
      const id = (saved as { state?: { workspaceId?: unknown } } | null)?.state?.workspaceId;
      workspaceId = typeof id === "string" && id ? id : null;
    } catch {}

    void track("page_view", { workspaceId, target: pathname, metadata: query ? { query } : {} });
  }, [pathname, params]);

  return null;
}

/**
 * Records each view the signed-in person lands on. Rendered in the layout so
 * it follows every navigation without each page having to remember to call it.
 */
export function ActivityTracker() {
  return (
    <Suspense>
      <Tracker />
    </Suspense>
  );
}
