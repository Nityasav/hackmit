import { describe, it } from "bun:test";
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

  /**
   * The checklist is an AnimatedDisclosure now, not a <details>. A native <details> keeps
   * its content in the DOM when shut, so the groups used to be in the server-rendered HTML
   * even while collapsed; the animated one mounts its body only once opened. The guarantee
   * under test is unchanged — the checklist starts collapsed — so it is asserted where it
   * now lives: on the control that says so, and on a body that has not arrived yet.
   */
  it("renders a current empty checklist, collapsed", () => {
    const coverage = { requirements: [], satisfied_count: 0, required_count: 0 } as unknown as Coverage;
    const html = renderToStaticMarkup(<DataRequirements ws="test" coverage={coverage} onSaved={() => {}} />);

    // The summary — the only thing a shut disclosure shows — is present, counts and all.
    assert.ok(html.includes("What the agents need"));
    assert.ok(html.includes("required items supplied"));
    assert.ok(html.includes("remaining"));

    assert.ok(!/<details/.test(html), "the native disclosure is gone");
    assert.ok(html.includes('aria-expanded="false"'), "Requirements start collapsed");
    assert.ok(!html.includes('aria-expanded="true"'), "Requirements start collapsed");

    // Everything below the summary is part of that collapsed body, and so is absent from
    // the static markup rather than merely hidden. Each string is still accounted for.
    for (const body of [
      "Everything required has been supplied",
      "Required records and settings",
      "Optional records and settings",
      "Already supplied",
    ]) {
      assert.ok(!html.includes(body), `"${body}" is inside the collapsed checklist`);
    }
  });
});
