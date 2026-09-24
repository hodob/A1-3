"""Derived Action-Target pair availability and coarse support sufficiency."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from .debate_contracts import DebateState


class PairState(str, Enum):
    AVAILABLE = "AVAILABLE"
    OPEN = "OPEN"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    RESOLVED = "RESOLVED"
    EXHAUSTED = "EXHAUSTED"
    BLOCKED = "BLOCKED"


class SupportSufficiency(str, Enum):
    NONE = "NONE"
    WEAK = "WEAK"
    SUFFICIENT = "SUFFICIENT"
    CONTESTED = "CONTESTED"


@dataclass(frozen=True)
class ActionTargetPairStatus:
    speaker: str
    action: str
    target_id: str
    state: PairState
    support_sufficiency: SupportSufficiency | None
    reason: str

    @property
    def selectable(self) -> bool:
        return self.state in (PairState.AVAILABLE, PairState.OPEN, PairState.PARTIALLY_RESOLVED)


_WORDS = re.compile(r"[가-힣A-Za-z0-9]+")
_STOPWORDS = {"그", "이", "저", "것", "수", "점", "때", "대한", "한다", "있다", "된다", "이다"}


def _tokens(text: str) -> set[str]:
    return {word for word in _WORDS.findall(text) if len(word) >= 2 and word not in _STOPWORDS}


def _history_matches(history, speaker: str, action: str | None, target_id: str) -> list[tuple]:
    return [entry for entry in history if entry[0] == speaker and (action is None or entry[1] == action) and target_id in entry[2]]


def support_sufficiency(state: DebateState, target_id: str, *, speaker: str, history) -> SupportSufficiency:
    target = next((p for p in state.propositions if p.id == target_id), None)
    if target is None:
        return SupportSufficiency.NONE
    direct = [r.from_proposition_id for r in state.relations if r.to_proposition_id == target_id and r.relation_type == "SUPPORTS"]
    weak = [r.from_proposition_id for r in state.relations if r.to_proposition_id == target_id and r.relation_type == "QUALIFIES"]
    if direct:
        contested = any(r.to_proposition_id in direct and r.relation_type in ("ATTACKS", "CONTRADICTS") for r in state.relations)
        return SupportSufficiency.CONTESTED if contested else SupportSufficiency.SUFFICIENT
    if weak:
        return SupportSufficiency.WEAK

    # An explicit local concession is structured evidence. It may establish
    # sufficiency for a strongly overlapping same-owner proposition.
    prior_engagement = _history_matches(history, speaker, None, target_id)
    if prior_engagement:
        target_terms = _tokens(target.text)
        conceded_ids = {event.proposition_id for event in state.commitment_events if event.event == "CONCEDE" and event.speaker == speaker}
        conceded_overlap = [
            len(target_terms.intersection(_tokens(proposition.text))) for proposition in state.propositions
            if proposition.id in conceded_ids and proposition.speaker == target.speaker
        ]
        if any(overlap >= 2 for overlap in conceded_overlap):
            return SupportSufficiency.SUFFICIENT

        # Lexical overlap alone is never enough for SUFFICIENT.
        overlaps = [
            len(target_terms.intersection(_tokens(proposition.text))) for proposition in state.propositions
            if proposition.speaker == target.speaker and proposition.turn > target.turn
        ]
        if any(overlaps):
            return SupportSufficiency.WEAK
    return SupportSufficiency.NONE


def evaluate_action_target_pair(state: DebateState, speaker: str, action: str, target_id: str, history, *, current_turn: int) -> ActionTargetPairStatus:
    attempts = len(_history_matches(history, speaker, action, target_id))
    proposition = next((p for p in state.propositions if p.id == target_id), None)
    question = next((q for q in state.questions if q.id == target_id), None)

    if action == "PRESS_UNANSWERED":
        if question is None or question.asker != speaker:
            return ActionTargetPairStatus(speaker, action, target_id, PairState.BLOCKED, None, "question is not pressable by speaker")
        if question.response_status in ("DIRECT", "FRAME_REJECTED_VALID") or question.resolution == "RESOLVED":
            return ActionTargetPairStatus(speaker, action, target_id, PairState.RESOLVED, None, "question is resolved")
        if question.response_status in ("PARTIAL", "EVADED"):
            return ActionTargetPairStatus(speaker, action, target_id, PairState.OPEN, None, "important answer remains incomplete")
        return ActionTargetPairStatus(speaker, action, target_id, PairState.AVAILABLE, None, "question has no substantive answer")

    if proposition is None:
        return ActionTargetPairStatus(speaker, action, target_id, PairState.BLOCKED, None, "target proposition does not exist")
    if proposition.speaker == speaker and action not in ("DEFEND_CLAIM", "REVISE_CLAIM"):
        return ActionTargetPairStatus(speaker, action, target_id, PairState.BLOCKED, None, "action requires opponent target")
    revised = any(e.event == "REVISE" and e.old_proposition_id == target_id for e in state.commitment_events)
    withdrawn = any(e.event == "WITHDRAW" and e.proposition_id == target_id for e in state.commitment_events)
    if revised or withdrawn:
        return ActionTargetPairStatus(speaker, action, target_id, PairState.BLOCKED, None, "old target was revised or withdrawn")

    sufficiency = support_sufficiency(state, target_id, speaker=speaker, history=history)
    if action == "REQUEST_SUPPORT":
        if sufficiency == SupportSufficiency.SUFFICIENT:
            return ActionTargetPairStatus(speaker, action, target_id, PairState.RESOLVED, sufficiency, "direct or sufficiently developed support already exists")
        if sufficiency == SupportSufficiency.CONTESTED:
            return ActionTargetPairStatus(speaker, action, target_id, PairState.EXHAUSTED, sufficiency, "existing support should be attacked instead of requested again")
        if sufficiency == SupportSufficiency.WEAK:
            return ActionTargetPairStatus(speaker, action, target_id, PairState.OPEN if attempts else PairState.AVAILABLE, sufficiency, "support remains incomplete")
        return ActionTargetPairStatus(speaker, action, target_id, PairState.OPEN if attempts else PairState.AVAILABLE, sufficiency, "important support is absent")

    if action == "CHALLENGE_INFERENCE" and sufficiency == SupportSufficiency.NONE:
        return ActionTargetPairStatus(speaker, action, target_id, PairState.BLOCKED, sufficiency, "no support-to-claim inference exists")
    if action == "CLARIFY_CLAIM":
        resolved_question = any(q.target_proposition_id == target_id and q.resolution == "RESOLVED" and q.response_status in ("DIRECT", "QUALIFIED", "FRAME_REJECTED_VALID") for q in state.questions)
        if resolved_question or attempts:
            return ActionTargetPairStatus(speaker, action, target_id, PairState.RESOLVED, sufficiency, "definition or scope was already clarified")
    if action == "CHECK_CONSISTENCY":
        repaired = any(e.event in ("REVISE", "CONCEDE") and (e.proposition_id == target_id or e.old_proposition_id == target_id) for e in state.commitment_events)
        if repaired:
            return ActionTargetPairStatus(speaker, action, target_id, PairState.RESOLVED, sufficiency, "tension was repaired")
    if action == "TEST_BOUNDARY" and attempts:
        return ActionTargetPairStatus(speaker, action, target_id, PairState.EXHAUSTED, sufficiency, "same boundary dimension was already tested")
    if action == "SEEK_COMMITMENT" and attempts:
        later_commitment = any(e.speaker == proposition.speaker and e.proposition_id == target_id for e in state.commitment_events)
        if later_commitment:
            return ActionTargetPairStatus(speaker, action, target_id, PairState.RESOLVED, sufficiency, "commitment is recorded")
    if attempts:
        return ActionTargetPairStatus(speaker, action, target_id, PairState.EXHAUSTED, sufficiency, "same action-target pair was already used")
    return ActionTargetPairStatus(speaker, action, target_id, PairState.AVAILABLE, sufficiency, "pair remains useful")


def filter_available_pairs(state: DebateState, speaker: str, candidates, history, *, current_turn: int):
    result = []
    for candidate in candidates:
        if not candidate.target_ids:
            result.append(candidate)
            continue
        status = evaluate_action_target_pair(state, speaker, candidate.name, candidate.target_ids[0], history, current_turn=current_turn)
        if status.selectable:
            result.append(candidate)
    return result


def strategic_priority(status: ActionTargetPairStatus) -> int:
    if status.action == "PRESS_UNANSWERED":
        return 4
    if status.action == "CHALLENGE_INFERENCE" and status.support_sufficiency in (SupportSufficiency.SUFFICIENT, SupportSufficiency.CONTESTED):
        return 3
    if status.action == "REQUEST_SUPPORT" and status.support_sufficiency == SupportSufficiency.NONE:
        return 2
    return 1
