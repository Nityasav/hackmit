import React from "react";
import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { Orchestrator, Reply } from "../src/components/investigation/Orchestrator";
import { Subagent } from "../src/components/investigation/Investigation";

test("specialist completion and failure stay beside its Run control", () => {
  const agent = { id: "A2", name: "Accounts Receivable", charter: "Review receivables", reads: [], ready: true, budget: { usd_cents: 40 } };
  const state = { running: null, results: [{ agent_id: "A2", decision_id: "saved-1", result: { summary: "Remittances require review." } }], runErrors: {}, run: async () => {} };
  const html = renderToStaticMarkup(<Subagent agent={agent} state={state} ws="test" />);
  expect(html).toContain("Result ready");
  expect(html).toContain("Remittances require review.");
  expect(html).toContain("View deliverable &amp; download PDF");
  const error = renderToStaticMarkup(<Subagent agent={agent} state={{ ...state, results: [], runErrors: { A2: "Evidence unavailable" } }} ws="test" />);
  expect(error).toContain("Evidence unavailable");
});

test("empty CFO panel has starter prompts and compact aligned controls", () => {
  const html = renderToStaticMarkup(<Orchestrator ws="test-workspace" />);
  expect(html).toContain("Can we close the period?");
  expect(html).toContain("Ask CFO");
  expect(html).toContain("Run financial audit");
  expect(html).not.toContain("Nothing has been asked");
});

describe("audit replies", () => {
  for (const agent of ["A2", { id: "A2", name: "Accounts Receivable" }]) {
    test(`renders saved escalation shape ${typeof agent}`, () => {
      const turn = { id: "turn-1", thread_id: "run-1", role: "orchestrator", status: "waiting_on_you", created_at: "2026-09-20",
        body: { text: "Review paused.", routed_to: ["Treasurer"], findings: [],
          escalations: [{ approval_id: "ESC-1", agent, title: "Review receipt", reasons: ["ambiguous_remittance"] }] } };
      const html = renderToStaticMarkup(<Reply turn={turn} deciding="" onDecide={() => {}} />);
      expect(html).toContain(typeof agent === "string" ? agent : agent.name);
      expect(html).toContain("Review receipt");
    });
  }
});
