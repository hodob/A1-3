import unittest

from src.debate_engine.debate_contracts import (
    DebateState,
    PatchValidationError,
    apply_patch,
    apply_with_bounded_repair,
)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.initial = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "text": "핫도그는 샌드위치다"},
            {"op": "ASK_QUESTION", "core_proposition": "분류 기준은?", "target_proposition_id": "C1"},
        ]}, speaker="A", turn=1)

    def test_question_id_in_proposition_field_rejected(self):
        patch = {"operations": [{"op": "ADD_RELATION", "from_proposition_id": "Q1", "to_proposition_id": "C1", "relation_type": "ATTACKS"}]}
        with self.assertRaises(PatchValidationError) as caught:
            apply_patch(self.initial, patch, speaker="B", turn=2)
        self.assertEqual(caught.exception.issues[0].code, "invalid_reference_type")

    def test_proposition_id_in_question_field_rejected(self):
        patch = {"operations": [{"op": "ANSWER_QUESTION", "question_id": "C1", "response_status": "DIRECT", "resolution": "RESOLVED"}]}
        with self.assertRaises(PatchValidationError) as caught:
            apply_patch(self.initial, patch, speaker="B", turn=2)
        self.assertEqual(caught.exception.issues[0].code, "invalid_reference_type")

    def test_missing_entity_reference_rejected(self):
        patch = {"operations": [{"op": "REVISE_PROPOSITION", "old_proposition_id": "C404", "new_proposition_text": "핫도그는 별도 범주다"}]}
        with self.assertRaises(PatchValidationError) as caught:
            apply_patch(self.initial, patch, speaker="A", turn=2)
        self.assertEqual(caught.exception.issues[0].code, "missing_entity")

    def test_invalid_later_operation_leaves_original_state_unchanged(self):
        before = self.initial.model_dump()
        patch = {"operations": [
            {"op": "ADD_PROPOSITION", "text": "새 주장"},
            {"op": "ANSWER_QUESTION", "question_id": "Q404", "response_status": "DIRECT", "resolution": "RESOLVED"},
        ]}
        with self.assertRaises(PatchValidationError):
            apply_patch(self.initial, patch, speaker="B", turn=2)
        self.assertEqual(self.initial.model_dump(), before)

    def test_revision_creates_new_proposition_and_event(self):
        revised = apply_patch(self.initial, {"operations": [
            {"op": "REVISE_PROPOSITION", "old_proposition_id": "C1", "new_proposition_text": "핫도그는 별도 범주다"}
        ]}, speaker="A", turn=2)
        self.assertEqual(revised.propositions[0].text, "핫도그는 샌드위치다")
        self.assertEqual(revised.propositions[1].text, "핫도그는 별도 범주다")
        self.assertEqual(revised.commitment_events[-1].event, "REVISE")
        self.assertEqual(revised.commitment_events[-1].old_proposition_id, "C1")
        self.assertEqual(revised.commitment_events[-1].new_proposition_id, "C2")

    def test_text_mutation_operation_rejected(self):
        with self.assertRaises(PatchValidationError):
            apply_patch(self.initial, {"operations": [{"op": "SET_PROPOSITION_TEXT", "proposition_id": "C1", "text": "덮어쓰기"}]}, speaker="A", turn=2)

    def test_repair_is_bounded_and_repeated_failure_is_safe(self):
        before = self.initial.model_dump()
        bad = {"operations": [{"op": "ANSWER_QUESTION", "question_id": "C1", "response_status": "DIRECT", "resolution": "RESOLVED"}]}
        calls = []

        def repair(issues):
            calls.append(issues)
            self.assertEqual(self.initial.model_dump(), before)
            return bad

        result = apply_with_bounded_repair(self.initial, bad, speaker="B", turn=2, repair=repair)
        self.assertFalse(result.applied)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.state.model_dump(), before)
        self.assertEqual(result.issues[0].code, "invalid_reference_type")


if __name__ == "__main__":
    unittest.main()
