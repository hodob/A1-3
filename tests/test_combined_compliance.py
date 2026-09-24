import unittest

from src.debate_engine.combined_compliance import CombinedComplianceAssessment, finalize_compliant_utterance
from src.debate_engine.action_fidelity import ActionFidelityLabel
from src.debate_engine.stance_compliance import StanceAssignment, StanceLabel
from src.debate_engine.debate_contracts import DebateState
from etc.tools.integrated_debate import commit_guarded_turn


class CombinedComplianceTests(unittest.TestCase):
    def setUp(self):
        self.assignment = StanceAssignment("A안", "B안")

    def test_partial_action_and_compatible_stance_are_accepted_with_flag(self):
        assessment = CombinedComplianceAssessment(ActionFidelityLabel.PARTIALLY_ALIGNED, StanceLabel.COMPATIBLE_WITH_ASSIGNED, "일부 수행", "양보 후 유지")
        result = finalize_compliant_utterance(lambda _: "발언", self.assignment, "CHALLENGE_PREMISE", "target", "crossfire", lambda *_: assessment)
        self.assertTrue(result.committed)
        self.assertTrue(result.diagnostic_flag)

    def test_misaligned_action_regenerates_once(self):
        verdicts = iter([
            CombinedComplianceAssessment(ActionFidelityLabel.MISALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "다른 target", "유지"),
            CombinedComplianceAssessment(ActionFidelityLabel.ALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "수행", "유지"),
        ])
        prompts = []
        result = finalize_compliant_utterance(lambda feedback: (prompts.append(feedback), "발언")[1], self.assignment, "CHALLENGE_PREMISE", "target", "crossfire", lambda *_: next(verdicts))
        self.assertTrue(result.committed)
        self.assertEqual(result.attempts, 2)
        self.assertIn("MISALIGNED", prompts[1])

    def test_repeated_action_failure_is_safe(self):
        bad = CombinedComplianceAssessment(ActionFidelityLabel.MISALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "target 지지", "유지")
        result = finalize_compliant_utterance(lambda _: "발언", self.assignment, "CHALLENGE_PREMISE", "target", "crossfire", lambda *_: bad)
        self.assertFalse(result.committed)
        self.assertEqual(result.attempts, 2)

    def test_ambiguous_stance_regenerates(self):
        bad = CombinedComplianceAssessment(ActionFidelityLabel.ALIGNED, StanceLabel.AMBIGUOUS, "수행", "입장 불명")
        result = finalize_compliant_utterance(lambda _: "발언", self.assignment, "CRYSTALLIZE", None, "final_focus", lambda *_: bad)
        self.assertFalse(result.committed)

    def test_repeated_fidelity_failure_skips_patch_and_state_change(self):
        bad = CombinedComplianceAssessment(ActionFidelityLabel.MISALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "target 지지", "유지")
        patch_calls = []
        state = DebateState()
        result = commit_guarded_turn(state, lambda _: "발언", self.assignment, action="CHALLENGE_PREMISE", target_text="target", phase="crossfire", combined_check=lambda *_: bad, extract_patch=lambda *_: patch_calls.append(1))
        self.assertFalse(result["committed"])
        self.assertEqual(patch_calls, [])
        self.assertEqual(result["state"].model_dump(), state.model_dump())


if __name__ == "__main__":
    unittest.main()
