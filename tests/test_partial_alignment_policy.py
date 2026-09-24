import unittest

from src.debate_engine.action_fidelity import ActionFidelityLabel
from src.debate_engine.combined_compliance import CombinedComplianceAssessment, finalize_compliant_utterance
from src.debate_engine.stance_compliance import StanceAssignment, StanceLabel


class PartialAlignmentPolicyTests(unittest.TestCase):
    def setUp(self):
        self.assignment = StanceAssignment("A안", "B안")

    def verdict(self, **overrides):
        values = dict(primary_action_performed=True, target_used=True, action_is_core_function=True, additional_move_protocol_compliant=True)
        values.update(overrides)
        return CombinedComplianceAssessment(ActionFidelityLabel.PARTIALLY_ALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "부분 수행", "입장 유지", **values)

    def test_partial_is_accepted_only_when_all_policy_conditions_hold(self):
        result = finalize_compliant_utterance(lambda _: "발언", self.assignment, "CHALLENGE_PREMISE", "대상", "crossfire", lambda *_: self.verdict())
        self.assertTrue(result.committed)

    def test_partial_without_target_use_regenerates_and_safe_fails(self):
        result = finalize_compliant_utterance(lambda _: "발언", self.assignment, "CHALLENGE_PREMISE", "대상", "crossfire", lambda *_: self.verdict(target_used=False))
        self.assertFalse(result.committed)
        self.assertEqual(result.attempts, 2)

    def test_partial_with_protocol_violation_regenerates(self):
        verdicts = iter([self.verdict(additional_move_protocol_compliant=False), self.verdict()])
        result = finalize_compliant_utterance(lambda _: "발언", self.assignment, "CHALLENGE_PREMISE", "대상", "crossfire", lambda *_: next(verdicts))
        self.assertTrue(result.committed)
        self.assertEqual(result.attempts, 2)


if __name__ == "__main__":
    unittest.main()
