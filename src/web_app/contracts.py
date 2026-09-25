"""Web-facing DTOs for the AI Debate Harness MVP.

These models intentionally hide internal Patch/Selector structures from the browser.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


ClaimType = Literal["FACT", "DEFINITION", "CAUSE", "VALUE", "POLICY", "COMPARISON", "INTERPRETATION", "PERSONAL_DISPUTE", "INFORMATIONAL", "OTHER"]
EpistemicStatus = Literal["NON_FACTUAL", "OPEN_EMPIRICAL", "GENUINELY_CONTESTED", "WEIGHT_DOMINANT_TRUE", "WEIGHT_DOMINANT_FALSE", "FORMALLY_SETTLED", "UNKNOWN"]
TreatmentMode = Literal["NATURAL_DEBATE", "PLAYFUL_DEBATE", "REFRAMED_DEBATE"]
InteractionState = Literal["READY", "CONFIRMATION_REQUIRED", "CONTEXT_REQUIRED", "INFORMATIONAL_FIRST"]
TruthMode = Literal["REAL_WORLD", "STIPULATED_COUNTERFACTUAL", "RHETORICAL_PLAY"]
Phase = Literal["OPENING", "CROSSFIRE", "AUDIENCE_RESPONSE", "REBUTTAL", "FINAL_FOCUS", "COMPLETE"]


class AnalyzeTopicRequest(StrictModel):
    topic: str = Field(min_length=1, max_length=2000)

    @field_validator("topic")
    @classmethod
    def strip_topic(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("topic must not be blank")
        return value


class TopicAnalysis(StrictModel):
    original_topic: str
    claim_type: ClaimType
    epistemic_status: EpistemicStatus
    treatment_mode: TreatmentMode
    interaction_state: InteractionState
    normalized_motion: str
    side_labels: tuple[str, str]
    context_required: bool = False
    confirmation_reason: str | None = None
    fact_anchor: str | None = None
    truth_mode: TruthMode = "REAL_WORLD"
    tone_hint: Literal["SERIOUS", "PLAYFUL"] | None = None


class ContextAnswer(StrictModel):
    question_id: str
    answer: str = Field(min_length=1, max_length=1000)


class ContextQuestion(StrictModel):
    id: str
    text: str
    options: list[str]
    allow_unknown: bool = True
    allow_free_text: bool = True


class ContextStepRequest(StrictModel):
    topic: str = Field(min_length=1, max_length=2000)
    answers: list[ContextAnswer] = Field(default_factory=list)


class ContextStepResponse(StrictModel):
    context_completeness: int = Field(ge=0, le=100)
    debate_ready: bool
    question: ContextQuestion | None = None
    context_summary: dict[str, list[str]] | None = None


class CreateMotionRequest(StrictModel):
    analysis: TopicAnalysis
    context_summary: dict[str, list[str]] | None = None
    edited_motion: str | None = Field(default=None, max_length=1200)
    edit_count: int = Field(default=0, ge=0, le=1)

    @field_validator("edited_motion")
    @classmethod
    def normalize_edit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("edited_motion must not be blank")
        return value


class MotionNormalizationDraft(StrictModel):
    motion: str = Field(min_length=1, max_length=1200)
    side_labels: tuple[str, str]


class MotionResponse(StrictModel):
    motion: str
    side_labels: tuple[str, str]
    personas: tuple[str, str]
    tone: Literal["SERIOUS", "PLAYFUL"]
    edit_count: int = Field(ge=0, le=1)
    context_summary: dict[str, list[str]] | None = None
    fact_anchor: str | None = None
    truth_mode: TruthMode = "REAL_WORLD"


class TranscriptItem(StrictModel):
    turn: int
    phase: Phase
    speaker: Literal["A", "B"]
    side_label: str
    utterance: str


class DebateSession(StrictModel):
    motion: str
    side_labels: tuple[str, str]
    personas: tuple[str, str]
    tone: Literal["SERIOUS", "PLAYFUL"]
    context_summary: dict[str, list[str]] | None = None
    fact_anchor: str | None = None
    truth_mode: TruthMode = "REAL_WORLD"
    next_index: int = 0
    transcript: list[TranscriptItem] = Field(default_factory=list)
    audience_status: Literal["PENDING", "ASKED", "SKIPPED", "DONE"] = "PENDING"
    audience_question: str | None = None
    audience_response_index: int = 0
    completed: bool = False
    engine_token: str | None = None


class DebateStepRequest(StrictModel):
    session: DebateSession
    command: Literal["NEXT", "AUDIENCE_QUESTION", "SKIP_AUDIENCE"] = "NEXT"
    audience_question: str | None = Field(default=None, max_length=500)

    @field_validator("audience_question")
    @classmethod
    def strip_audience_question(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("audience_question must not be blank")
        return value


class DebateStepResponse(StrictModel):
    session: DebateSession
    phase: Phase
    speaker: Literal["A", "B"] | None = None
    side_label: str | None = None
    utterance: str | None = None
    awaiting_audience_question: bool = False
    completed: bool = False
    turn_task: str | None = None
    moderator_decision: str | None = None


class NeutralSummaryRequest(StrictModel):
    motion: str = Field(min_length=1, max_length=1200)
    transcript: list[TranscriptItem] = Field(default_factory=list)


class NeutralSummaryResponse(StrictModel):
    key_clashes: list[str]
    side_a_strong_points: list[str]
    side_b_strong_points: list[str]
    agreements: list[str]
    unresolved: list[str]
