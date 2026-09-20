import type { SourceRole } from "./types";

// Match complete import schemas, not filenames or financial-sounding prose.
const schemas: Partial<Record<SourceRole, string[]>> = {
  chart: ["account", "name", "type", "report_mapping", "effective_from"],
  opening: ["record_id", "account", "balance_date", "debit", "credit"],
  ledger: ["entry_id", "line_id", "date", "account", "debit", "credit"],
  payroll: ["record_id", "employee_id", "service_start", "service_end", "pay_date", "gross", "deductions", "net", "employer_cost", "award_id", "award_amount"],
  grants: ["award_id", "name", "ceiling", "valid_from", "valid_to"],
  budget: ["record_id", "account", "amount", "approval_reference"],
  invoice: ["record_id", "vendor_id", "invoice_number", "service_date", "amount"],
  fees: ["record_id", "student_ref", "fee_type", "charge_date", "amount"],
  collections: ["record_id", "collected_by", "collection_date", "method", "amount"],
  deposits: ["record_id", "deposit_date", "bank_reference", "amount"],
  sponsorships: ["record_id", "sponsor_id", "program", "pledge_date", "due_date", "amount"],
};
const optional = ["currency", "school", "fund", "department", "award_id", "ledger_entry_id", "ledger_line_id", "effective_to", "po_id", "receipt_id", "student_ref", "fee_record_id", "deposit_reference", "collection_reference", "program", "waiver_reference", "due_date"];
export type Detection = { role: SourceRole; mapping: Record<string, string>; note: string };
const normalize = (s: string) => s.trim().toLowerCase().replace(/[ -]+/g, "_");

function header(text: string): string[] {
  const cells: string[] = [];
  let cell = "", quoted = false;
  const source = text.replace(/^\uFEFF/, "");
  for (let i = 0; i < source.length; i++) {
    const c = source[i];
    if (c === '"') {
      if (quoted && source[i + 1] === '"') { cell += '"'; i++; }
      else quoted = !quoted;
    } else if (!quoted && c === ",") { cells.push(cell); cell = ""; }
    else if (!quoted && (c === "\n" || c === "\r")) { cells.push(cell); return cells; }
    else cell += c;
  }
  return quoted ? [] : [...cells, cell];
}

export function detectSource(name: string, text: string, publicOnly = false): Detection {
  const fallback: Detection = { role: "document", mapping: {}, note: "Type unclear — check the file type before importing." };
  if (publicOnly) return { ...fallback, note: "Public-document workspace — kept as reference evidence." };
  if (/\.csv$/i.test(name)) {
    const columns = header(text);
    const normalized = columns.map(normalize);
    if (new Set(normalized).size !== columns.length) return fallback;
    const matches = Object.entries(schemas).filter(([, fields]) => fields.every(f => normalized.includes(f)));
    if (matches.length !== 1) return fallback;
    const [role, required] = matches[0];
    const allowed = new Set([...required, ...optional]);
    const mapping = Object.fromEntries(columns.flatMap((original, i) => allowed.has(normalized[i]) ? [[normalized[i], original]] : []));
    return { role: role as SourceRole, mapping, note: "Detected from CSV columns. You can change the type." };
  }
  // Strong content cues only. A document mentioning both needs a human choice.
  const service = /(?:employees?|payroll)[\s,:-]|\bEMP-[A-Z0-9]/i.test(text) && /(?:service allocation|hours total|actual service)/i.test(text);
  const policy = /(?:award|grant)[\s:-]/i.test(text) && /(?:eligible|require|must)/i.test(text) && /(?:terms|ceiling|award period|valid:)/i.test(text);
  if (service !== policy) return { role: service ? "service" : "policy", mapping: {}, note: "Suggested from document text — confirm the type." };
  return fallback;
}
