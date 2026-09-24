"""Small deterministic eligibility policy for the integration diagnostic."""

from __future__ import annotations

from dataclasses import dataclass

from .debate_contracts import DebateState
from .target_quality import derive_target_metadata, ranking_key, saturation_key
from .action_pair_state import evaluate_action_target_pair, filter_available_pairs, strategic_priority
from .persona_preferences import preference_level


@dataclass(frozen=True)
class ActionCandidate:
    name: str
    target_ids: tuple[str, ...] = ()


def eligible_actions(state: DebateState, speaker: str, phase: str) -> list[ActionCandidate]:
    opponent = [p for p in state.propositions if p.speaker != speaker]
    own = [p for p in state.propositions if p.speaker == speaker]
    if phase == "opening":
        return [ActionCandidate("EXTEND_ARGUMENT")]
    if phase == "crossfire":
        options = [ActionCandidate("PRESS_UNANSWERED", (q.id,)) for q in state.questions if q.asker == speaker and q.resolution == "OPEN" and q.response_status in ("PARTIAL", "EVADED")]
        for proposition in reversed(opponent):
            options.extend(ActionCandidate(name, (proposition.id,)) for name in ("CHALLENGE_PREMISE", "CHALLENGE_INFERENCE", "REQUEST_SUPPORT", "TEST_BOUNDARY", "CLARIFY_CLAIM"))
        return options
    if phase == "rebuttal":
        return [ActionCandidate("REFUTE_CLAIM", (p.id,)) for p in reversed(opponent)] + [ActionCandidate("DEFEND_CLAIM", (p.id,)) for p in reversed(own)]
    if phase == "final_focus":
        return [ActionCandidate("CRYSTALLIZE")]
    if phase == "audience_response":
        return [ActionCandidate("DEFEND_CLAIM", (p.id,)) for p in reversed(own)]
    raise ValueError(f"Unsupported phase: {phase}")


def select_action(options: list[ActionCandidate], previous: list[tuple[str, tuple[str, ...]]]) -> ActionCandidate | None:
    used = set(previous)
    return next((candidate for candidate in options if (candidate.name, candidate.target_ids) not in used), None)


def select_action_for_speaker(options: list[ActionCandidate], previous: list[tuple[str, str, tuple[str, ...]]], speaker: str, *, state: DebateState | None = None, current_turn: int | None = None, persona: str | None = None) -> ActionCandidate | None:
    remaining = list(options)
    if state is None or current_turn is None:
        speaker_previous = {(action, targets) for owner, action, targets in previous if owner == speaker}
        remaining = [candidate for candidate in remaining if (candidate.name, candidate.target_ids) not in speaker_previous]
        return max(remaining, key=lambda candidate: preference_level(persona, candidate.name), default=None)
    remaining = filter_available_pairs(state, speaker, remaining, previous, current_turn=current_turn)

    def candidate_key(candidate: ActionCandidate) -> tuple:
        if candidate.target_ids and candidate.target_ids[0].startswith("Q"):
            return (3, (), 0, int(preference_level(persona, candidate.name)), 0)
        if not candidate.target_ids:
            return (1, (), 0, int(preference_level(persona, candidate.name)), 0)
        metadata = derive_target_metadata(state, candidate.target_ids[0], current_turn=current_turn, action_history=previous)
        pair = evaluate_action_target_pair(state, speaker, candidate.name, candidate.target_ids[0], previous, current_turn=current_turn)
        return (
            2,
            ranking_key(metadata),
            strategic_priority(pair),
            int(preference_level(persona, candidate.name)),
            saturation_key(metadata),
        )

    return max(remaining, key=candidate_key, default=None)
