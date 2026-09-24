import unittest

from src.debate_engine.stance_compliance import StanceAssignment, StanceLabel, finalize_utterance, validate_utterance


class StanceTests(unittest.TestCase):
    def setUp(self):
        self.assignment = StanceAssignment(
            assigned_thesis="핫도그는 샌드위치가 아니다",
            opposing_thesis="핫도그는 샌드위치다",
        )

    def test_socratic_local_concession_passes(self):
        speech = "구조가 닮았다는 점은 인정합니다. 하지만 제 최종 입장은 핫도그는 샌드위치가 아니다."
        result = validate_utterance(speech, self.assignment, phase="final_focus")
        self.assertTrue(result.accepted)
        self.assertNotEqual(result.label, StanceLabel.CONTRADICTS_ASSIGNED)

    def test_socratic_thesis_reversal_fails(self):
        speech = "반론을 받아들입니다. 제 최종 입장은 핫도그는 샌드위치다."
        result = validate_utterance(speech, self.assignment, phase="final_focus")
        self.assertFalse(result.accepted)
        self.assertEqual(result.label, StanceLabel.CONTRADICTS_ASSIGNED)

    def test_reversal_is_not_committed_and_one_regeneration_is_allowed(self):
        generated = iter([
            "제 최종 입장은 핫도그는 샌드위치다.",
            "유사성은 인정하지만 제 최종 입장은 핫도그는 샌드위치가 아니다.",
        ])
        calls = []

        def generate(feedback):
            calls.append(feedback)
            return next(generated)

        result = finalize_utterance(generate, self.assignment, phase="final_focus")
        self.assertTrue(result.committed)
        self.assertEqual(result.attempts, 2)
        self.assertIn("CONTRADICTS_ASSIGNED", calls[1])
        self.assertNotIn("제 최종 입장은 핫도그는 샌드위치다.", result.utterance)

    def test_repeated_reversal_fails_safely(self):
        calls = []

        def generate(feedback):
            calls.append(feedback)
            return "제 최종 입장은 핫도그는 샌드위치다."

        result = finalize_utterance(generate, self.assignment, phase="final_focus")
        self.assertFalse(result.committed)
        self.assertIsNone(result.utterance)
        self.assertEqual(len(calls), 2)

    def test_actual_swapped_final_is_not_committed_when_thesis_is_ambiguous(self):
        assignment = StanceAssignment("별도 범주", "샌드위치")
        actual = "그래서 제 최종 입장도 간단합니다: 핫도그는 샌드위치이기도 하지만, 생활 언어에선 별도 범주로 강하게 작동한다. 다만 논제에 한 줄로 답해야 한다면, 이제는 ‘예, 하지만 보통은 따로 부른다’가 가장 덜 비틀린 답이라고 봅니다."
        assessment = validate_utterance(actual, assignment, phase="final_focus")
        self.assertFalse(assessment.accepted)
        self.assertEqual(assessment.label, StanceLabel.AMBIGUOUS)


if __name__ == "__main__":
    unittest.main()
