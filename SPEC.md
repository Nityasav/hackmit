# Sherlock specification

Read [the canonical product and implementation specification](schooltrace/spec.md) first.
It describes the current three-screen interface, 22-agent registry (one orchestrator,
four workers and 17 specialists), LangGraph execution, deterministic accounting,
document intake, extraction evaluation lifecycle and deployment boundaries.
It also covers the CFO/full-review interface, human continuation and revised tasks,
source withdrawal, live execution events, deterministic charts and PDF briefing export.

All four worker branches are wired. This is not a claim that all live model runs pass
an accuracy benchmark; see the canonical spec's verification and limitations sections.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before your first commit: what is stable, what is
being rewritten, and where the best parallel work is.

Read [PROJECT_TRACKER.md](PROJECT_TRACKER.md) for the latest verification and handoff.
Keep technical detail in the canonical spec so these entry points cannot diverge.
