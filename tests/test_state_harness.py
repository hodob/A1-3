import unittest

from src.debate_engine.debate_contracts import DebateState, PatchEnvelope, PatchValidationError, apply_patch
from src.debate_engine.provider_adapter import ProviderOutputError
from src.debate_engine.state_harness import PATCH_INSTRUCTIONS, extract_and_apply, extraction_context


class StateHarnessTests(unittest.TestCase):
    def test_extraction_prompt_avoids_duplicate_concession_and_rhetorical_nodes(self):
        self.assertIn("CONCEDE_LOCAL", PATCH_INSTRUCTIONS)
        self.assertIn("비유", PATCH_INSTRUCTIONS)
        self.assertIn("합치지", PATCH_INSTRUCTIONS)
        self.assertIn("ASK_QUESTION", PATCH_INSTRUCTIONS)
        self.assertIn("빠뜨리지", PATCH_INSTRUCTIONS)

    def test_extraction_prompt_understands_state_reference_markers(self):
        self.assertIn("[[C24]]", PATCH_INSTRUCTIONS)
        self.assertIn("citation marker", PATCH_INSTRUCTIONS)
        self.assertIn("selected_target_ids", PATCH_INSTRUCTIONS)

    def test_extraction_context_is_bounded_but_keeps_current_facets_and_targets(self):
        state = DebateState()
        state = apply_patch(state, {"operations": [
            {"op": "ADD_PROPOSITION", "text": "A root", "semantic_kind": "NEW_REASON"},
            {"op": "ADD_PROPOSITION", "text": "B root", "semantic_kind": "NEW_REASON"},
        ]}, speaker="A", turn=1)
        for turn in range(2, 14):
            state = apply_patch(state, {"operations": [
                {
                    "op": "ADD_PROPOSITION",
                    "text": f"A refinement {turn}",
                    "semantic_kind": "REFINEMENT",
                    "semantic_anchor_ref": "C1",
                }
            ]}, speaker="A", turn=turn)
        context = extraction_context(state, {"action": "DEFEND_CLAIM", "target_ids": ["C2"]})
        ids = {item["id"] for item in context["propositions"]}
        self.assertIn("C2", ids)
        self.assertIn("C1", ids)
        self.assertLess(len(context["propositions"]), len(state.propositions))
        self.assertEqual(context["selected_action"], "DEFEND_CLAIM")
        self.assertEqual(context["selected_target_ids"], ["C2"])

    def test_question_extraction_prompt_groups_one_immediate_qud(self):
        self.assertIn("Immediate QUD", PATCH_INSTRUCTIONS)
        self.assertIn("ASK_QUESTION 하나만", PATCH_INSTRUCTIONS)
        self.assertIn("질문표('?') 개수", PATCH_INSTRUCTIONS)

    def test_adaptive_context_caps_large_unrelated_state(self):
        state = DebateState()
        for turn in range(1, 21):
            state = apply_patch(state, {"operations": [
                {"op": "ADD_PROPOSITION", "text": f"독립 주장 {turn}", "semantic_kind": "NEW_REASON"},
            ]}, speaker="A" if turn % 2 else "B", turn=turn)
        context = extraction_context(
            state,
            {
                "speaker": "A",
                "action": "CHALLENGE_PREMISE",
                "target_ids": ["C2"],
                "reference_ids": ["C3"],
            },
        )
        ids = {item["id"] for item in context["propositions"]}
        self.assertIn("C2", ids)
        self.assertIn("C3", ids)
        self.assertLessEqual(len(context["propositions"]), 10)
        self.assertLess(len(context["propositions"]), len(state.propositions))
        self.assertEqual(context["working_set"]["immediate_qud_id"], None)
        self.assertIn("explicit_target_or_reference", context["working_set"]["reasons"]["C2"])

    def test_adaptive_context_keeps_immediate_qud_target(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "text": "A 주장", "semantic_kind": "NEW_REASON"},
        ]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [
            {"op": "ASK_QUESTION", "core_proposition": "근거는?", "target_proposition_id": "C1", "semantic_kind": "NEW_QUESTION"},
        ]}, speaker="B", turn=2)
        context = extraction_context(state, {"speaker": "A", "action": "DEFEND_CLAIM", "target_ids": ["C1"]})
        self.assertEqual(context["working_set"]["immediate_qud_id"], "QG-Q1")
        self.assertIn("Q1", {q["id"] for q in context["questions"]})
        self.assertIn("C1", {p["id"] for p in context["propositions"]})

    def test_invalid_model_patch_gets_one_validated_retry(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": "기존 주장"}]}, speaker="A", turn=1)
        candidates = [
            {"operations": [{"op": "ADD_RELATION", "from_proposition_id": "Q1", "to_proposition_id": "C1", "relation_type": "ATTACKS"}]},
            {"operations": [{"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "반론"}, {"op": "ADD_RELATION", "from_proposition_ref": "P1", "to_proposition_ref": "C1", "relation_type": "ATTACKS"}]},
        ]
        feedback_seen = []

        # The first candidate fails local schema validation before extraction returns.
        def validating_extractor(feedback):
            feedback_seen.append(feedback)
            try:
                return PatchEnvelope.model_validate(candidates.pop(0)), {}
            except Exception:
                raise ProviderOutputError("local_validation_failed", [{"loc": ["operations", 0, "from_proposition_id"], "msg": "Q ID is not a proposition"}])

        result, attempts = extract_and_apply(state, "B", 2, validating_extractor)
        self.assertEqual(len(feedback_seen), 2)
        self.assertEqual(feedback_seen[1][0]["code"], "local_validation_failed")
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len(result.propositions), 2)
        self.assertEqual(len(result.relations), 1)
        self.assertEqual(len(state.propositions), 1)

    def test_failed_repair_leaves_original_state(self):
        state = DebateState()

        def extractor(feedback):
            return PatchEnvelope.model_validate({"operations": [{"op": "ASK_QUESTION", "core_proposition": "왜?", "target_proposition_id": "C404"}]}), {}

        with self.assertRaises(PatchValidationError):
            extract_and_apply(state, "A", 1, extractor)
        self.assertEqual(state.model_dump(), DebateState().model_dump())


if __name__ == "__main__":
    unittest.main()
