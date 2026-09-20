"use client";

import { useState } from "react";
import type { Decision } from "@/lib/types";
import { AGENT_NAME, AgentAvatar } from "@/components/ui";

export function DecisionCard({ decision, defaultOpen = false }: { decision: Decision; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const d = decision;

  return (
    <div
      className={`mb-1.5 grid grid-cols-[44px_24px_1fr] gap-2 rounded-lg border bg-surface p-2.5 transition ${
        open ? "border-accent-good shadow-[0_4px_14px_rgba(15,118,110,0.10)]" : "border-line hover:border-ink"
      }`}
    >
      <span className="pt-1 font-mono text-[12.5px] text-ink-faint">{d.time}</span>
      {/* A human decision must not wear an agent's badge; `agent` only groups it with its run. */}
      {d.actor ? (
        <span
          title={d.actor}
          className="inline-flex h-6 w-6 flex-none items-center justify-center rounded-none border border-ink bg-surface text-[11px] font-bold text-ink"
        >
          YOU
        </span>
      ) : (
        <AgentAvatar id={d.agent} />
      )}
      <div className="min-w-0">
        <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full cursor-pointer items-start gap-2 text-left">
          <span className="min-w-0">
            <span className="block text-[14px] font-semibold">{d.action}</span>
            <span className="block text-[13.5px] text-ink-dim">
              <b className="font-semibold text-ink">Why:</b> {d.summary}
            </span>
          </span>
          {!open && <span className="ml-auto flex-none text-[12px] text-ink-faint">details</span>}
          <span className={`flex-none pt-0.5 text-[13px] transition-transform ${open ? "rotate-90 text-ink" : "text-ink-faint"}`}>
            ▶
          </span>
        </button>

        <div className="mt-1.5 flex flex-wrap gap-2">
          <Tag>{d.actor ? `Human · ${d.actor}` : AGENT_NAME[d.agent]}</Tag>
          {d.tags.map((t) => (
            <Tag key={t.label} kind={t.kind}>
              {t.label}
            </Tag>
          ))}
        </div>

        {open && (
          <div className="mt-4 grid gap-2 border-t border-dashed border-line pt-2.5 md:grid-cols-2">
            <Box title="🕒 When">
              <dl className="grid grid-cols-[78px_1fr] gap-x-2 gap-y-0.5">
                <Kv k="Run" v={d.when.run} />
                <Kv k="Step" v={d.when.step} />
                <Kv k="Started" v={d.when.started} />
                <Kv k="Finished" v={d.when.finished} />
                <Kv k="Trigger" v={d.when.trigger} />
              </dl>
            </Box>

            <Box title="🛠 How: tools it called">
              {d.how.map((h, i) => (
                <div key={i} className="grid grid-cols-[18px_1fr] gap-2 py-0.5">
                  <span className="mt-px flex h-4 w-4 items-center justify-center rounded-none bg-surface-3 text-[11px] font-bold text-ink-dim">
                    {i + 1}
                  </span>
                  <span>
                    <code className="rounded border border-line bg-surface px-1 font-mono text-[12.5px]">
                      {h.tool}({h.input})
                    </code>{" "}
                    <span className="text-ink-dim">→ {h.output}</span>
                  </span>
                </div>
              ))}
            </Box>

            <Box title="💡 Why it did it">{d.why}</Box>

            <Box title="⚖️ Why this over the alternatives">
              {d.alternatives.map((a) => (
                <div key={a.option} className="grid grid-cols-[16px_1fr] gap-2 py-0.5">
                  <span className={`font-bold ${a.chosen ? "text-ink" : "text-accent-bad"}`}>{a.chosen ? "✓" : "✗"}</span>
                  <span>
                    <b className="font-semibold">{a.option}</b>: {a.reason}
                  </span>
                </div>
              ))}
            </Box>

            {d.memory_checks.length > 0 && (
              <Box title="🧠 Memory checks">
                {d.memory_checks.map((m) => (
                  <div key={m.text} className="flex gap-2 py-0.5">
                    <span className={`font-bold ${m.ok ? "text-ink" : "text-accent-bad"}`}>{m.ok ? "✓" : "✗"}</span>
                    {m.text}
                  </div>
                ))}
              </Box>
            )}

            <Box title="➡️ Outcome" wide={d.memory_checks.length === 0}>
              {d.outcome}
            </Box>

            <div className="text-[12px] text-ink-faint md:col-span-2">
              Structured decision record the agent emits with each action (not raw chain-of-thought). Amounts come from
              the calculation engine.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Box({ title, children, wide }: { title: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className={`rounded-lg border border-line bg-surface-2 px-2.5 py-2 text-[13.5px] text-ink-dim ${wide ? "md:col-span-2" : ""}`}>
      <h6 className="mb-1.5 text-[12px] font-bold uppercase tracking-wider text-ink">{title}</h6>
      {children}
    </div>
  );
}

function Kv({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt className="text-ink-faint">{k}</dt>
      <dd>{v}</dd>
    </>
  );
}

function Tag({ children, kind }: { children: React.ReactNode; kind?: "mem" | "memx" }) {
  const tone = kind === "mem" ? "bg-surface-2 text-ink-dim" : kind === "memx" ? "bg-red-100 text-accent-bad" : "bg-surface-2 text-ink-dim";
  return <span className={`rounded px-1.5 py-px font-mono text-[12px] ${tone}`}>{children}</span>;
}
