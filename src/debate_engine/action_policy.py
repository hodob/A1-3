"""Small deterministic eligibility policy for the integration diagnostic."""

from __future__ import annotations

from dataclasses import dataclass

from .debate_contracts import DebateState
from .target_quality import derive_target_metadata, ranking_key, saturation_key
from .action_pair_state import evaluate_action_target_pair, filter_available_pairs, strategic_priority
from .persona_preferences import preference_level
from .debate_control import TurnTask, TurnTaskKind, build_control_view


@dataclass(frozen=True)
class ActionCandidate:
    name: str
    target_ids: tuple[str, ...] = ()


def eligible_actions(state: DebateState, speaker: str, phase: str, *, turn_task: TurnTask | None = None) -> list[ActionCandidate]:
    opponent = [p for p in state.propositions if p.speaker != speaker]
    own = [p for p in state.propositions if p.speaker == speaker]

    if turn_task is not None:
        kind = turn_task.kind
        if kind == TurnTaskKind.NO_VALUABLE_MOVE:
            return []
        if kind == TurnTaskKind.INTRODUCE_UNCOVERED_FACET:
            return [ActionCandidate("EXTEND_ARGUMENT")]
        if kind == TurnTaskKind.CRYSTALLIZE:
            return [ActionCandidate("CRYSTALLIZE")]
        if kind == TurnTaskKind.WEIGH_COMPETING_REASONS:
            return [ActionCandidate("WEIGH_COMPARATIVE", turn_task.target_ids)] if len(turn_task.target_ids) >= 2 else []
        if kind == TurnTaskKind.ADDRESS_COUNTEREXAMPLE:
            target = turn_task.target_ids[:1]
            return [ActionCandidate("REFUTE_CLAIM", target), ActionCandidate("CONCEDE_LOCAL", target)] if target else []
        if kind == TurnTaskKind.ANSWER_OPEN_QUESTION:
            # The Immediate QUD determines the strategic target. Persona preference may
            # choose between compatible moves, but may not redirect the turn elsewhere.
            question = next((q for q in state.questions if q.id in turn_task.target_ids), None)
            if question and question.target_proposition_id:
                target = next((p for p in state.propositions if p.id == question.target_proposition_id), None)
                if target is not None:
                    control = build_control_view(state)
                    facet_id = control.proposition_to_facet.get(target.id)
                    current_id = next((f.current_id for f in control.facets if f.id == facet_id), target.id)
                    if target.speaker == speaker:
                        return [
                            ActionCandidate("DEFEND_CLAIM", (current_id,)),
                            ActionCandidate("REVISE_CLAIM", (current_id,)),
                        ]
                    return [ActionCandidate("CONCEDE_LOCAL", (current_id,))]
            return [ActionCandidate("DEFEND_CLAIM", (p.id,)) for p in reversed(own[:2])] or [ActionCandidate("EXTEND_ARGUMENT")]
        if kind == TurnTaskKind.ADDRESS_AUDIENCE:
            options = [ActionCandidate("DEFEND_CLAIM", (p.id,)) for p in reversed(own[-2:])]
            comparative = any(token in turn_task.description for token in ("비교", "차이", "어느", "더 낫", "더 중요", "우선"))
            if comparative and opponent and own:
                options.append(ActionCandidate("WEIGH_COMPARATIVE", (opponent[-1].id, own[-1].id)))
            return options or [ActionCandidate("EXTEND_ARGUMENT")]
        if kind == TurnTaskKind.NARROW_DISAGREEMENT:
            return [ActionCandidate("SEEK_COMMITMENT", (p.id,)) for p in reversed(opponent)] + [ActionCandidate("CLARIFY_CLAIM", (p.id,)) for p in reversed(opponent)]
        if kind == TurnTaskKind.TEST_UNRESOLVED_REASON:
            target_ids = set(turn_task.target_ids)
            targets = [p for p in reversed(opponent) if not target_ids or p.id in target_ids]
            options = []
            for proposition in targets:
                options.extend(ActionCandidate(name, (proposition.id,)) for name in ("CHALLENGE_PREMISE", "CHALLENGE_INFERENCE", "REQUEST_SUPPORT", "TEST_BOUNDARY", "CLARIFY_CLAIM", "SEEK_COMMITMENT", "CHECK_CONSISTENCY"))
            return options

    # Legacy/default phase policy remains available for CLI fixtures and backward compatibility.
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

    # Prevent semantic duplicate proposition IDs from bypassing Action×Target exhaustion.
    # Raw proposition IDs remain authoritative, but the control plane treats members of
    # the same semantic facet as one target for repetition purposes.
    control = build_control_view(state)
    used_semantic_pairs = set()
    for owner, action, targets in previous:
        if owner != speaker or not targets:
            continue
        first = targets[0]
        facet_id = control.proposition_to_facet.get(first)
        if facet_id:
            used_semantic_pairs.add((action, facet_id))
    semantic_filtered = []
    for candidate in remaining:
        if not candidate.target_ids:
            semantic_filtered.append(candidate)
            continue
        facet_id = control.proposition_to_facet.get(candidate.target_ids[0])
        if facet_id and (candidate.name, facet_id) in used_semantic_pairs:
            continue
        if facet_id in control.agreed_facet_ids and candidate.name in {
            "CHALLENGE_PREMISE", "CHALLENGE_INFERENCE", "REQUEST_SUPPORT", "TEST_BOUNDARY", "CHECK_CONSISTENCY", "REFUTE_CLAIM", "CLARIFY_CLAIM", "SEEK_COMMITMENT"
        }:
            continue
        semantic_filtered.append(candidate)
    remaining = semantic_filtered

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
