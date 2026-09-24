import unittest

from src.debate_engine.action_policy import ActionCandidate, select_action_for_speaker
from src.debate_engine.debate_contracts import DebateState, apply_patch


def opponent_claim_state() -> DebateState:
    return apply_patch(
        DebateState(),
        {"operations": [{"op": "ADD_PROPOSITION", "text": "핵심 기준은 적용 범위와 결과를 함께 봐야 한다."}]},
        speaker="B",
        turn=1,
    )


class PersonaActionPreferenceTests(unittest.TestCase):
    def select(self, persona, options, state=None):
        return select_action_for_speaker(
            options,
            [],
            "A",
            state=state or opponent_claim_state(),
            current_turn=2,
            persona=persona,
        )

    def test_auditor_prefers_request_support_when_it_is_valid(self):
        selected = self.select("Auditor", [
            ActionCandidate("TEST_BOUNDARY", ("C1",)),
            ActionCandidate("REQUEST_SUPPORT", ("C1",)),
        ])
        self.assertEqual(selected.name, "REQUEST_SUPPORT")

    def test_auditor_cannot_resurrect_request_support_after_support_is_sufficient(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "핵심 주장"},
            {"op": "ADD_PROPOSITION", "temp_id": "P2", "text": "핵심 주장을 직접 뒷받침하는 근거"},
            {"op": "ADD_RELATION", "from_proposition_ref": "P2", "to_proposition_ref": "P1", "relation_type": "SUPPORTS"},
        ]}, speaker="B", turn=1)
        selected = self.select("Auditor", [
            ActionCandidate("REQUEST_SUPPORT", ("C1",)),
            ActionCandidate("TEST_BOUNDARY", ("C1",)),
        ], state)
        self.assertEqual(selected.name, "TEST_BOUNDARY")

    def test_socratic_prefers_clarification_in_tie_like_candidates(self):
        selected = self.select("Socratic", [
            ActionCandidate("TEST_BOUNDARY", ("C1",)),
            ActionCandidate("CLARIFY_CLAIM", ("C1",)),
        ])
        self.assertEqual(selected.name, "CLARIFY_CLAIM")

    def test_falsifier_prefers_boundary_test_in_tie_like_candidates(self):
        selected = self.select("Falsifier", [
            ActionCandidate("CLARIFY_CLAIM", ("C1",)),
            ActionCandidate("TEST_BOUNDARY", ("C1",)),
        ])
        self.assertEqual(selected.name, "TEST_BOUNDARY")

    def test_same_ordered_candidates_change_only_by_persona(self):
        options = [
            ActionCandidate("CLARIFY_CLAIM", ("C1",)),
            ActionCandidate("TEST_BOUNDARY", ("C1",)),
            ActionCandidate("CHALLENGE_PREMISE", ("C1",)),
        ]
        self.assertEqual(self.select("Socratic", options).name, "CLARIFY_CLAIM")
        self.assertEqual(self.select("Falsifier", options).name, "TEST_BOUNDARY")

    def test_pragmatist_prefers_comparative_weighing_when_candidate_is_valid(self):
        selected = self.select("Pragmatist", [
            ActionCandidate("CHALLENGE_PREMISE", ("C1",)),
            ActionCandidate("WEIGH_COMPARATIVE", ("C1",)),
        ])
        self.assertEqual(selected.name, "WEIGH_COMPARATIVE")

    def test_principlist_prefers_consistency_check_in_tie_like_candidates(self):
        selected = self.select("Principlist", [
            ActionCandidate("TEST_BOUNDARY", ("C1",)),
            ActionCandidate("CHECK_CONSISTENCY", ("C1",)),
        ])
        self.assertEqual(selected.name, "CHECK_CONSISTENCY")

    def test_synthesist_prefers_concession_only_when_it_is_an_eligible_candidate(self):
        selected = self.select("Synthesist", [
            ActionCandidate("CHALLENGE_PREMISE", ("C1",)),
            ActionCandidate("CONCEDE_LOCAL", ("C1",)),
        ])
        self.assertEqual(selected.name, "CONCEDE_LOCAL")

        without_concession = self.select("Synthesist", [ActionCandidate("CHALLENGE_PREMISE", ("C1",))])
        self.assertEqual(without_concession.name, "CHALLENGE_PREMISE")

    def test_persona_off_preserves_deterministic_control_path(self):
        options = [
            ActionCandidate("CLARIFY_CLAIM", ("C1",)),
            ActionCandidate("TEST_BOUNDARY", ("C1",)),
        ]
        selected = self.select(None, options)
        self.assertEqual(selected, options[0])

    def test_persona_cannot_select_blocked_target(self):
        state = opponent_claim_state()
        selected = self.select("Falsifier", [
            ActionCandidate("TEST_BOUNDARY", ("C999",)),
            ActionCandidate("CLARIFY_CLAIM", ("C1",)),
        ], state)
        self.assertEqual(selected.name, "CLARIFY_CLAIM")

    def test_persona_cannot_resurrect_action_with_failed_precondition(self):
        selected = self.select("Auditor", [
            ActionCandidate("CHALLENGE_INFERENCE", ("C1",)),
            ActionCandidate("CHECK_CONSISTENCY", ("C1",)),
        ])
        self.assertEqual(selected.name, "CHECK_CONSISTENCY")

    def test_single_valid_candidate_is_identical_for_every_persona(self):
        option = ActionCandidate("CHALLENGE_PREMISE", ("C1",))
        for persona in ("Auditor", "Socratic", "Falsifier", "Pragmatist", "Principlist", "Synthesist", None):
            with self.subTest(persona=persona):
                self.assertEqual(self.select(persona, [option]), option)


if __name__ == "__main__":
    unittest.main()
