"""What an agent is allowed to return.

One result shape for the whole organization, because the agents genuinely do the same
thing: read scoped evidence, reach a bounded conclusion, cite what it rests on, and say
what a person still has to decide. A domain that needs more adds a field; it does not
add a schema.

Two absences are deliberate:

- **No confidence field.** A model's estimate of its own certainty is uncalibrated, and
  a number like "99.3%" reads as measurement when it is a guess. Confidence is computed
  from match features in `accounting/match.py` and attached by the runtime.
- **No amounts in prose.** `rationale` and `proposed_action` are validated to contain no
  digits or currency symbols. Every figure a person reads is inserted by the renderer
  from a deterministic calculation, so an agent cannot write a number into a report.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

#: Digits, currency symbols and percent signs. Dates are written as words in prose, or
#: cited through evidence, so excluding digits entirely costs nothing and removes the
#: whole class of "the model wrote a figure into the narrative".
_FIGURE = re.compile(r"[\d$€£%]")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")


class Citation(Contract):
    """Where a claim rests. Either a committed record or a span of an original file.

    `record_key` is the business key from `roles.key_of`, so a citation survives a
    re-import that changes row order, and points at the same economic thing.
    """

    role: str = Field(min_length=1, max_length=40)
    record_key: str = Field(default="", max_length=200)
    source_id: str = Field(default="", max_length=100)
    line: int | None = Field(default=None, ge=1)
    note: str = Field(default="", max_length=300)


class Exception_(Contract):
    """One thing that did not hold. `code` must be a condition the spec knows about."""

    code: str = Field(min_length=1, max_length=60)
    detail: str = Field(min_length=1, max_length=600)


class AgentResult(Contract):
    """The shape every agent returns."""

    summary: str = Field(min_length=1, max_length=600)
    disposition: Literal["clear", "exception", "insufficient_evidence"]
    rationale: str = Field(min_length=1, max_length=2000)
    citations: list[Citation] = Field(default_factory=list, max_length=24)
    exceptions: list[Exception_] = Field(default_factory=list, max_length=12)
    proposed_action: str = Field(default="No action proposed.", max_length=600)
    #: What the agent could not settle, and would need to.
    open_questions: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("rationale", "proposed_action")
    @classmethod
    def no_figures_in_prose(cls, value: str) -> str:
        if _FIGURE.search(value):
            raise ValueError(
                "Prose must not contain figures. Cite the calculation and let the "
                "renderer insert the authoritative number.")
        return value

    @field_validator("exceptions")
    @classmethod
    def exception_requires_a_finding(cls, value):
        return value

    def model_post_init(self, _context) -> None:
        # A disposition and its evidence have to agree. "Exception" with nothing named
        # is an accusation with no content; "clear" with exceptions listed is worse,
        # because it reads as a pass.
        if self.disposition == "exception" and not self.exceptions:
            raise ValueError("An exception disposition must name at least one exception.")
        if self.disposition == "clear" and self.exceptions:
            raise ValueError("A clear disposition cannot also list exceptions.")
        if self.disposition != "insufficient_evidence" and not self.citations:
            raise ValueError("A conclusion must cite the evidence it rests on.")


class APResult(AgentResult):
    """Accounts Payable adds what it decided about paying.

    `may_pay` is a recommendation only. Nothing an agent can call releases a payment;
    the runtime records the recommendation and, above the approval limit, routes it to
    a person regardless of what this says.
    """

    may_pay: bool = False
    matched_po: str = Field(default="", max_length=100)
    matched_receipt: str = Field(default="", max_length=100)


class ReviewVerdict(Contract):
    """An independent reviewer's answer. Separate from `AgentResult` on purpose: a
    reviewer does not restate the work, it accepts, rejects, or asks for more."""

    verdict: Literal["accept", "reject", "needs_evidence"]
    rationale: str = Field(min_length=1, max_length=1500)
    required_action: str = Field(default="", max_length=800)

    @field_validator("rationale", "required_action")
    @classmethod
    def no_figures_in_prose(cls, value: str) -> str:
        if _FIGURE.search(value):
            raise ValueError("Prose must not contain figures; cite the re-performed calculation.")
        return value


class Delegation(Contract):
    """One unit of work an orchestrator or worker hands down."""

    agent_id: str = Field(min_length=1, max_length=20)
    objective: str = Field(min_length=1, max_length=1000)
    #: The economic events this delegation is about, when it is about specific ones.
    event_ids: list[str] = Field(default_factory=list, max_length=50)
    record_keys: list[str] = Field(default_factory=list, max_length=50)


class Usage(Contract):
    """What one model call actually cost. Tokens are reported; cents are computed."""

    input_tokens: StrictInt = 0
    output_tokens: StrictInt = 0
    cost_cents: StrictInt = 0
