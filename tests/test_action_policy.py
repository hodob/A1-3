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

    def test_press_requires_partial_or_evaded_open_question(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ASK_QUESTION", "core_proposition": "왜?"}]}, speaker="A", turn=1)
        self.assertFalse(any(option.name == "PRESS_UNANSWERED" for option in eligible_actions(state, "A", "crossfire")))
        state = apply_patch(state, {"operations": [{"op": "ANSWER_QUESTION", "question_id": "Q1", "response_status": "PARTIAL", "resolution": "OPEN"}]}, speaker="B", turn=2)
        self.assertTrue(any(option.name == "PRESS_UNANSWERED" for option in eligible_actions(state, "A", "crossfire")))


if __name__ == "__main__":
    unittest.main()
