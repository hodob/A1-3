import json
import unittest
from pathlib import Path

from src.debate_engine.action_policy import eligible_actions, select_action_for_speaker
from src.debate_engine.debate_contracts import DebateState, apply_patch
from src.debate_engine.target_quality import Actionability, derive_target_metadata


class TargetQualityTests(unittest.TestCase):
    def test_c40_rhetorical_fixture_is_classified_rhetorical(self):
        item = json.loads(Path("etc/fixtures/rhetorical_target_c40.json").read_text(encoding="utf-8"))
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": item["text"]}]}, speaker="B", turn=8)
        metadata = derive_target_metadata(state, "C1", current_turn=9, action_history=[])
        self.assertEqual(metadata.actionability, Actionability.RHETORICAL)

    def test_core_target_ranks_ahead_of_rhetorical_target(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "text": "출석 의무화는 학습 공동체의 최소 참여를 보장해야 한다."},
            {"op": "ADD_PROPOSITION", "text": "비유하자면 출석표는 교실의 체온계와 같다."},
        ]}, speaker="B", turn=1)
        options = eligible_actions(state, "A", "crossfire")
        selected = select_action_for_speaker(options, [], "A", state=state, current_turn=2)
        self.assertEqual(selected.target_ids, ("C1",))

    def test_superseded_target_is_penalized(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": "모든 학생에게 효과가 있다."}]}, speaker="B", turn=1)
        state = apply_patch(state, {"operations": [{"op": "REVISE_PROPOSITION", "old_proposition_id": "C1", "new_proposition_text": "일부 학생에게 효과가 있다."}]}, speaker="B", turn=2)
        options = eligible_actions(state, "A", "crossfire")
        selected = select_action_for_speaker(options, [], "A", state=state, current_turn=3)
        self.assertEqual(selected.target_ids, ("C2",))


if __name__ == "__main__":
    unittest.main()
