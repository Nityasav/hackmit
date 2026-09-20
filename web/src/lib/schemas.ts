import { z } from "zod";

import type { Bundle } from "@/lib/types";

/**
 * Runtime shape of the bundle.
 *
 * The intake API returns untyped JSON. Casting it to Bundle only silences the
 * compiler — a schema drift would surface later as a blank panel or a crash
 * deep in a component. Parsing here fails at the boundary, where the message
 * can say what is actually wrong.
 */

/**
 * A field the contract declares optional, tolerant of an explicit null.
 *
 * Postgres omits these, but the intake API may send null. The TypeScript
 * contract says `T | undefined`, so null is normalised away here rather than
 * widening every consumer to accept it.
 */
function optional<T extends z.ZodTypeAny>(schema: T) {
  return schema.nullish().transform((v) => v ?? undefined);
}

// Mirrors `AgentId` in api/app/models.py. A bundle naming an agent this does not
// list fails to parse and the dashboard renders an error, so the two move together.
const agentIdSchema = z.enum([
  "orchestrator",
  "A", "B", "C", "D",
  "A1", "A2", "A3", "A4",
  "B1", "B2", "B3", "B4",
  "C1", "C2", "C3", "C4", "C5",
  "D1", "D2", "D3", "D4",
]);

// As wide as TabId in api/app/models.py. See the note on TabId in types.ts:
// narrowing this below what the API emits makes whole bundles fail to parse.
const tabIdSchema = z.enum([
  "command", "board", "workflows", "findings",
  "approvals", "reports", "reasoning", "learning",
]);

const workspaceSchema = z.object({
  id: z.string(),
  name: z.string(),
  kind: z.enum(["synthetic", "public"]),
  period: z.string(),
  mode: z.enum(["live", "not_started"]),
  snapshot_id: z.string(),
  model: z.string(),
  run_budget: z.object({ used: z.number(), total: z.number() }),
  source_url: optional(z.string()),
  intake: optional(z.boolean()),
  currency: optional(z.string()),
  profile: optional(z.string()),
});

const agentSchema = z.object({
  id: agentIdSchema,
  name: z.string(),
  short: z.string(),
  role: z.string(),
  status: z.enum(["working", "waiting", "idle"]),
  doing: z.string(),
});

const briefingSchema = z.object({
  generated_at: z.string(),
  text: z.string(),
  actions: z.array(z.object({
    label: z.string(),
    href: tabIdSchema,
    primary: optional(z.boolean()),
  })),
});



const taskSchema = z.object({
  id: z.string(),
  agent: agentIdSchema,
  title: z.string(),
  workflow: z.string(),
  column: z.enum(["queued", "working", "needs_you", "auditor_review", "done"]),
  progress: z.number(),
  // Declared `T | null` and required, so null must be accepted, not treated
  // as absent.
  eta_s: z.number().nullable(),
  started_at: z.string().nullable(),
  rationale: z.string().nullable(),
  tool_calls: z.object({ used: z.number(), budget: z.number() }),
  steps: z.array(z.object({
    title: z.string(),
    detail: optional(z.string()),
    state: z.enum(["done", "running", "todo"]),
    memory: optional(z.boolean()),
  })),
  todos: z.array(z.string()),
  note: optional(z.string()),
  note_tone: optional(z.enum(["warn", "info"])),
  approval_id: optional(z.string()),
});

const evidenceNodeSchema = z.object({
  label: z.string(),
  kind: z.enum(["record", "award", "doc", "calc", "page"]),
  tone: z.enum(["neutral", "bad", "good"]),
  // `optional()`, not `.optional()`: the API sends these as explicit null, and
  // a bare .optional() accepts an absent key but rejects a null one.
  edge: optional(z.string()),
  locator: optional(z.string()),
  source_preview: optional(z.string()),
});

const findingSchema = z.object({
  id: z.string(),
  agent: agentIdSchema,
  title: z.string(),
  summary: z.string(),
  status: z.enum([
    "hypothesized", "substantiated", "cleared", "explained",
    "needs_evidence", "none_reported", "ties",
  ]),
  amount_cents: z.number().nullable(),
  amount_note: optional(z.string()),
  verified_by: optional(agentIdSchema),
  evidence: z.array(evidenceNodeSchema),
});


const decisionSchema = z.object({
  id: z.string(),
  run: z.string(),
  time: z.string(),
  agent: agentIdSchema,
  // Absent here, zod silently dropped it: a human decision arrived at the UI
  // indistinguishable from an agent's.
  actor: optional(z.string()),
  action: z.string(),
  summary: z.string(),
  when: z.object({
    run: z.string(), step: z.string(), started: z.string(),
    finished: z.string(), trigger: z.string(),
  }),
  how: z.array(z.object({ tool: z.string(), input: z.string(), output: z.string() })),
  why: z.string(),
  outcome: z.string(),
  memory_checks: z.array(z.object({ text: z.string(), ok: z.boolean() })),
});

const playbookSchema = z.object({
  id: z.string(),
  title: z.string(),
  source: z.string(),
  proposed_by: agentIdSchema,
  // Sent as a string by the projection; kept a string rather than coerced, so
  // a shape change surfaces here instead of rendering as NaN.
  uses: z.string(),
  status: z.enum(["active", "retired"]),
  status_note: z.string(),
});

const approvalSchema = z.object({
  id: z.string(),
  agent: agentIdSchema,
  kind: z.enum(["journal", "payment", "playbook", "evidence", "decision"]),
  title: z.string(),
  summary: z.string(),
  verified: z.boolean(),
  status: z.enum(["pending", "approved", "rejected"]),
  journal: z.array(z.object({
    account: z.string(), fund: z.string(),
    debit_cents: z.number(), credit_cents: z.number(),
  })).nullable(),
  effects: z.array(z.object({
    label: z.string(), value: z.string(),
    tone: optional(z.enum(["good", "neutral"])),
  })).nullable(),
  finding_id: optional(z.string()),
});

export const bundleSchema = z.object({
  contract_version: z.number().optional(),
  workspace: workspaceSchema,
  agents: z.array(agentSchema),
  briefing: briefingSchema,
  tasks: z.array(taskSchema),
  findings: z.array(findingSchema),
  decisions: z.array(decisionSchema),
  playbooks: z.array(playbookSchema),
  // Dropped from this schema, the whole approvals list was silently stripped
  // and nothing in the UI could offer a person the decision an agent escalated.
  approvals: z.array(approvalSchema),
});

/**
 * Parses a payload and, on failure, raises an error naming the first field
 * that did not match rather than dumping the whole Zod tree.
 */
export function parseOrThrow<T>(schema: z.ZodType<T>, value: unknown, label: string): T {
  const result = schema.safeParse(value);
  if (result.success) return result.data;

  const first = result.error.issues[0];
  const path = first?.path.join(".") || "(root)";
  throw new Error(`${label} did not match the expected shape at "${path}": ${first?.message}`);
}

/**
 * Compile-time proof that the schema still matches the hand-written contract.
 *
 * Without this, a field added to types.ts but not to the schema (or a widened
 * enum) would only be caught at runtime, on someone's screen. This makes it a
 * build error instead. It emits no JavaScript.
 */
type Extends<A extends B, B> = A;
export type _BundleMatchesContract = Extends<z.infer<typeof bundleSchema>, Bundle>;
