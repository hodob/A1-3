"""Coarse, explainable metadata for ranking eligible action targets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import re

from .debate_contracts import DebateState


class Level(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Actionability(str, Enum):
    CORE = "CORE"
    SUPPORTING = "SUPPORTING"
    CONTEXTUAL = "CONTEXTUAL"
    RHETORICAL = "RHETORICAL"


@dataclass(frozen=True)
class TargetQualityMetadata:
    target_id: str
    actionability: Actionability
    clash_relevance: Level
    claim_centrality: Level
    unresolved_status: bool
    recentness: Level
    opponent_commitment_strength: Level
    question_dependency: bool
    downstream_reuse_risk: Level
    rhetorical_only: bool
    duplicate_or_superseded: bool
    already_resolved: bool
    already_conceded: bool
    recently_exhausted: bool

    def as_dict(self) -> dict:
        result = asdict(self)
        return {key: value.value if isinstance(value, Enum) else value for key, value in result.items()}


_RHETORICAL = re.compile(r"비유|마치|처럼|셈(?:이|인|으)|볼륨\s*자동조절|다이내믹\s*레인지|체온계와\s*같")


def _actionability(text: str, degree: int, is_first_commitment: bool) -> Actionability:
    if _RHETORICAL.search(text):
        return Actionability.RHETORICAL
    if is_first_commitment or degree >= 2:
        return Actionability.CORE
    if degree == 1:
        return Actionability.SUPPORTING
    return Actionability.CONTEXTUAL


def derive_target_metadata(state: DebateState, target_id: str, *, current_turn: int, action_history: list[tuple[str, str, tuple[str, ...]]]) -> TargetQualityMetadata:
    proposition = next((p for p in state.propositions if p.id == target_id), None)
    if proposition is None:
        raise ValueError(f"Invalid proposition target: {target_id}")
    related = [r for r in state.relations if target_id in (r.from_proposition_id, r.to_proposition_id)]
    attacks = any(r.relation_type in ("ATTACKS", "CONTRADICTS") for r in related)
    revised = any(e.event == "REVISE" and e.old_proposition_id == target_id for e in state.commitment_events)
    withdrawn = any(e.event == "WITHDRAW" and e.proposition_id == target_id for e in state.commitment_events)
    conceded = any(e.event == "CONCEDE" and e.proposition_id == target_id for e in state.commitment_events)
    dependent_questions = [q for q in state.questions if q.target_proposition_id == target_id]
    unresolved = any(q.resolution == "OPEN" for q in dependent_questions) or not dependent_questions
    resolved = bool(dependent_questions) and all(q.resolution == "RESOLVED" for q in dependent_questions)
    targeted = sum(target_id in targets for _, _, targets in action_history)
    first_for_speaker = next((p.id for p in state.propositions if p.speaker == proposition.speaker), None) == target_id
    actionability = _actionability(proposition.text, len(related), first_for_speaker)
    degree = len(related)
    return TargetQualityMetadata(
        target_id=target_id,
        actionability=actionability,
        clash_relevance=Level.HIGH if attacks else Level.MEDIUM if degree else Level.LOW,
        claim_centrality=Level.HIGH if actionability == Actionability.CORE else Level.MEDIUM if actionability == Actionability.SUPPORTING else Level.LOW,
        unresolved_status=unresolved and not (revised or withdrawn or conceded),
        recentness=Level.HIGH if current_turn - proposition.turn <= 2 else Level.MEDIUM if current_turn - proposition.turn <= 5 else Level.LOW,
        opponent_commitment_strength=Level.LOW if (revised or withdrawn or conceded) else Level.HIGH,
        question_dependency=bool(dependent_questions),
        downstream_reuse_risk=Level.HIGH if degree >= 3 else Level.MEDIUM if degree else Level.LOW,
        rhetorical_only=actionability == Actionability.RHETORICAL,
        duplicate_or_superseded=revised or withdrawn,
        already_resolved=resolved,
        already_conceded=conceded,
        recently_exhausted=targeted >= 2,
    )


def ranking_key(metadata: TargetQualityMetadata) -> tuple:
    level = {Level.LOW: 0, Level.MEDIUM: 1, Level.HIGH: 2}
    penalty = sum((metadata.rhetorical_only, metadata.duplicate_or_superseded, metadata.already_resolved, metadata.already_conceded))
    return (
        -penalty,
        int(metadata.unresolved_status),
        level[metadata.clash_relevance],
        level[metadata.claim_centrality],
        level[metadata.opponent_commitment_strength],
        int(metadata.question_dependency),
        level[metadata.recentness],
    )


def saturation_key(metadata: TargetQualityMetadata) -> int:
    """Apply repeated-target saturation after strategic and Persona ranking."""
    return -int(metadata.recently_exhausted)
