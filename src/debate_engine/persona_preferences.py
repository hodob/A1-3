"""Coarse Persona preferences used only after hard Action eligibility."""

from __future__ import annotations

from enum import IntEnum


class PreferenceLevel(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2


PERSONA_ACTION_PREFERENCES: dict[str, frozenset[str]] = {
    "Auditor": frozenset({"REQUEST_SUPPORT", "CHALLENGE_INFERENCE", "CHECK_CONSISTENCY"}),
    "Socratic": frozenset({"CLARIFY_CLAIM", "CHALLENGE_PREMISE", "SEEK_COMMITMENT"}),
    "Falsifier": frozenset({"TEST_BOUNDARY", "CHECK_CONSISTENCY", "REFUTE_CLAIM"}),
    "Pragmatist": frozenset({"WEIGH_COMPARATIVE", "REFUTE_CLAIM", "DEFEND_CLAIM"}),
    "Principlist": frozenset({"CHALLENGE_PREMISE", "CHECK_CONSISTENCY", "EXTEND_ARGUMENT"}),
    "Synthesist": frozenset({"CONCEDE_LOCAL", "REVISE_CLAIM", "WEIGH_COMPARATIVE", "CRYSTALLIZE"}),
}


def preference_level(persona: str | None, action: str) -> PreferenceLevel:
    """Return a tie-break preference; None is the Persona-off control."""
    if persona is None:
        return PreferenceLevel.MEDIUM
    if persona not in PERSONA_ACTION_PREFERENCES:
        raise ValueError(f"Unknown Persona: {persona}")
    return PreferenceLevel.HIGH if action in PERSONA_ACTION_PREFERENCES[persona] else PreferenceLevel.MEDIUM
