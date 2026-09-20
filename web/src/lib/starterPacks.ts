/**
 * Starter packs: fictional records to try the product with when you have no
 * files of your own yet.
 *
 * Every pack is generated against the workspace's own period and currency, so
 * the dates always fall inside the review window someone chose rather than a
 * window this file guessed. Nothing here is a shortcut past intake: the packs
 * produce ordinary CSV and Markdown bytes, and they are uploaded, mapped,
 * validated and committed through the same path as a real file. A pack that
 * would not pass validation is a broken pack, not a special case.
 *
 * The numbers are built to tie: the payroll subledger equals the payroll-mapped
 * ledger activity, the opening trial balance balances, and every journal
 * balances. The differences that remain are deliberate, so a first run has
 * something true to find — a repeated invoice, an overspent supplies budget, a
 * restricted allocation with no service record, a collection reference no
 * deposit answers.
 */
import type { SourceRole } from "./types";

export interface PackFile {
  name: string;
  role: SourceRole;
  text: string;
}

export interface StarterPack {
  id: string;
  label: string;
  /** One line: what someone gets by loading this. */
  summary: string;
  /** What the checks and the agents should have to say about it. */
  expect: string;
  build: (period: Period) => PackFile[];
}

export interface Period {
  start: string;
  end: string;
  currency: string;
}

/**
 * Day `offset` of the review period, never past its end.
 *
 * A pack has to be legal in a three-day period as well as a month, and intake
 * rejects activity outside the window, so a short period compresses the story
 * rather than breaking it.
 */
export function periodDay(period: { start: string; end: string }, offset: number): string {
  const start = new Date(period.start + "T00:00:00Z");
  const end = new Date(period.end + "T00:00:00Z");
  const wanted = new Date(start.getTime() + offset * 86_400_000);
  const chosen = wanted > end ? end : wanted;
  return chosen.toISOString().slice(0, 10);
}

function csv(headers: string[], rows: (string | number)[][]): string {
  const line = (cells: (string | number)[]) =>
    cells
      .map((cell) => {
        const text = String(cell);
        return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
      })
      .join(",");
  return [line(headers), ...rows.map(line)].join("\n") + "\n";
}

/** Exact major units, the way a finance export writes them. */
function amount(cents: number): string {
  return (cents / 100).toFixed(2);
}

// ---------------------------------------------------------------------------
// Riverbend Middle School — one school, one month, books that tie.
// ---------------------------------------------------------------------------

const CHART: [string, string, string, string][] = [
  ["1000", "Operating bank", "asset", "balance_sheet"],
  ["1100", "Undeposited receipts", "asset", "balance_sheet"],
  ["1200", "Fees receivable", "asset", "balance_sheet"],
  ["2000", "Accounts payable", "liability", "balance_sheet"],
  ["2100", "Payroll liabilities", "liability", "balance_sheet"],
  ["3000", "Fund balance", "equity", "balance_sheet"],
  ["4000", "Student fee revenue", "revenue", "operating"],
  ["4100", "Sponsorship revenue", "revenue", "operating"],
  // report_mapping "payroll" is what ties the subledger to the ledger (L07).
  ["5000", "Instructional salaries", "expense", "payroll"],
  ["5100", "Employer benefits", "expense", "payroll"],
  ["5200", "Classroom supplies", "expense", "operating"],
  ["5300", "Field trip costs", "expense", "operating"],
];

function chartFile(period: Period): PackFile {
  return {
    name: "chart-of-accounts.csv",
    role: "chart",
    text: csv(
      ["account", "name", "type", "report_mapping", "effective_from"],
      CHART.map(([account, name, type, mapping]) => [account, name, type, mapping, period.start]),
    ),
  };
}

function openingFile(period: Period): PackFile {
  // Debits 50,400.00 = credits 50,400.00.
  const rows: [string, string, number, number][] = [
    ["OB-01", "1000", 4_800_000, 0],
    ["OB-02", "1200", 240_000, 0],
    ["OB-03", "2000", 0, 615_000],
    ["OB-04", "3000", 0, 4_425_000],
  ];
  return {
    name: "opening-trial-balance.csv",
    role: "opening",
    text: csv(
      ["record_id", "account", "balance_date", "debit", "credit"],
      // Intake requires the opening balance to be dated at the start of the
      // period, before any activity.
      rows.map(([id, account, debit, credit]) => [id, account, period.start, amount(debit), amount(credit)]),
    ),
  };
}

