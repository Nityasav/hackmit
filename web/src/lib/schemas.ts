import { z } from "zod";

import type { Bundle } from "@/lib/types";

/**
 * Runtime shape of the bundle.
 *
 * get_bundle() returns jsonb, which arrives as `any`. Casting it to Bundle
 * only silences the compiler — a schema drift would surface later as a blank
 * panel or a crash deep in a component. Parsing here fails at the boundary,
 * where the message can say what is actually wrong.
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

export const agentIdSchema = z.enum(["cfo", "ap", "py", "gr", "au"]);

export const tabIdSchema = z.enum([
  "command", "board", "workflows", "findings", "approvals", "reports", "reasoning", "learning",
]);

export const toneSchema = z.enum(["good", "warn", "neutral"]);

export const workspaceSchema = z.object({
  id: z.string(),
  name: z.string(),
  kind: z.enum(["synthetic", "public"]),
  period: z.string(),
  mode: z.enum(["live", "recorded", "scripted", "not_started"]),
  snapshot_id: z.string(),
  disabled_tabs: z.array(tabIdSchema),
  model: z.string(),
  run_budget: z.object({ used: z.number(), total: z.number() }),
  source_url: z.string().optional(),
  intake: z.boolean().optional(),
  currency: z.string().optional(),
  profile: z.string().optional(),
});

export const agentSchema = z.object({
  id: agentIdSchema,
  name: z.string(),
  short: z.string(),
  role: z.string(),
  status: z.enum(["working", "waiting", "idle"]),
  doing: z.string(),
});

export const briefingSchema = z.object({
  generated_at: z.string(),
  text: z.string(),
  actions: z.array(z.object({
    label: z.string(),
    href: tabIdSchema,
    primary: z.boolean().optional(),
  })),
});

export const kpiSchema = z.object({
  label: z.string(),
  value: z.string(),
  note: z.string(),
  tone: toneSchema.optional(),
});

export const workflowSchema = z.object({
  id: z.string(),
  name: z.string(),
  owner: agentIdSchema,
  progress: z.number(),
  stages: z.array(z.object({
    name: z.string(),
    state: z.enum(["done", "running", "human", "todo"]),
  })),
});

export const taskSchema = z.object({
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
    detail: z.string().optional(),
    state: z.enum(["done", "running", "todo"]),
    memory: z.boolean().optional(),
  })),
  todos: z.array(z.string()),
  note: z.string().optional(),
  note_tone: z.enum(["warn", "info"]).optional(),
  approval_id: z.string().optional(),
});

export const evidenceNodeSchema = z.object({
  label: z.string(),
  kind: z.enum(["record", "award", "doc", "calc", "page"]),
  tone: z.enum(["neutral", "bad", "good"]),
  edge: z.string().optional(),
  locator: z.string().optional(),
  source_preview: z.string().optional(),
});

export const findingSchema = z.object({
  id: z.string(),
  agent: agentIdSchema,
  title: z.string(),
  summary: z.string(),
  status: z.enum([
    "hypothesized", "substantiated", "cleared", "explained",
    "needs_evidence", "none_reported", "ties",
  ]),
  amount_cents: z.number().nullable(),
  amount_note: z.string().optional(),
  verified_by: agentIdSchema.optional(),
  evidence: z.array(evidenceNodeSchema),
});

export const approvalSchema = z.object({
  id: z.string(),
  agent: agentIdSchema,
  kind: z.enum(["journal", "payment", "playbook", "evidence"]),
  title: z.string(),
  summary: z.string(),
  verified: z.boolean(),
  status: z.enum(["pending", "approved", "rejected"]),
  journal: optional(z.array(z.object({
    account: z.string(),
    fund: z.string(),
    debit_cents: z.number(),
    credit_cents: z.number(),
  }))),
  effects: optional(z.array(z.object({
    label: z.string(),
    value: z.string(),
    // Narrower than toneSchema on purpose: an approval effect is never a warning.
    tone: z.enum(["good", "neutral"]).optional(),
  }))),
});

export const decisionSchema = z.object({
  id: z.string(),
  run: z.string(),
  time: z.string(),
  agent: agentIdSchema,
  action: z.string(),
  summary: z.string(),
  tags: z.array(z.object({ label: z.string(), kind: z.enum(["mem", "memx"]).optional() })),
  when: z.object({
    run: z.string(), step: z.string(), started: z.string(),
    finished: z.string(), trigger: z.string(),
  }),
  how: z.array(z.object({ tool: z.string(), input: z.string(), output: z.string() })),
  why: z.string(),
  alternatives: z.array(z.object({ option: z.string(), reason: z.string(), chosen: z.boolean() })),
  memory_checks: z.array(z.object({ text: z.string(), ok: z.boolean() })),
  outcome: z.string(),
});

export const playbookSchema = z.object({
  id: z.string(),
  title: z.string(),
  source: z.string(),
  proposed_by: agentIdSchema,
  replay: z.object({
    passed: z.boolean(),
    new_false_positives: z.number(),
    months: z.array(z.string()),
  }),
  uses: z.string(),
  status: z.enum(["active", "needs_approval", "retired", "blocked"]),
  status_note: z.string().optional(),
});

export const bundleSchema = z.object({
  contract_version: z.number().optional(),
  workspace: workspaceSchema,
  agents: z.array(agentSchema),
  briefing: briefingSchema,
  kpis: z.array(kpiSchema),
  workflows: z.array(workflowSchema),
  tasks: z.array(taskSchema),
  findings: z.array(findingSchema),
  approvals: z.array(approvalSchema),
  decisions: z.array(decisionSchema),
  playbooks: z.array(playbookSchema),
  ablation: z.object({
    example: z.boolean(),
    rows: z.array(z.object({ metric: z.string(), without: z.number(), with: z.number() })),
    note: z.string(),
  }).nullable(),
  report: z.object({
    title: z.string(),
    sections: z.array(z.string()),
    comparisons: z.array(z.object({ label: z.string(), before: z.string(), after: z.string() })),
    applies_approval: z.string().optional(),
    before_label: z.string().optional(),
    after_label: z.string().optional(),
  }),
});

export const workspaceSummarySchema = z.object({
  id: z.string(),
  name: z.string(),
  kind: z.enum(["synthetic", "public"]),
  intake: optional(z.boolean()),
});

export const workspaceSummaryListSchema = z.array(workspaceSummarySchema);

export const starterPackSchema = z.object({
  name: z.string(),
  start: z.string(),
  end: z.string(),
  files: z.array(z.object({
    name: z.string(),
    role: z.string(),
    content: z.string(),
    later: optional(z.boolean()),
  })),
});

export type ParsedBundle = z.infer<typeof bundleSchema>;
export type WorkspaceSummary = z.infer<typeof workspaceSummarySchema>;
export type StarterPack = z.infer<typeof starterPackSchema>;

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
