import unittest

from src.debate_engine.action_pair_state import SupportSufficiency, support_sufficiency
from src.debate_engine.debate_contracts import DebateState, PatchValidationError, apply_patch
from src.debate_engine.state_harness import PATCH_INSTRUCTIONS, extraction_context


class RelationExtractionContractTests(unittest.TestCase):
    def test_new_temp_proposition_can_support_existing_c15(self):
        state = DebateState()
        for turn in range(1, 16):
            state = apply_patch(state, {"operations": [{"op": "ADD_PROPOSITION", "text": f"기존 주장 {turn}"}]}, speaker="A", turn=turn)
        result = apply_patch(state, {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "C15의 직접 근거"},
            {"op": "ADD_RELATION", "from_proposition_ref": "P1", "to_proposition_ref": "C15", "relation_type": "SUPPORTS"},
        ]}, speaker="B", turn=16)
        self.assertEqual((result.relations[-1].from_proposition_id, result.relations[-1].to_proposition_id), ("C16", "C15"))

    def test_new_p2_can_support_new_p1(self):
        result = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "결론"},
            {"op": "ADD_PROPOSITION", "temp_id": "P2", "text": "근거"},
            {"op": "ADD_RELATION", "from_proposition_ref": "P2", "to_proposition_ref": "P1", "relation_type": "SUPPORTS"},
        ]}, speaker="A", turn=1)
        self.assertEqual((result.relations[0].from_proposition_id, result.relations[0].to_proposition_id), ("C2", "C1"))

    def test_missing_temp_reference_is_rejected_atomically(self):
        state = DebateState()
        with self.assertRaises(PatchValidationError) as caught:
            apply_patch(state, {"operations": [{"op": "ADD_RELATION", "from_proposition_ref": "P9", "to_proposition_ref": "C1", "relation_type": "SUPPORTS"}]}, speaker="A", turn=1)
        self.assertEqual(caught.exception.issues[0].code, "missing_temp_reference")
        self.assertEqual(state, DebateState())

    def test_missing_existing_c_reference_is_rejected(self):
        with self.assertRaises(PatchValidationError) as caught:
            apply_patch(DebateState(), {"operations": [{"op": "ADD_RELATION", "from_proposition_ref": "C404", "to_proposition_ref": "C1", "relation_type": "ATTACKS"}]}, speaker="A", turn=1)
        self.assertEqual(caught.exception.issues[0].code, "missing_entity")

    def test_duplicate_temp_id_is_rejected(self):
        with self.assertRaises(PatchValidationError) as caught:
            apply_patch(DebateState(), {"operations": [
                {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "첫 주장"},
                {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "둘째 주장"},
            ]}, speaker="A", turn=1)
        self.assertEqual(caught.exception.issues[0].code, "duplicate_temp_id")

    def test_existing_relation_is_deduplicated(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "결론"},
            {"op": "ADD_PROPOSITION", "temp_id": "P2", "text": "근거"},
            {"op": "ADD_RELATION", "from_proposition_ref": "P2", "to_proposition_ref": "P1", "relation_type": "SUPPORTS"},
        ]}, speaker="A", turn=1)
        result = apply_patch(state, {"operations": [{"op": "ADD_RELATION", "from_proposition_ref": "C2", "to_proposition_ref": "C1", "relation_type": "SUPPORTS"}]}, speaker="A", turn=2)
        self.assertEqual(len(result.relations), 1)

    def test_extraction_context_contains_compact_existing_relations(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "결론"},
            {"op": "ADD_PROPOSITION", "temp_id": "P2", "text": "근거"},
            {"op": "ADD_RELATION", "from_proposition_ref": "P2", "to_proposition_ref": "P1", "relation_type": "SUPPORTS"},
        ]}, speaker="A", turn=1)
        context = extraction_context(state)
        self.assertEqual(context["propositions"][0], {"id": "C1", "text": "결론", "speaker": "A"})
        self.assertEqual(context["relations"][0], {"id": "R1", "from": "C2", "to": "C1", "type": "SUPPORTS"})

    def test_lexical_overlap_without_relation_is_at_most_weak(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": "토론 수업은 참여 기준이 필요하다"}]}, speaker="B", turn=1)
        state = apply_patch(state, {"operations": [{"op": "ADD_PROPOSITION", "text": "토론 수업 참여 기준은 학습에 필요하다"}]}, speaker="B", turn=2)
        signal = support_sufficiency(state, "C1", speaker="A", history=[("A", "CHALLENGE_PREMISE", ("C1",))])
        self.assertEqual(signal, SupportSufficiency.WEAK)

    def test_explicit_support_is_sufficient(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "결론"},
            {"op": "ADD_PROPOSITION", "temp_id": "P2", "text": "직접 근거"},
            {"op": "ADD_RELATION", "from_proposition_ref": "P2", "to_proposition_ref": "P1", "relation_type": "SUPPORTS"},
        ]}, speaker="B", turn=1)
        self.assertEqual(support_sufficiency(state, "C1", speaker="A", history=[]), SupportSufficiency.SUFFICIENT)

    def test_attack_is_not_support_and_qualifier_is_weak(self):
        attacked = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "결론"},
            {"op": "ADD_PROPOSITION", "temp_id": "P2", "text": "반박"},
            {"op": "ADD_RELATION", "from_proposition_ref": "P2", "to_proposition_ref": "P1", "relation_type": "ATTACKS"},
        ]}, speaker="B", turn=1)
        self.assertEqual(support_sufficiency(attacked, "C1", speaker="A", history=[]), SupportSufficiency.NONE)
        qualified = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "결론"},
            {"op": "ADD_PROPOSITION", "temp_id": "P2", "text": "범위 제한"},
            {"op": "ADD_RELATION", "from_proposition_ref": "P2", "to_proposition_ref": "P1", "relation_type": "QUALIFIES"},
        ]}, speaker="B", turn=1)
        self.assertEqual(support_sufficiency(qualified, "C1", speaker="A", history=[]), SupportSufficiency.WEAK)

    def test_relationless_patch_remains_valid(self):
        result = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "독립 주장"}]}, speaker="A", turn=1)
        self.assertEqual(len(result.propositions), 1)
        self.assertEqual(result.relations, [])

    def test_prompt_contains_relation_semantics_and_temp_reference_rule(self):
        for phrase in ("Patch-local", "SUPPORTS", "이유", "ATTACKS", "동시에 참", "CONTRADICTS", "QUALIFIES", "implicit warrant", "단순 주제 유사성"):
            self.assertIn(phrase, PATCH_INSTRUCTIONS)

    def test_prompt_requires_semantic_progress_classification(self):
        from src.debate_engine.state_harness import PATCH_INSTRUCTIONS
        for label in ("SAME_POINT", "NEW_COUNTEREXAMPLE", "SAME_QUESTION", "semantic_anchor_ref"):
            self.assertIn(label, PATCH_INSTRUCTIONS)

    def test_extraction_context_contains_resolved_questions_and_semantic_facets(self):
        from src.debate_engine.state_harness import extraction_context
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "text": "핵심", "semantic_kind": "NEW_REASON"},
            {"op": "ASK_QUESTION", "core_proposition": "왜?"},
        ]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [{"op": "ANSWER_QUESTION", "question_id": "Q1", "response_status": "DIRECT", "resolution": "RESOLVED"}]}, speaker="B", turn=2)
        context = extraction_context(state)
        self.assertEqual(context["questions"][0]["resolution"], "RESOLVED")
        self.assertEqual(context["facets"][0]["representative_id"], "C1")


if __name__ == "__main__":
    unittest.main()