function ledgerFile(period: Period): PackFile {
  const rows: [string, string, string, string, number, number][] = [
    // Payroll posting. Debits to the payroll-mapped accounts total 19,680.00,
    // which is the subledger's gross (16,400.00) plus employer cost (3,280.00).
    ["JE-2001", "1", periodDay(period, 14), "5000", 1_640_000, 0],
    ["JE-2001", "2", periodDay(period, 14), "5100", 328_000, 0],
    ["JE-2001", "3", periodDay(period, 14), "1000", 0, 1_245_000],
    ["JE-2001", "4", periodDay(period, 14), "2100", 0, 395_000],
    ["JE-2001", "5", periodDay(period, 14), "2100", 0, 328_000],
    // Classroom supplies: 4,150.00 against an approved 3,000.00.
    ["JE-2002", "1", periodDay(period, 7), "5200", 415_000, 0],
    ["JE-2002", "2", periodDay(period, 7), "2000", 0, 415_000],
    // Field trips: 950.00 against an approved 1,200.00.
    ["JE-2003", "1", periodDay(period, 11), "5300", 95_000, 0],
    ["JE-2003", "2", periodDay(period, 11), "2000", 0, 95_000],
    // Fees receipted into the undeposited-cash account, then what reached the bank.
    ["JE-2004", "1", periodDay(period, 8), "1100", 75_100, 0],
    ["JE-2004", "2", periodDay(period, 8), "4000", 0, 75_100],
    ["JE-2005", "1", periodDay(period, 11), "1000", 39_100, 0],
    ["JE-2005", "2", periodDay(period, 11), "1100", 0, 39_100],
  ];
  return {
    name: "general-ledger.csv",
    role: "ledger",
    text: csv(
      ["entry_id", "line_id", "date", "account", "debit", "credit"],
      rows.map(([entry, line, date, account, debit, credit]) => [entry, line, date, account, amount(debit), amount(credit)]),
    ),
  };
}

function payrollFile(period: Period): PackFile {
  // Gross 16,400.00 − deductions 3,950.00 = net 12,450.00; employer cost 3,280.00,
  // which is what the payroll-to-ledger tie expects to find posted.
  const rows: [string, string, number, number, number, number][] = [
    ["PAY-1001", "EMP-014", 620_000, 155_000, 465_000, 124_000],
    ["PAY-1002", "EMP-027", 540_000, 129_600, 410_400, 108_000],
    ["PAY-1003", "EMP-033", 480_000, 110_400, 369_600, 96_000],
  ];
  return {
    name: "payroll-register.csv",
    role: "payroll",
    text: csv(
      ["record_id", "employee_id", "period_start", "period_end", "pay_date", "gross", "deductions", "net", "employer_cost"],
      rows.map(([id, employee, gross, deductions, net, employer]) => [
        id, employee, period.start, period.end, periodDay(period, 14),
        amount(gross), amount(deductions), amount(net), amount(employer),
      ]),
    ),
  };
}

function budgetFile(period: Period): PackFile {
  return {
    name: "approved-budget.csv",
    role: "budgets",
    text: csv(
      ["record_id", "account", "period", "amount", "approval_reference"],
      [
        ["BUD-01", "5200", period.start.slice(0, 7), amount(300_000), "BOARD-2026-07"],
        ["BUD-02", "5300", period.start.slice(0, 7), amount(120_000), "BOARD-2026-07"],
      ],
    ),
  };
}

