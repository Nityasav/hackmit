"""The shared closing tool every agent role calls: record_decision.

The schema here is static and shared across roles — this is what fills the
Reasoning log (spec.md §8). The executable side is deliberately NOT a plain
function in a registry like ap_tools/ap_write_tools: filing a decision needs
run-specific context (run id, wall-clock timing, the gateway's own call log)
that the model must never supply itself. A model can't be trusted to report
its own tool calls accurately, and has no way to know real elapsed time.
run_loop.py builds a closure per run (see _bind_record_decision) that injects
those mechanical fields and only accepts the model's judgment fields below.
"""

from __future__ import annotations

from typing import Any

RECORD_DECISION_SPEC: dict[str, Any] = {
    "type": "function",
    "name": "record_decision",
    "description": "File this run's decision record, once, as your final step after you have finished "
    "investigating. The when/how fields (timing, the tool calls you actually made) are filled in "
    "automatically — you only supply the judgment below. This is what the human reads in the "
    "Reasoning log, so write it plainly and ground it in evidence you actually retrieved with a "
    "tool this run. Do not call this before you have investigated.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "One short phrase naming what you did."},
            "summary": {"type": "string", "description": "One or two sentence plain-language summary."},
            "why": {"type": "string", "description": "1-3 sentences grounded in evidence you cited."},
            "alternatives": {
                "type": "array",
                "description": "Options you considered, which you chose, and why each other one was rejected.",
                "items": {
                    "type": "object",
                    "properties": {
                        "option": {"type": "string"},
                        "reason": {"type": "string"},
                        "chosen": {"type": "boolean"},
                    },
                    "required": ["option", "reason", "chosen"],
                },
            },
            "memory_checks": {
                "type": "array",
                "description": "Each playbook/precedent applicability check and whether it passed. "
                "Empty array if none applied — do not invent one.",
                "items": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}, "ok": {"type": "boolean"}},
                    "required": ["text", "ok"],
                },
            },
            "outcome": {"type": "string", "description": "What actually resulted from this run."},
            "tags": {
                "type": "array",
                "description": "Optional short labels, e.g. a memory/playbook ID that was used.",
                "items": {"type": "string"},
            },
        },
        "required": ["action", "summary", "why", "alternatives", "memory_checks", "outcome"],
    },
}
