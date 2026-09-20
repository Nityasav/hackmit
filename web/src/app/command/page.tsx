"use client";

import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { SourcesPanel } from "@/components/SourcesPanel";
import { PageHeader } from "@/components/ui";
import { useData } from "@/lib/data";

export default function RecordsPage() {
  const { ws } = useData();
  return (
    <>
      <ReviewWorkspace />
      <div className="mt-8">
        <PageHeader title="Source records & uploads" />
        {/* Keyed so switching workspace resets the upload draft rather than
            carrying another institution's staged files across. */}
        <SourcesPanel key={ws} />
      </div>
    </>
  );
}
