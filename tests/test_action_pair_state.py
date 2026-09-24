import json
import unittest
from pathlib import Path

from src.debate_engine.action_pair_state import PairState, SupportSufficiency, evaluate_action_target_pair, filter_available_pairs
from src.debate_engine.action_policy import ActionCandidate, eligible_actions, select_action_for_speaker
from src.debate_engine.debate_contracts import DebateState, apply_patch


def claim_with_support(relation_type="SUPPORTS"):
    return apply_patch(DebateState(), {"operations": [
        {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "핵심 주장은 제도 효과가 있다."},
        {"op": "ADD_PROPOSITION", "temp_id": "P2", "text": "관찰된 사례가 핵심 주장을 뒷받침한다."},
        {"op": "ADD_RELATION", "from_proposition_ref": "P2", "to_proposition_ref": "P1", "relation_type": relation_type},
    ]}, speaker="B", turn=1)


class ActionPairStateTests(unittest.TestCase):
    def test_unsupported_claim_allows_request_support(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": "근거 없는 핵심 주장"}]}, speaker="B", turn=1)
        status = evaluate_action_target_pair(state, "A", "REQUEST_SUPPORT", "C1", [], current_turn=2)
        self.assertEqual(status.support_sufficiency, SupportSufficiency.NONE)
        self.assertEqual(status.state, PairState.AVAILABLE)

    def test_direct_support_resolves_request_support(self):
        status = evaluate_action_target_pair(claim_with_support(), "A", "REQUEST_SUPPORT", "C1", [], current_turn=2)
        self.assertEqual(status.support_sufficiency, SupportSufficiency.SUFFICIENT)
        self.assertEqual(status.state, PairState.RESOLVED)

    def test_weak_support_keeps_request_support_open(self):
        status = evaluate_action_target_pair(claim_with_support("QUALIFIES"), "A", "REQUEST_SUPPORT", "C1", [], current_turn=2)
        self.assertEqual(status.support_sufficiency, SupportSufficiency.WEAK)
        self.assertIn(status.state, (PairState.AVAILABLE, PairState.OPEN))

    def test_contested_support_prioritizes_challenge_inference(self):
        state = claim_with_support()
        state = apply_patch(state, {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "그 사례는 대표성이 없다."},
            {"op": "ADD_RELATION", "from_proposition_ref": "P1", "to_proposition_ref": "C2", "relation_type": "ATTACKS"},
        ]}, speaker="A", turn=2)
        request = evaluate_action_target_pair(state, "A", "REQUEST_SUPPORT", "C1", [], current_turn=3)
        self.assertEqual(request.support_sufficiency, SupportSufficiency.CONTESTED)
        options = [ActionCandidate("REQUEST_SUPPORT", ("C1",)), ActionCandidate("CHALLENGE_INFERENCE", ("C1",))]
        selected = select_action_for_speaker(options, [], "A", state=state, current_turn=3)
        self.assertEqual(selected.name, "CHALLENGE_INFERENCE")

    def test_exhausted_pair_removed_without_removing_high_value_target(self):
        state = claim_with_support()
        options = filter_available_pairs(state, "A", [ActionCandidate("REQUEST_SUPPORT", ("C1",)), ActionCandidate("TEST_BOUNDARY", ("C1",))], [], current_turn=2)
        self.assertNotIn(ActionCandidate("REQUEST_SUPPORT", ("C1",)), options)
        self.assertIn(ActionCandidate("TEST_BOUNDARY", ("C1",)), options)

    def test_direct_answer_removes_press(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ASK_QUESTION", "text": "왜입니까?", "core_proposition": "이유"}]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [{"op": "ANSWER_QUESTION", "question_id": "Q1", "response_status": "DIRECT", "resolution": "RESOLVED"}]}, speaker="B", turn=2)
        status = evaluate_action_target_pair(state, "A", "PRESS_UNANSWERED", "Q1", [], current_turn=3)
        self.assertEqual(status.state, PairState.RESOLVED)

    def test_partial_answer_keeps_press_open(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ASK_QUESTION", "text": "왜입니까?", "core_proposition": "이유"}]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [{"op": "ANSWER_QUESTION", "question_id": "Q1", "response_status": "PARTIAL", "resolution": "OPEN"}]}, speaker="B", turn=2)
        status = evaluate_action_target_pair(state, "A", "PRESS_UNANSWERED", "Q1", [], current_turn=3)
        self.assertEqual(status.state, PairState.OPEN)

    def test_repaired_inconsistency_blocks_repeat(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": "모든 경우에 효과가 있다."}]}, speaker="B", turn=1)
        state = apply_patch(state, {"operations": [{"op": "REVISE_PROPOSITION", "old_proposition_id": "C1", "new_proposition_text": "일부 경우에 효과가 있다."}]}, speaker="B", turn=2)
        status = evaluate_action_target_pair(state, "A", "CHECK_CONSISTENCY", "C1", [("A", "CHECK_CONSISTENCY", ("C1",))], current_turn=3)
        self.assertIn(status.state, (PairState.RESOLVED, PairState.BLOCKED))

    def test_revision_does_not_reuse_old_pair_but_keeps_new_target(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": "모든 경우에 효과가 있다."}]}, speaker="B", turn=1)
        state = apply_patch(state, {"operations": [{"op": "REVISE_PROPOSITION", "old_proposition_id": "C1", "new_proposition_text": "일부 경우에 효과가 있다."}]}, speaker="B", turn=2)
        self.assertEqual(evaluate_action_target_pair(state, "A", "TEST_BOUNDARY", "C1", [], current_turn=3).state, PairState.BLOCKED)
        self.assertEqual(evaluate_action_target_pair(state, "A", "TEST_BOUNDARY", "C2", [], current_turn=3).state, PairState.AVAILABLE)

    def test_known_hotdog_and_attendance_request_support_are_resolved(self):
        for name in ("action_pair_hotdog_turn6.json", "action_pair_attendance_turn7.json"):
            fixture = json.loads(Path("etc", "fixtures", name).read_text(encoding="utf-8"))
            state = DebateState.model_validate(fixture["state"])
            history = [(owner, action, tuple(targets)) for owner, action, targets in fixture["action_history"]]
            status = evaluate_action_target_pair(state, fixture["speaker"], fixture["action"], fixture["target_id"], history, current_turn=fixture["turn_id"])
            self.assertEqual(status.state, PairState.RESOLVED, name)
            options = filter_available_pairs(state, fixture["speaker"], eligible_actions(state, fixture["speaker"], "crossfire"), history, current_turn=fixture["turn_id"])
            self.assertNotIn(ActionCandidate("REQUEST_SUPPORT", (fixture["target_id"],)), options)
            self.assertTrue(any(option.target_ids == (fixture["target_id"],) for option in options))


if __name__ == "__main__":
    unittest.main()
