import unittest

from src.debate_engine.action_policy import eligible_actions
from src.debate_engine.debate_contracts import DebateState, apply_patch
from src.debate_engine.debate_control import TurnTask, TurnTaskKind


class ProgressAwarePolicyTests(unittest.TestCase):
    def _two_sides(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": "A 이유"}]}, speaker="A", turn=1)
        return apply_patch(state, {"operations": [{"op": "ADD_PROPOSITION", "text": "B 이유"}]}, speaker="B", turn=2)

    def test_weigh_task_yields_weighing_candidate_in_crossfire(self):
        state = self._two_sides()
        task = TurnTask(TurnTaskKind.WEIGH_COMPETING_REASONS, ("C2", "C1"), "두 이유를 직접 비교")
        options = eligible_actions(state, "A", "crossfire", turn_task=task)
        self.assertTrue(any(x.name == "WEIGH_COMPARATIVE" and len(x.target_ids) == 2 for x in options))
        self.assertFalse(any(x.name == "REQUEST_SUPPORT" for x in options))

    def test_counterexample_task_allows_refute_or_concede_not_random_probe(self):
        state = self._two_sides()
        task = TurnTask(TurnTaskKind.ADDRESS_COUNTEREXAMPLE, ("C2",), "반례를 처리")
        names = {x.name for x in eligible_actions(state, "A", "crossfire", turn_task=task)}
        self.assertIn("REFUTE_CLAIM", names)
        self.assertIn("CONCEDE_LOCAL", names)
        self.assertNotIn("REQUEST_SUPPORT", names)

    def test_no_valuable_move_has_no_action_candidates(self):
        state = self._two_sides()
        task = TurnTask(TurnTaskKind.NO_VALUABLE_MOVE, (), "더 진행할 고가치 과제 없음")
        self.assertEqual(eligible_actions(state, "A", "crossfire", turn_task=task), [])

    def test_same_semantic_facet_cannot_bypass_action_target_history_with_new_id(self):
        from src.debate_engine.action_policy import select_action_for_speaker
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "text": "전체 조화가 중요하다", "semantic_kind": "NEW_REASON"},
        ]}, speaker="B", turn=1)
        state = apply_patch(state, {"operations": [
            {"op": "ADD_PROPOSITION", "text": "전체 과정 안정성이 중요하다", "semantic_kind": "SAME_POINT", "semantic_anchor_ref": "C1"},
        ]}, speaker="B", turn=2)
        task = TurnTask(TurnTaskKind.TEST_UNRESOLVED_REASON, ("C2",), "같은 논지 검증")
        options = eligible_actions(state, "A", "crossfire", turn_task=task)
        selected = select_action_for_speaker(options, [("A", "CHALLENGE_PREMISE", ("C1",))], "A", state=state, current_turn=3, persona="Socratic")
        self.assertTrue(selected is None or selected.name != "CHALLENGE_PREMISE")

    def test_conceded_semantic_facet_is_not_reopened_through_duplicate_id(self):
        from src.debate_engine.action_policy import select_action_for_speaker
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "text": "찍먹은 바삭함을 오래 유지한다", "semantic_kind": "NEW_REASON"},
        ]}, speaker="B", turn=1)
        state = apply_patch(state, {"operations": [
            {"op": "CONCEDE_LOCAL", "proposition_id": "C1"},
        ]}, speaker="A", turn=2)
        state = apply_patch(state, {"operations": [
            {"op": "ADD_PROPOSITION", "text": "찍먹의 식감 유지 장점은 분명하다", "semantic_kind": "SAME_POINT", "semantic_anchor_ref": "C1"},
        ]}, speaker="B", turn=3)
        task = TurnTask(TurnTaskKind.TEST_UNRESOLVED_REASON, ("C2",), "이미 합의된 논지 재검증")
        options = eligible_actions(state, "A", "crossfire", turn_task=task)
        selected = select_action_for_speaker(options, [], "A", state=state, current_turn=4, persona="Falsifier")
        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
