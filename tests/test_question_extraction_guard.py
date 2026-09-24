import json
import unittest
from pathlib import Path

from src.debate_engine.debate_contracts import DebateState, PatchEnvelope, PatchValidationError
from src.debate_engine.question_extraction_guard import explicit_question_candidates
from src.debate_engine.state_harness import extract_and_apply


class ExplicitQuestionGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(Path("etc/fixtures/explicit_question_turn7.json").read_text(encoding="utf-8"))

    def test_turn7_explicit_question_is_detected(self):
        self.assertIn(self.fixture["expected_question"], explicit_question_candidates(self.fixture["utterance"]))

    def test_korean_question_without_question_mark_is_detected(self):
        self.assertEqual(explicit_question_candidates("그 근거는 무엇인가요."), ["그 근거는 무엇인가요."])

    def test_colloquial_explicit_question_endings_are_detected(self):
        self.assertEqual(len(explicit_question_candidates("그게 완성된 한 접시라는 근거는 뭔가요?")), 1)
        self.assertEqual(len(explicit_question_candidates("개별 맞춤에 너무 기대는 것 아닌가요?")), 1)

    def test_quoted_question_is_not_attributed_to_speaker(self):
        self.assertEqual(explicit_question_candidates('상대는 "왜 그렇죠?"라고 물었지만 저는 전제에 답하겠습니다.'), [])

    def test_missing_question_gets_one_repair_and_creates_complete_entity(self):
        candidates = [
            self.fixture["missed_patch"],
            {"operations": [{"op": "ASK_QUESTION", "text": self.fixture["expected_question"], "core_proposition": "찍먹의 기준이 덜 희생적인 이유", "target_proposition_id": None}]},
        ]
        feedback = []

        def extractor(errors):
            feedback.append(errors)
            return PatchEnvelope.model_validate(candidates.pop(0)), {}

        state, attempts = extract_and_apply(DebateState(), "A", 7, extractor, utterance=self.fixture["utterance"])
        self.assertEqual(len(attempts), 2)
        self.assertEqual(feedback[1][0]["code"], "missing_explicit_question")
        question = state.questions[0]
        self.assertEqual(question.text, self.fixture["expected_question"])
        self.assertEqual(question.source_turn_id, 7)
        self.assertEqual(question.response_status, "UNCLEAR")
        self.assertEqual(question.resolution, "OPEN")

    def test_repeated_question_miss_is_safe_failure(self):
        original = DebateState()
        patch = PatchEnvelope.model_validate(self.fixture["missed_patch"])
        with self.assertRaises(PatchValidationError):
            extract_and_apply(original, "A", 7, lambda _: (patch, {}), utterance=self.fixture["utterance"])
        self.assertEqual(original, DebateState())


if __name__ == "__main__":
    unittest.main()
