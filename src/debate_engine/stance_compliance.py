"""Local stance gate. Only explicit thesis commitments are decided automatically."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable
import re


class StanceLabel(StrEnum):
    SUPPORTS_ASSIGNED = "SUPPORTS_ASSIGNED"
    COMPATIBLE_WITH_ASSIGNED = "COMPATIBLE_WITH_ASSIGNED"
    AMBIGUOUS = "AMBIGUOUS"
    CONTRADICTS_ASSIGNED = "CONTRADICTS_ASSIGNED"


@dataclass(frozen=True)
class StanceAssignment:
    assigned_thesis: str
    opposing_thesis: str


@dataclass(frozen=True)
class StanceAssessment:
    label: StanceLabel
    accepted: bool
    reason: str


@dataclass(frozen=True)
class FinalizedUtterance:
    committed: bool
    utterance: str | None
    assessment: StanceAssessment
    attempts: int
    raw_utterance: str | None = None
    checks: tuple[dict, ...] = ()


def _explicit_commitment(speech: str) -> str | None:
    matches = re.findall(r"(?:제|저의|나의)\s*(?:최종\s*)?입장은\s*([^.!?。\n]+)", speech)
    return matches[-1].strip() if matches else None


def validate_utterance(speech: str, assignment: StanceAssignment, *, phase: str) -> StanceAssessment:
    """Fail closed on an explicit opposing final commitment; preserve local concessions.

    Semantic paraphrases require a separate assessor; this narrow deterministic gate
    reports AMBIGUOUS rather than claiming full stance compliance.
    """
    commitment = _explicit_commitment(speech)
    if commitment == assignment.opposing_thesis.strip():
        return StanceAssessment(StanceLabel.CONTRADICTS_ASSIGNED, False, "explicit opposing thesis commitment")
    if commitment == assignment.assigned_thesis.strip():
        return StanceAssessment(StanceLabel.SUPPORTS_ASSIGNED, True, "explicit assigned thesis commitment")
    decisive_opposition = re.search(
        rf"(?:결국|최종적으로|결론은)\s*{re.escape(assignment.opposing_thesis.strip())}\s*(?:이|가|은|는|쪽이)?\s*(?:더\s*)?(?:타당|낫|옳|맞)",
        speech,
    )
    if decisive_opposition:
        return StanceAssessment(StanceLabel.CONTRADICTS_ASSIGNED, False, "explicit preference for opposing thesis")
    if phase == "final_focus":
        return StanceAssessment(StanceLabel.AMBIGUOUS, False, "no unambiguous final thesis commitment detected")
    if assignment.assigned_thesis in speech and ("상대가 맞" in speech or "그 점은 맞" in speech):
        return StanceAssessment(StanceLabel.COMPATIBLE_WITH_ASSIGNED, True, "local concession while retaining assigned thesis")
    if any(word in speech for word in ("인정", "양보", "수정", "불확실")):
        return StanceAssessment(StanceLabel.COMPATIBLE_WITH_ASSIGNED, True, "local concession or uncertainty without explicit reversal")
    return StanceAssessment(StanceLabel.AMBIGUOUS, True, "no explicit thesis commitment detected")


def finalize_utterance(
    generate: Callable[[str], str],
    assignment: StanceAssignment,
    *,
    phase: str,
    semantic_check: Callable[[str, StanceAssignment, str], StanceAssessment] | None = None,
) -> FinalizedUtterance:
    checks = []
    first = None
    feedback = ""
    for attempt in (1, 2):
        speech = generate(feedback)
        if first is None:
            first = speech
        local = validate_utterance(speech, assignment, phase=phase)
        semantic = None
        if semantic_check is not None and local.label != StanceLabel.CONTRADICTS_ASSIGNED:
            semantic = semantic_check(speech, assignment, phase)
        assessment = local if local.label == StanceLabel.CONTRADICTS_ASSIGNED else semantic or local
        accepted = assessment.label in (StanceLabel.SUPPORTS_ASSIGNED, StanceLabel.COMPATIBLE_WITH_ASSIGNED)
        # The old local-only pilot may still accept a non-final ambiguous turn;
        # the integrated path always supplies semantic_check and rejects it.
        if semantic_check is None and phase != "final_focus" and local.label == StanceLabel.AMBIGUOUS:
            accepted = True
        checks.append({"attempt": attempt, "local_label": local.label.value, "semantic_label": semantic.label.value if semantic else None, "result": assessment.label.value, "accepted": accepted, "reason": assessment.reason})
        if accepted:
            return FinalizedUtterance(True, speech, assessment, attempt, first, tuple(checks))
        feedback = f"{assessment.label}: Assigned Stance는 {assignment.assigned_thesis}. 국소적 양보와 세부 주장 수정은 허용하지만 최종 Thesis 역전이나 모호한 입장 표시는 금지됩니다. 입장을 분명히 하면서 같은 쟁점에 다시 답하세요."
    return FinalizedUtterance(False, None, assessment, 2, first, tuple(checks))
