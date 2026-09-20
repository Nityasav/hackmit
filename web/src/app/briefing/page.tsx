"use client";

import { ReviewWorkspace } from "@/components/ReviewWorkspace";

/** The artifact handed to the director: findings, limits, and a file to take away. */
export default function BriefingPage() {
  return <ReviewWorkspace section="reports" />;
}
