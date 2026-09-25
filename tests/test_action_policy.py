import unittest

from src.debate_engine.action_policy import eligible_actions, select_action, select_action_for_speaker
from src.debate_engine.debate_contracts import DebateState, apply_patch


class ActionPolicyTests(unittest.TestCase):
    def test_opening_action_has_no_target(self):
        options = eligible_actions(DebateState(), "A", "opening")
        self.assertEqual(options[0].name, "EXTEND_ARGUMENT")
        self.assertEqual(options[0].target_ids, ())

    def test_both_speakers_can_take_opening_action(self):
        options = eligible_actions(DebateState(), "B", "opening")
        previous = [("A", "EXTEND_ARGUMENT", ())]
        selected = select_action_for_speaker(options, previous, "B")
        self.assertEqual(selected.name, "EXTEND_ARGUMENT")

    def test_crossfire_targets_existing_opponent_proposition(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": "상대 주장"}]}, speaker="B", turn=1)
        options = eligible_actions(state, "A", "crossfire")
        self.assertTrue(options)
        self.assertTrue(all(target in {p.id for p in state.propositions} for option in options for target in option.target_ids if target.startswith("C")))
        selected = select_action(options, [])
        self.assertIn(selected.name, {option.name for option in options})

    def test_repeated_action_target_is_skipped(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": "상대 주장"}]}, speaker="B", turn=1)
        options = eligible_actions(state, "A", "crossfire")
        first = select_action(options, [])
        second = select_action(options, [(first.name, first.target_ids)])
        self.assertNotEqual((first.name, first.target_ids), (second.name, second.target_ids))

    def test_answer_open_question_is_bound_to_question_target(self):
        from src.debate_engine.debate_control import plan_turn_task
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "text": "A의 핵심 주장", "semantic_kind": "NEW_REASON"},
        ]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [
            {"op": "ASK_QUESTION", "core_proposition": "그 주장의 근거는?", "target_proposition_id": "C1", "semantic_kind": "NEW_QUESTION"},
        ]}, speaker="B", turn=2)
        task = plan_turn_task(state, speaker="A", phase="crossfire")
        options = eligible_actions(state, "A", "crossfire", turn_task=task)
        self.assertEqual({option.name for option in options}, {"DEFEND_CLAIM", "REVISE_CLAIM"})
        self.assertTrue(all(option.target_ids == ("C1",) for option in options))

    def test_noncomparative_audience_task_does_not_force_weighing(self):
        from src.debate_engine.debate_control import TurnTask, TurnTaskKind
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "text": "A 이유", "semantic_kind": "NEW_REASON"},
        ]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [
            {"op": "ADD_PROPOSITION", "text": "B 이유", "semantic_kind": "NEW_REASON"},
        ]}, speaker="B", turn=2)
        task = TurnTask(TurnTaskKind.ADDRESS_AUDIENCE, (), "관객 입력에 직접 답하세요: 볶는 방식도 있나요?")
        options = eligible_actions(state, "A", "audience_response", turn_task=task)
        self.assertNotIn("WEIGH_COMPARATIVE", {option.name for option in options})

    def test_comparative_audience_task_may_use_weighing(self):
        from src.debate_engine.debate_control import TurnTask, TurnTaskKind
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "text": "A 이유", "semantic_kind": "NEW_REASON"},
        ]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [
            {"op": "ADD_PROPOSITION", "text": "B 이유", "semantic_kind": "NEW_REASON"},
        ]}, speaker="B", turn=2)
        task = TurnTask(TurnTaskKind.ADDRESS_AUDIENCE, (), "두 방식 중 어느 쪽이 더 중요한가요?")
        options = eligible_actions(state, "A", "audience_response", turn_task=task)
        self.assertIn("WEIGH_COMPARATIVE", {option.name for option in options})

    def test_press_requires_partial_or_evaded_open_question(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ASK_QUESTION", "core_proposition": "왜?"}]}, speaker="A", turn=1)
        self.assertFalse(any(option.name == "PRESS_UNANSWERED" for option in eligible_actions(state, "A", "crossfire")))
        state = apply_patch(state, {"operations": [{"op": "ANSWER_QUESTION", "question_id": "Q1", "response_status": "PARTIAL", "resolution": "OPEN"}]}, speaker="B", turn=2)
        self.assertTrue(any(option.name == "PRESS_UNANSWERED" for option in eligible_actions(state, "A", "crossfire")))


if __name__ == "__main__":
    unittest.main()
