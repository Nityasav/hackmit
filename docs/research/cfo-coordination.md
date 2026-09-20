# Research behind Sherlock's CFO coordinator

Research reviewed September 19, 2026. These sources motivate design choices;
their benchmark results are not Sherlock's measured results.

## References and implementation choices

| Source | Relevant result or pattern | Sherlock application |
| --- | --- | --- |
| Anthropic, [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), December 2024 | Orchestrator-workers decomposes and delegates work; evaluator-optimizer uses feedback to improve a result. The article recommends simple, composable implementations. | CFO plans a task DAG; specialist results pass independent auditor review; a rejected claim receives a bounded follow-up. Implemented directly in Python, without a required agent framework. |
| Anthropic, [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system), June 2025 | Lead-agent planning, focused subagent assignments, and independent parallel exploration can help breadth-first research. Coordination and token costs are substantial. | Delegate only independent tasks, cap concurrency at two, pass scoped inventories and dependency results rather than broadcasting full conversations. This is an engineering case study, not a financial-controls benchmark. |
| Wu et al., [AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation](https://arxiv.org/abs/2308.08155v2), 2023 | Customizable agents combine models, tools, and human input through programmable interaction patterns. | Typed specialist and auditor interfaces, explicit handoffs, and a separate human approval boundary. We reference the pattern; we do not claim to use the AutoGen library. |
| Kim et al., [Towards a Science of Scaling Agent Systems](https://arxiv.org/abs/2512.08296v3), revised April 2026 | Controlled comparisons find that architecture-task fit matters: decomposable work can benefit, sequential planning can degrade, and coordination adds overhead. Central verification can reduce error propagation. | Small task plans, explicit dependencies, centralized validation, independent review, and bounded execution instead of an unrestricted group conversation. The cited version is v3; older versions report different experimental counts. |
| Żywot et al., [Can Small Agents Collaborate to Beat a Single Large Language Model?](https://arxiv.org/abs/2601.11327v2), revised April 2026 | Their tool-intensive benchmark results emphasize orchestrator capacity and reasoning; additional reasoning in workers offers limited or negative benefits in their setup. | Spend initial model capability on the CFO, evaluate smaller specialist/planner alternatives empirically, and avoid assuming that adding more small models improves results. This does not establish a particular model as best for Sherlock. |

## OpenAI versus local Qwen

Recommendation: start the CFO on an available OpenAI structured-output model; retain a
local Qwen adapter for controlled comparison. This is an engineering judgment based
on integration effort and the importance of planning, not a measured model ranking.
We have not established the laptop's hardware capacity or benchmarked a Qwen size.

The hosted adapter uses the [OpenAI Responses structured-output interface](https://developers.openai.com/api/docs/guides/structured-outputs).
The local adapter uses JSON-schema responses via an OpenAI-compatible loopback server;
[Ollama documents structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
[Qwen-Agent](https://qwenlm.github.io/Qwen-Agent/en/guide/) is another potential implementation
for Linda's specialists, but is not a dependency of the CFO.

Schema validation constrains structure. It does not establish factual correctness.
The CFO additionally validates authorized IDs, dependency graphs, actual evidence-tool
calls, independently repeated calculation results, and report citation membership.

## Presentation wording

> Sherlock uses a research-informed orchestrator-worker architecture. The CFO
> delegates bounded financial investigations, an independent auditor checks original
> evidence and calculations, and the CFO follows up on rejected claims. Deterministic
> software enforces scope, budgets, and the human approval boundary.

> We optimize coordination by giving each specialist a focused task and evidence
> scope, running only independent tasks concurrently, and keeping unresolved findings
> visible. Our current tests validate those controls; model-quality and efficiency
> claims require a separate measured evaluation.

## Experiments to run before claiming efficiency

Use identical snapshots and issue sets. Keep model IDs, prompts, tool definitions,
sampling settings, and budgets recorded. Evaluate multiple runs and report sample sizes.

1. Single agent versus CFO + specialists, with comparable total token budgets.
2. Sequential versus two-way parallel execution, with identical tasks and models.
3. Hosted CFO versus local Qwen CFO, keeping specialists and evidence fixed.
4. Reviewer gate enabled versus disabled, on missing evidence and conflicting claims.

Measure supported-finding precision/recall, unsupported conclusions, evidence-request
accuracy, successful completion, time, input/output tokens, tool calls, and inference
cost (or local compute/energy separately). A cheaper run that misses the planted issue
is not an efficiency win. The current scripted tests do not measure these outcomes for
real models, and the UI fixture's learning figures must remain labeled examples.

## Implemented versus future work

Implemented: model planning and synthesis adapters, task DAG validation, bounded
parallel scheduler, scoped evidence tools, independent reviewer gate, limited follow-up,
conflict handling, durable checkpoints, reports, API, and a separate CFO inspection page.

Integration pending: Linda's real specialist/auditor agents and Maxim's real records
and calculation adapters. Automatic resume across new evidence, global specialist
token/cost accounting, authenticated human approval, and playbook learning are separate
features; this CFO package does not claim to implement them.
