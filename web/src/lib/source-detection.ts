import type { SourceRole } from "./types";

/**
 * Work out what a file is from its columns, before it is uploaded.
 *
 * Match complete import schemas, not filenames or financial-sounding prose. A file
 * called `invoices.csv` that does not carry an invoice's columns is not an invoice
 * register, and guessing from the name is how a payroll export gets imported as one.
 *
 * The schema table is **fetched from the API**, not restated here. It used to be a copy
 * of `roles.FIELDS` written in TypeScript, which meant adding a record type silently
 * stopped it being detected until someone remembered to edit both. `/api/roles` serves
 * the one definition and both sides read it.
 */

export type Detection = { role: SourceRole; mapping: Record<string, string>; note: string };

interface RoleSchema {
  id: SourceRole;
  label: string;
  required: string[];
}

export interface Vocabulary {
  roles: RoleSchema[];
  documents: { id: SourceRole; label: string }[];
  optional: string[];
}

const normalize = (s: string) => s.trim().toLowerCase().replace(/[ -]+/g, "_");

/** The first row of a CSV, honouring quoted cells and a leading byte-order mark. */
function header(text: string): string[] {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  const source = text.replace(/^﻿/, "");
  for (let i = 0; i < source.length; i++) {
    const c = source[i];
    if (c === '"') {
      if (quoted && source[i + 1] === '"') {
        cell += '"';
        i++;
      } else {
        quoted = !quoted;
      }
    } else if (!quoted && c === ",") {
      cells.push(cell);
      cell = "";
    } else if (!quoted && (c === "\n" || c === "\r")) {
      cells.push(cell);
      return cells;
    } else {
      cell += c;
    }
  }
  return quoted ? [] : [...cells, cell];
}

const UNCLEAR: Detection = {
  role: "document",
  mapping: {},
  note: "Type unclear — check the file type before importing.",
};

export function detectSource(
  name: string,
  text: string,
  vocab: Vocabulary,
  publicOnly = false,
): Detection {
  if (publicOnly) {
    return { ...UNCLEAR, note: "Public-document workspace — kept as reference evidence." };
  }
  if (!/\.csv$/i.test(name)) return UNCLEAR;

  const columns = header(text);
  const normalized = columns.map(normalize);
  // Duplicate headers mean the mapping would be ambiguous, so nothing is claimed.
  if (new Set(normalized).size !== columns.length) return UNCLEAR;

  // Exactly one role must fit. Two candidates is a question for a person, not a
  // coin toss, and the cost of being wrong is a record imported as the wrong type.
  const matches = vocab.roles.filter((role) =>
    role.required.every((field) => normalized.includes(field)));
  if (matches.length !== 1) return UNCLEAR;

  const [match] = matches;
  const allowed = new Set([...match.required, ...vocab.optional]);
  const mapping = Object.fromEntries(
    columns.flatMap((original, i) =>
      allowed.has(normalized[i]) ? [[normalized[i], original]] : []),
  );
  return {
    role: match.id,
    mapping,
    note: `Detected as ${match.label} from the CSV columns. You can change the type.`,
  };
}
