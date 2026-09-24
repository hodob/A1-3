"""Human annotation decision rule for question response status."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResponseLabel(StrEnum):
    DIRECT = "DIRECT"
    QUALIFIED = "QUALIFIED"
    PARTIAL = "PARTIAL"
    EVADED = "EVADED"
    FRAME_REJECTED_VALID = "FRAME_REJECTED_VALID"
    UNCLEAR = "UNCLEAR"


class ResponseEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core_answered: bool | None
    scope_restricted: bool | None = None
    requested_parts: int = Field(default=1, ge=1)
    resolved_parts: int = Field(default=0, ge=0)
    frame_rejected: bool = False
    premise_conflicts_state: bool | None = None
    on_topic: bool | None = None

    @model_validator(mode="after")
    def check_counts(self):
        if self.resolved_parts > self.requested_parts:
            raise ValueError("resolved_parts exceeds requested_parts")
        return self


def classify_response(evidence: ResponseEvidence) -> ResponseLabel:
    if evidence.frame_rejected:
        if evidence.premise_conflicts_state is True:
            return ResponseLabel.FRAME_REJECTED_VALID
        return ResponseLabel.UNCLEAR
    if evidence.resolved_parts > 0 and evidence.resolved_parts < evidence.requested_parts:
        return ResponseLabel.PARTIAL
    if evidence.core_answered is None:
        return ResponseLabel.UNCLEAR
    if evidence.core_answered is False:
        if evidence.on_topic is False:
            return ResponseLabel.EVADED
        return ResponseLabel.UNCLEAR
    if evidence.resolved_parts < evidence.requested_parts:
        return ResponseLabel.PARTIAL
    if evidence.scope_restricted is None:
        return ResponseLabel.UNCLEAR
    return ResponseLabel.QUALIFIED if evidence.scope_restricted else ResponseLabel.DIRECT
