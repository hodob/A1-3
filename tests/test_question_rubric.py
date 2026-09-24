import unittest
import json
from pathlib import Path

from src.debate_engine.question_rubric import ResponseEvidence, ResponseLabel, classify_response


class QuestionRubricTests(unittest.TestCase):
    def test_direct_answer_with_explanation_stays_direct(self):
        evidence = ResponseEvidence(core_answered=True, scope_restricted=False, requested_parts=1, resolved_parts=1)
        self.assertEqual(classify_response(evidence), ResponseLabel.DIRECT)

    def test_actual_scope_restriction_is_qualified(self):
        evidence = ResponseEvidence(core_answered=True, scope_restricted=True, requested_parts=1, resolved_parts=1)
        self.assertEqual(classify_response(evidence), ResponseLabel.QUALIFIED)

    def test_valid_frame_rejection_requires_state_conflict(self):
        evidence = ResponseEvidence(core_answered=False, frame_rejected=True, premise_conflicts_state=True)
        self.assertEqual(classify_response(evidence), ResponseLabel.FRAME_REJECTED_VALID)
        unsupported = ResponseEvidence(core_answered=False, frame_rejected=True, premise_conflicts_state=False)
        self.assertNotEqual(classify_response(unsupported), ResponseLabel.FRAME_REJECTED_VALID)

    def test_six_real_cases_keep_original_text_and_review_provenance(self):
        fixture = json.loads(Path("etc/fixtures/question_response_reannotation.json").read_text(encoding="utf-8"))
        self.assertEqual(len(fixture["cases"]), 6)
        self.assertTrue(all(case["question"] and case["response"] for case in fixture["cases"]))
        self.assertIn("assistant_manual_review", fixture["annotation_provenance"])
        self.assertTrue(all(case["source_human_label"] for case in fixture["cases"]))


if __name__ == "__main__":
    unittest.main()