function invoiceFile(period: Period): PackFile {
  // INV-001 and INV-002 share vendor, invoice number and amount: a duplicate
  // candidate, not a proven duplicate payment.
  const rows: [string, string, string, number, number][] = [
    ["INV-001", "VEND-ATLAS", "ATL-7741", 2, 125_000],
    ["INV-002", "VEND-ATLAS", "ATL-7741", 5, 125_000],
    ["INV-003", "VEND-NORTHWIND", "NW-2210", 10, 290_000],
    ["INV-004", "VEND-CLARKE", "CB-0455", 17, 67_500],
    ["INV-005", "VEND-NORTHWIND", "NW-2255", 21, 148_000],
  ];
  return {
    name: "vendor-invoices.csv",
    role: "vendor_invoices",
    text: csv(
      ["record_id", "vendor_id", "invoice_number", "invoice_date", "due_date", "amount"],
      rows.map(([id, vendor, number, offset, cents]) => [
        id, vendor, number, periodDay(period, offset), periodDay(period, offset + 30), amount(cents),
      ]),
    ),
  };
}

function vendorsFile(): PackFile {
  return {
    name: "vendors.csv",
    role: "vendors",
    text: csv(
      ["vendor_id", "name", "country", "payment_terms_days"],
      [
        ["VEND-ATLAS", "Atlas Facilities Ltd", "US", "30"],
        ["VEND-NORTHWIND", "Northwind Supply Co.", "US", "30"],
        ["VEND-CLARKE", "Clarke & Bell Advisory", "US", "14"],
      ],
    ),
  };
}

function accountingPolicyFile(period: Period): PackFile {
  return {
    name: "accounting-policy.md",
    role: "policy",
    text: [
      "# Finance policy (extract)",
      "",
      `Period covered: ${period.start} to ${period.end}. Reporting currency: ${period.currency}.`,
      "",
      "## 3. Purchasing",
      "",
      "3.1 A vendor invoice above 1,000.00 requires a matching purchase order and a goods receipt",
      "before it may be scheduled for payment.",
      "",
      "3.2 Duplicate vendor, invoice number and amount must be investigated before payment, and a",
      "second payment may not be released while that investigation is open.",
      "",
      "## 6. Payroll",
      "",
      "6.1 Payroll expense is gross compensation plus employer costs. Net pay is a settlement",
      "amount, not an expense.",
      "",
      "## 8. Budget",
      "",
      "8.1 Spending above an approved budget line requires written explanation at close; overspend",
      "alone is not an exception finding.",
    ].join("\n") + "\n",
  };
}

export const STARTER_PACKS: StarterPack[] = [
  {
    id: "riverbend-close",
    label: "Riverbend Trading Co. — full month close",
    summary: "8 files: chart, opening balances, ledger, payroll, the approved budget, the vendor register with its invoices, and the finance policy the checks read.",
    expect: "The books tie: the opening trial balance balances, every journal balances, and payroll expense equals what the ledger posts. What is left for the review to find is a repeated vendor invoice and supplies overspent against the approved budget.",
    build: (period) => [
      chartFile(period),
      openingFile(period),
      ledgerFile(period),
      payrollFile(period),
      budgetFile(period),
      vendorsFile(),
      invoiceFile(period),
      accountingPolicyFile(period),
    ],
  },
  {
    id: "riverbend-p2p",
    label: "Purchase to pay — vendors and invoices",
    summary: "3 files: the vendor register, the invoices received against it and the finance policy that governs them.",
    expect: "Accounts payable has a population to test. The duplicate candidate shows up; the purchase orders and goods receipts a three-way match needs are reported as missing rather than assumed.",
    build: (period) => [vendorsFile(), invoiceFile(period), accountingPolicyFile(period)],
  },
  {
    id: "riverbend-ledger",
    label: "Ledger only — quick start",
    summary: "3 files: chart of accounts, a balanced opening trial balance and one month of journals.",
    expect: "The fastest committed snapshot. Every journal balances, so the checks report what is missing — no invoices, no payroll, no budget — rather than a difference.",
    build: (period) => [chartFile(period), openingFile(period), ledgerFile(period)],
  },
];

/** The pack as browser files, ready for the ordinary upload path. */
export function packFiles(pack: StarterPack, period: Period): { file: File; role: SourceRole }[] {
  return pack.build(period).map(({ name, role, text }) => ({
    file: new File([text], name, { type: name.endsWith(".csv") ? "text/csv" : "text/markdown" }),
    role,
  }));
}
