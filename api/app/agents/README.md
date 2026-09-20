# Agents

- `cfo.py` is the first live slice: OpenAI Responses API, immutable-snapshot scope, bounded read-only
  evidence tools, strict structured submission, citation verification and persisted telemetry.
- The remaining specialists, independent Auditor, resumable orchestrator and replay adapter are planned.
- Keep this folder flat until a second implementation creates a real shared abstraction.

Runs store concise decisions and tool metadata, never private chain-of-thought. The local extraction model
and its gated offline improvement loop are specified for a later implementation.
