import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { DataRequirements } from "./DataRequirements";
import type { Coverage } from "@/lib/types";

describe("coverage API compatibility", () => {
  it("shows a recoverable warning for an older API, not an all-clear", () => {
    for (const requirements of [undefined, null, {}]) {
      const coverage = { requirements } as unknown as Coverage;
      const html = renderToStaticMarkup(<DataRequirements ws="test" coverage={coverage} onSaved={() => {}} />);
      assert.ok(html.includes("Retry requirements"));
      assert.ok(!html.includes("Everything required has been supplied"));
    }
  });
  it("renders a current empty checklist", () => {
    const coverage = { requirements: [], satisfied_count: 0, required_count: 0 } as unknown as Coverage;
    const html = renderToStaticMarkup(<DataRequirements ws="test" coverage={coverage} onSaved={() => {}} />);
    assert.ok(html.includes("Everything required has been supplied"));
    assert.ok(html.includes("Required records and settings"));
    assert.ok(html.includes("Optional records and settings"));
    assert.ok(html.includes("Already supplied"));
    assert.ok(!/<details[^>]*\bopen\b/.test(html), "Requirements start collapsed");
  });
});
