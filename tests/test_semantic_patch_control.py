import unittest
from pydantic import ValidationError

from src.debate_engine.debate_contracts import DebateState, PatchEnvelope, apply_patch


class SemanticPatchControlTests(unittest.TestCase):
    def test_same_point_requires_anchor(self):
        with self.assertRaises(ValidationError):
            PatchEnvelope.model_validate({"operations": [{"op": "ADD_PROPOSITION", "text": "반복", "semantic_kind": "SAME_POINT"}]})

    def test_semantic_anchor_can_reference_patch_local_proposition(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "핵심 이유", "semantic_kind": "NEW_REASON"},
            {"op": "ADD_PROPOSITION", "temp_id": "P2", "text": "같은 이유 정교화", "semantic_kind": "REFINEMENT", "semantic_anchor_ref": "P1"},
        ]}, speaker="A", turn=1)
        control = state.event_log[-1]["control"]["propositions"]
        self.assertEqual(control[1]["semantic_anchor_id"], "C1")

    def test_same_question_requires_anchor_and_is_not_added_twice(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ASK_QUESTION", "core_proposition": "왜?"}]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [{"op": "ASK_QUESTION", "core_proposition": "왜 그런가요?", "semantic_kind": "SAME_QUESTION", "anchor_question_id": "Q1"}]}, speaker="A", turn=2)
        self.assertEqual(len(state.questions), 1)
        self.assertEqual(state.event_log[-1]["control"]["questions"][0]["anchor_question_id"], "Q1")

    def test_same_point_cannot_anchor_opponents_proposition(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": "B 주장"}]}, speaker="B", turn=1)
        from src.debate_engine.debate_contracts import PatchValidationError
        with self.assertRaises(PatchValidationError):
            apply_patch(state, {"operations": [{"op": "ADD_PROPOSITION", "text": "A가 같은 말", "semantic_kind": "SAME_POINT", "semantic_anchor_ref": "C1"}]}, speaker="A", turn=2)


if __name__ == "__main__":
    unittest.main()
