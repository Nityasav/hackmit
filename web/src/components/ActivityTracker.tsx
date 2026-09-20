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

    let workspaceId: string | null = null;
    try {
      workspaceId = localStorage.getItem("st.ws");
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
