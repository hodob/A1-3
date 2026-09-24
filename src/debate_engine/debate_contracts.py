"""Typed, atomic Debate State patch contract.

LLM output is untrusted. Pydantic checks shape and ID namespaces; apply_patch
checks existence and ownership on a deep copy before returning a new state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Callable, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator


PropositionId = Annotated[str, StringConstraints(pattern=r"^C[1-9][0-9]*$")]
PatchPropositionId = Annotated[str, StringConstraints(pattern=r"^P[1-9][0-9]*$")]
PropositionRef = Annotated[str, StringConstraints(pattern=r"^(?:C|P)[1-9][0-9]*$")]
QuestionId = Annotated[str, StringConstraints(pattern=r"^Q[1-9][0-9]*$")]
RelationId = Annotated[str, StringConstraints(pattern=r"^R[1-9][0-9]*$")]
RelationType = Literal["SUPPORTS", "ATTACKS", "CONTRADICTS", "QUALIFIES"]
ResponseStatus = Literal["DIRECT", "QUALIFIED", "PARTIAL", "EVADED", "FRAME_REJECTED_VALID", "UNCLEAR"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddProposition(StrictModel):
    op: Literal["ADD_PROPOSITION"]
    temp_id: PatchPropositionId | None = None
    text: str = Field(min_length=1)


class AddRelation(StrictModel):
    op: Literal["ADD_RELATION"]
    from_proposition_ref: PropositionRef
    to_proposition_ref: PropositionRef
    relation_type: RelationType

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_existing_state_ids(cls, value):
        """Read old saved fixtures while exposing only ref fields in new schema."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for old, new in (("from_proposition_id", "from_proposition_ref"), ("to_proposition_id", "to_proposition_ref")):
            if old in data:
                if new in data:
                    raise ValueError(f"Use {new}, not both legacy and ref fields")
                data[new] = data.pop(old)
        return data


class AskQuestion(StrictModel):
    op: Literal["ASK_QUESTION"]
    text: str | None = Field(default=None, min_length=1)
    core_proposition: str = Field(min_length=1)
    target_proposition_id: PropositionId | None = None


class AnswerQuestion(StrictModel):
    op: Literal["ANSWER_QUESTION"]
    question_id: QuestionId
    response_status: ResponseStatus
    resolution: Literal["OPEN", "RESOLVED"]


class ReviseProposition(StrictModel):
    op: Literal["REVISE_PROPOSITION"]
    old_proposition_id: PropositionId
    new_proposition_text: str = Field(min_length=1)


class ConcedeLocal(StrictModel):
    op: Literal["CONCEDE_LOCAL"]
    proposition_id: PropositionId


class WithdrawProposition(StrictModel):
    op: Literal["WITHDRAW_PROPOSITION"]
    proposition_id: PropositionId


PatchOperation = Annotated[
    Union[AddProposition, AddRelation, AskQuestion, AnswerQuestion, ReviseProposition, ConcedeLocal, WithdrawProposition],
    Field(discriminator="op"),
]


class PatchEnvelope(StrictModel):
    operations: list[PatchOperation]


