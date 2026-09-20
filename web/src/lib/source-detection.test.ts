import assert from "node:assert/strict";
import { describe, it } from "bun:test";

import { detectSource } from "./source-detection.ts";

/**
 * Run with: node --experimental-strip-types --test src/lib/source-detection.test.ts
 *
 * The vocabulary is passed in rather than fetched, so these describe the *matching*
 * rule and never depend on a running API. The columns below are the real ones from
 * `api/app/roles.py`; if they drift, the API serves the truth at run time and only
 * this fixture is stale.
 */

const vocab = {
  optional: ["currency", "department", "memo", "event_ref", "po_id", "receipt_id"],
  documents: [{ id: "document" as const, label: "Other documents" }],
  roles: [
    { id: "chart" as const, label: "Chart of accounts",
      required: ["account", "name", "type", "report_mapping", "effective_from"] },
    { id: "opening" as const, label: "Opening trial balance",
      required: ["record_id", "account", "balance_date", "debit", "credit"] },
    { id: "ledger" as const, label: "General ledger",
      required: ["entry_id", "line_id", "date", "account", "debit", "credit"] },
    { id: "vendors" as const, label: "Vendors",
      required: ["vendor_id", "name", "country", "payment_terms_days"] },
    { id: "vendor_invoices" as const, label: "Vendor invoices",
      required: ["record_id", "vendor_id", "invoice_number", "invoice_date", "due_date", "amount"] },
    { id: "bank_transactions" as const, label: "Bank transactions",
      required: ["bank_id", "bank_account", "settlement_date", "direction", "amount", "description"] },
    { id: "processor_payouts" as const, label: "Payment processor payouts",
      required: ["payout_id", "processor", "payout_date", "gross", "fees", "refunds",
                 "chargebacks", "net"] },
  ],
};

describe("source detection", () => {
  for (const role of vocab.roles) {
    it(`detects ${role.id} from its columns, with no filename hint`, () => {
      const header = role.required.join(",");
      assert.equal(detectSource("unknown.CSV", header + "\r\n", vocab).role, role.id);
    });
  }

  it("normalizes quoted headers and a byte-order mark", () => {
    const result = detectSource(
      "x.csv", '﻿"Vendor ID","Name","Country","Payment Terms Days"\n', vocab);
    assert.equal(result.role, "vendors");
    assert.equal(result.mapping.payment_terms_days, "Payment Terms Days");
  });

  it("refuses a file whose name claims more than its columns do", () => {
    // The whole point: a file called invoices.csv without an invoice's columns is
    // not an invoice register, and importing it as one would be worse than asking.
    assert.equal(detectSource("vendor_invoices.csv", "a,b,c\n", vocab).role, "document");
  });

  it("refuses duplicate headers rather than pick a mapping", () => {
    assert.equal(detectSource("x.csv", "account,account,type\n", vocab).role, "document");
  });

  it("keeps everything as evidence in a public-document workspace", () => {
    const header = vocab.roles[0].required.join(",");
    const result = detectSource("chart.csv", header + "\n", vocab, true);
    assert.equal(result.role, "document");
    assert.match(result.note, /reference evidence/);
  });
});
