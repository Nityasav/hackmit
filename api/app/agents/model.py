"""Structured-output model adapter for specialist agents.

Specialists are separate model callers from the CFO coordinator, so they carry
their own budget: `app/cfo/README.md` makes each specialist adapter responsible
for enforcing its own model limits and cooperating with cancellation. Credential
selection is shared with the coordinator (`cfo.model.build_client`) so there is
exactly one implementation of "never forward the hosted key to a local host".

Every call requests a typed schema and refuses anything else. A refusal, a
truncation or an unparseable response raises, and the caller fails the task
closed rather than presenting an unverified conclusion.
"""

from __future__ import annotations

import os

from ..cfo.model import build_client

MAX_OUTPUT_TOKENS = 2048
# A specialist may reason across several bounded steps, never unbounded.
DEFAULT_MODEL_CALLS = 4


class ModelBudgetExceeded(RuntimeError):
    """The specialist used its own model-call allowance for one task."""


class SpecialistRefusal(RuntimeError):
    """The provider refused, truncated, or returned unusable structured output."""


class StructuredSpecialistModel:
    """One bounded structured-output caller, shared by a specialist's steps."""

    def __init__(self, provider: str, model: str, client, max_calls: int = DEFAULT_MODEL_CALLS):
        self.provider, self.model, self.client = provider, model, client
        self.label = f"{provider}/{model}"
        self.max_calls = max_calls
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    @classmethod
    def from_env(cls, max_calls: int = DEFAULT_MODEL_CALLS):
        """Specialist settings fall back to the coordinator's, so one key configures both."""
        provider = os.getenv("SPECIALIST_PROVIDER") or os.getenv("CFO_PROVIDER", "openai")
        model = os.getenv("SPECIALIST_MODEL") or os.getenv("CFO_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-5.4-mini"
        if not model:
            raise ValueError("Set SPECIALIST_MODEL (or CFO_MODEL) to an available structured-output model ID.")
        if provider not in {"openai", "local"}:
            raise ValueError("SPECIALIST_PROVIDER must be openai or local.")
        local_url = os.getenv("SPECIALIST_LOCAL_BASE_URL") or os.getenv("CFO_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1")
        return cls(provider, model, build_client(provider, local_url), max_calls)

    def reset(self) -> None:
        """Start a fresh per-task allowance; accumulated token usage is kept."""
        self.calls = 0

    async def generate(self, system: str, instruction: str, payload: dict, schema):
        if self.calls >= self.max_calls:
            raise ModelBudgetExceeded("Specialist model call budget exhausted for this task.")
        self.calls += 1
        import json

        content = json.dumps(payload, ensure_ascii=False)
        if len(content) > 60000:
            raise SpecialistRefusal("Specialist context exceeds the bounded limit; narrow the task scope.")
        messages = [{"role": "system", "content": system + "\n" + instruction},
                    {"role": "user", "content": content}]
        if self.provider == "openai":
            response = await self.client.responses.parse(
                model=self.model, input=messages, text_format=schema,
                max_output_tokens=MAX_OUTPUT_TOKENS, store=False,
            )
            if response.usage:
                self.input_tokens += response.usage.input_tokens
                self.output_tokens += response.usage.output_tokens
            if response.output_parsed is None:
                raise SpecialistRefusal("Model refused or returned incomplete structured output.")
            return schema.model_validate(response.output_parsed)
        response = await self.client.chat.completions.create(
            model=self.model, messages=messages, max_tokens=MAX_OUTPUT_TOKENS,
            response_format={"type": "json_schema", "json_schema": {
                "name": schema.__name__, "schema": schema.model_json_schema(), "strict": True,
            }},
        )
        choice = response.choices[0]
        if response.usage:
            self.input_tokens += response.usage.prompt_tokens
            self.output_tokens += response.usage.completion_tokens
        if choice.finish_reason != "stop" or not choice.message.content:
            raise SpecialistRefusal("Local model returned incomplete structured output.")
        return schema.model_validate_json(choice.message.content)

    async def close(self):
        await self.client.close()