class Proposition(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: PropositionId
    text: str
    speaker: str
    turn: int


class Relation(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: RelationId
    from_proposition_id: PropositionId
    to_proposition_id: PropositionId
    relation_type: RelationType


class Question(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: QuestionId
    asker: str
    text: str
    core_proposition: str
    target_proposition_id: PropositionId | None
    response_status: ResponseStatus = "UNCLEAR"
    resolution: Literal["OPEN", "RESOLVED"] = "OPEN"
    turn: int
    source_turn_id: int


class CommitmentEvent(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    event: Literal["ASSERT", "CONCEDE", "WITHDRAW", "REVISE"]
    speaker: str
    proposition_id: PropositionId
    old_proposition_id: PropositionId | None = None
    new_proposition_id: PropositionId | None = None
    turn: int


class DebateState(StrictModel):
    propositions: list[Proposition] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    commitment_events: list[CommitmentEvent] = Field(default_factory=list)
    question_response_events: list[dict] = Field(default_factory=list)
    event_log: list[dict] = Field(default_factory=list)


@dataclass(frozen=True)
class PatchIssue:
    code: str
    field: str
    message: str
    op_index: int | None = None
    reference: str | None = None

    def as_dict(self) -> dict:
        return {"code": self.code, "field": self.field, "message": self.message, "op_index": self.op_index, "reference": self.reference}


class PatchValidationError(ValueError):
    def __init__(self, issues: list[PatchIssue]):
        self.issues = issues
        super().__init__("; ".join(f"{issue.code}:{issue.field}:{issue.reference or ''}" for issue in issues))


@dataclass(frozen=True)
class PatchResult:
    applied: bool
    state: DebateState
    attempts: int
    issues: tuple[PatchIssue, ...] = ()


def _schema_issues(error: ValidationError) -> list[PatchIssue]:
    issues = []
    for item in error.errors(include_url=False):
        loc = item["loc"]
        field = ".".join(str(part) for part in loc)
        value = item.get("input")
        leaf = next((part for part in reversed(loc) if isinstance(part, str)), "")
        prefix = "Q" if leaf == "question_id" else "C" if leaf.endswith("proposition_id") or leaf == "proposition_id" or leaf.endswith("proposition_ref") else None
        wrong_namespace = prefix and isinstance(value, str) and len(value) > 1 and value[0] in "CQR" and value[0] != prefix
        issues.append(PatchIssue("invalid_reference_type" if wrong_namespace else "invalid_schema", field, item["msg"], next((part for part in loc if isinstance(part, int)), None), value if isinstance(value, str) else None))
    return issues


def parse_patch(raw: dict | PatchEnvelope) -> PatchEnvelope:
    try:
        return raw if isinstance(raw, PatchEnvelope) else PatchEnvelope.model_validate(raw)
    except ValidationError as exc:
        raise PatchValidationError(_schema_issues(exc)) from exc


def _require(mapping: dict, reference: str, field: str, index: int) -> object:
    if reference not in mapping:
        raise PatchValidationError([PatchIssue("missing_entity", field, "Reference does not exist", index, reference)])
    return mapping[reference]


def apply_patch(state: DebateState, raw_patch: dict | PatchEnvelope, *, speaker: str, turn: int) -> DebateState:
    patch = parse_patch(raw_patch)
    next_state = state.model_copy(deep=True)
    propositions = {item.id: item for item in next_state.propositions}
    original_propositions = dict(propositions)
    questions = {item.id: item for item in next_state.questions}
    planned_propositions: dict[int, Proposition] = {}
    temp_propositions: dict[str, Proposition] = {}
    next_number = len(next_state.propositions) + 1
    for index, operation in enumerate(patch.operations):
        if not isinstance(operation, AddProposition):
            continue
        node = Proposition(id=f"C{next_number}", text=operation.text, speaker=speaker, turn=turn)
        next_number += 1
        planned_propositions[index] = node
        if operation.temp_id:
            if operation.temp_id in temp_propositions:
                raise PatchValidationError([PatchIssue("duplicate_temp_id", "temp_id", "Patch-local ID must be unique", index, operation.temp_id)])
            temp_propositions[operation.temp_id] = node

    def resolve_proposition_ref(reference: str, field: str, index: int) -> Proposition:
        if reference.startswith("P"):
            if reference not in temp_propositions:
                raise PatchValidationError([PatchIssue("missing_temp_reference", field, "Patch-local Proposition does not exist", index, reference)])
            return temp_propositions[reference]
        if reference not in original_propositions:
            raise PatchValidationError([PatchIssue("missing_entity", field, "Existing State Proposition does not exist", index, reference)])
        return original_propositions[reference]

    relation_keys = {(r.from_proposition_id, r.to_proposition_id, r.relation_type) for r in next_state.relations}
    for index, operation in enumerate(patch.operations):
        if isinstance(operation, AddProposition):
            node = planned_propositions[index]
            next_state.propositions.append(node)
            propositions[node.id] = node
            next_state.commitment_events.append(CommitmentEvent(event="ASSERT", speaker=speaker, proposition_id=node.id, turn=turn))
        elif isinstance(operation, AddRelation):
            source = resolve_proposition_ref(operation.from_proposition_ref, "from_proposition_ref", index)
            target = resolve_proposition_ref(operation.to_proposition_ref, "to_proposition_ref", index)
            key = (source.id, target.id, operation.relation_type)
            if key in relation_keys:
                continue
            next_state.relations.append(Relation(id=f"R{len(next_state.relations) + 1}", from_proposition_id=source.id, to_proposition_id=target.id, relation_type=operation.relation_type))
            relation_keys.add(key)
        elif isinstance(operation, AskQuestion):
            if operation.target_proposition_id:
                _require(propositions, operation.target_proposition_id, "target_proposition_id", index)
            question = Question(id=f"Q{len(next_state.questions) + 1}", asker=speaker, text=operation.text or operation.core_proposition, core_proposition=operation.core_proposition, target_proposition_id=operation.target_proposition_id, turn=turn, source_turn_id=turn)
            next_state.questions.append(question)
            questions[question.id] = question
        elif isinstance(operation, AnswerQuestion):
            prior = _require(questions, operation.question_id, "question_id", index)
            if prior.asker == speaker:
                raise PatchValidationError([PatchIssue("invalid_owner", "question_id", "Asker cannot answer own question", index, operation.question_id)])
            updated = prior.model_copy(update={"response_status": operation.response_status, "resolution": operation.resolution})
            next_state.questions = [updated if q.id == prior.id else q for q in next_state.questions]
            questions[prior.id] = updated
            next_state.question_response_events.append({"question_id": prior.id, "responder": speaker, "response_status": operation.response_status, "resolution": operation.resolution, "turn": turn})
        elif isinstance(operation, ReviseProposition):
            old = _require(propositions, operation.old_proposition_id, "old_proposition_id", index)
            if old.speaker != speaker:
                raise PatchValidationError([PatchIssue("invalid_owner", "old_proposition_id", "Cannot revise opponent proposition", index, old.id)])
            new_id = f"C{len(next_state.propositions) + 1}"
            node = Proposition(id=new_id, text=operation.new_proposition_text, speaker=speaker, turn=turn)
            next_state.propositions.append(node)
            propositions[new_id] = node
            next_state.commitment_events.append(CommitmentEvent(event="REVISE", speaker=speaker, proposition_id=new_id, old_proposition_id=old.id, new_proposition_id=new_id, turn=turn))
        elif isinstance(operation, ConcedeLocal):
            _require(propositions, operation.proposition_id, "proposition_id", index)
            next_state.commitment_events.append(CommitmentEvent(event="CONCEDE", speaker=speaker, proposition_id=operation.proposition_id, turn=turn))
        elif isinstance(operation, WithdrawProposition):
            prior = _require(propositions, operation.proposition_id, "proposition_id", index)
            if prior.speaker != speaker:
                raise PatchValidationError([PatchIssue("invalid_owner", "proposition_id", "Cannot withdraw opponent proposition", index, prior.id)])
            next_state.commitment_events.append(CommitmentEvent(event="WITHDRAW", speaker=speaker, proposition_id=prior.id, turn=turn))
    next_state.event_log.append({"turn": turn, "speaker": speaker, "patch": patch.model_dump()})
    return next_state


def apply_with_bounded_repair(
    state: DebateState,
    candidate: dict | PatchEnvelope,
    *,
    speaker: str,
    turn: int,
    repair: Callable[[list[PatchIssue]], dict | PatchEnvelope] | None = None,
) -> PatchResult:
    try:
        return PatchResult(True, apply_patch(state, candidate, speaker=speaker, turn=turn), 1)
    except PatchValidationError as first:
        if repair is None:
            return PatchResult(False, state, 1, tuple(first.issues))
        try:
            corrected = repair(first.issues)
            return PatchResult(True, apply_patch(state, corrected, speaker=speaker, turn=turn), 2)
        except PatchValidationError as second:
            return PatchResult(False, state, 2, tuple(second.issues))
        except Exception as exc:
            return PatchResult(False, state, 2, (PatchIssue("repair_failed", "repair", type(exc).__name__),))
