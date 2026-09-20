"use client";

import Link from "next/link";

import { AgentBoard } from "@/components/investigation/AgentBoard";
import { useData } from "@/lib/data";

/**
 * Agents: what the organization is doing, while it does it.
 *
 * The board was reachable only by scrolling past everything on Investigation, which
 * made the one screen that answers "what is happening right now" the hardest one to
 * reach. It is a destination of its own here, and it opens on the work.
 *
 * Every card is a row the runtime wrote as it worked. An agent that has not run shows
 * nothing rather than a placeholder.
 */
export default function AgentsPage() {
  const { ws } = useData();

  return (
    // Keyed on the workspace, so switching never leaves the previous one's board on
    // screen while the first poll for the new one is still in flight.
    <div key={ws} className="mx-auto max-w-7xl pb-16">
      <header className="mb-8">
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-ink-dim">Agents</p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
          What the organization is doing.
        </h1>
        <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-ink-dim">
          One card per task an agent was handed. Open one to see the steps it took, the evidence it read and what it
          concluded. Nothing here is estimated: a card moves because the run recorded that it moved.
        </p>
        <p className="mt-4 font-accent text-[14px] text-ink-dim">
          Start work from{" "}
          <Link href="/investigation" className="underline underline-offset-4">
            Investigation
          </Link>
          . Answer what stopped for a person there too.
        </p>
      </header>

      <AgentBoard ws={ws} />
    </div>
  );
}
