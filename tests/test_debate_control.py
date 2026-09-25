import unittest

from src.debate_engine.debate_contracts import DebateState, apply_patch
from src.debate_engine.debate_control import (
    ProgressType,
    TurnTaskKind,
    build_control_view,
    plan_turn_task,
)


class DebateControlTests(unittest.TestCase):
    def test_same_point_new_id_stays_in_same_facet_and_is_not_progress(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "한 접시 전체의 조화가 중요하다.", "semantic_kind": "NEW_REASON"},
        ]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "전체 과정의 안정성이 중요하다.", "semantic_kind": "SAME_POINT", "semantic_anchor_ref": "C1"},
        ]}, speaker="A", turn=2)
        view = build_control_view(state)
        self.assertEqual(view.proposition_to_facet["C1"], view.proposition_to_facet["C2"])
        self.assertIn(ProgressType.REPHRASE, view.progress_by_turn[2])
        self.assertNotIn(ProgressType.NEW_REASON, view.progress_by_turn[2])

    def test_new_counterexample_is_real_progress_and_new_facet(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "부먹은 끝까지 균일하다.", "semantic_kind": "NEW_REASON"},
        ]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [
            {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "바닥과 위쪽 조각은 시간에 따라 다르게 변한다.", "semantic_kind": "NEW_COUNTEREXAMPLE", "semantic_anchor_ref": "C1"},
        ]}, speaker="B", turn=2)
        view = build_control_view(state)
        self.assertNotEqual(view.proposition_to_facet["C1"], view.proposition_to_facet["C2"])
        self.assertIn(ProgressType.NEW_COUNTEREXAMPLE, view.progress_by_turn[2])

    def test_repeated_resolved_question_does_not_reopen_question_state(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ASK_QUESTION", "core_proposition": "왜 전체 조화가 더 중요한가?", "semantic_kind": "NEW_QUESTION"},
        ]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [
            {"op": "ANSWER_QUESTION", "question_id": "Q1", "response_status": "DIRECT", "resolution": "RESOLVED"},
        ]}, speaker="B", turn=2)
        state = apply_patch(state, {"operations": [
            {"op": "ASK_QUESTION", "core_proposition": "왜 전체 안정성이 우선인가?", "semantic_kind": "SAME_QUESTION", "anchor_question_id": "Q1"},
        ]}, speaker="A", turn=3)
        self.assertEqual(len(state.questions), 1)
        self.assertEqual(state.questions[0].resolution, "RESOLVED")
        view = build_control_view(state)
        self.assertIn(ProgressType.REOPEN_RESOLVED, view.progress_by_turn[3])

    def test_open_question_is_highest_priority_turn_task(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "text": "A 이유", "semantic_kind": "NEW_REASON"},
            {"op": "ASK_QUESTION", "core_proposition": "왜 그런가?", "target_proposition_id": "C1", "semantic_kind": "NEW_QUESTION"},
        ]}, speaker="A", turn=1)
        task = plan_turn_task(state, speaker="B", phase="crossfire")
        self.assertEqual(task.kind, TurnTaskKind.ANSWER_OPEN_QUESTION)
        self.assertEqual(task.target_ids, ("Q1",))

    def test_audience_question_overrides_existing_agenda(self):
        task = plan_turn_task(DebateState(), speaker="A", phase="audience_response", audience_question="볶는다는 것도 있어")
        self.assertEqual(task.kind, TurnTaskKind.ADDRESS_AUDIENCE)
        self.assertIn("볶는다는 것도 있어", task.description)

    def test_two_rephrase_only_turns_trigger_weigh_not_more_probe(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ADD_PROPOSITION", "text": "전체 조화", "semantic_kind": "NEW_REASON"},
        ]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [
            {"op": "ADD_PROPOSITION", "text": "선택권", "semantic_kind": "NEW_REASON"},
        ]}, speaker="B", turn=2)
        state = apply_patch(state, {"operations": [
            {"op": "ADD_PROPOSITION", "text": "전체 과정 안정성", "semantic_kind": "SAME_POINT", "semantic_anchor_ref": "C1"},
        ]}, speaker="A", turn=3)
        state = apply_patch(state, {"operations": [
            {"op": "ADD_PROPOSITION", "text": "개인별 선택 유지", "semantic_kind": "SAME_POINT", "semantic_anchor_ref": "C2"},
        ]}, speaker="B", turn=4)
        task = plan_turn_task(state, speaker="A", phase="crossfire")
        self.assertEqual(task.kind, TurnTaskKind.WEIGH_COMPETING_REASONS)
        self.assertEqual(len(task.target_ids), 2)

    def test_final_focus_is_always_crystallize_even_when_questions_remain(self):
        state = apply_patch(DebateState(), {"operations": [
            {"op": "ASK_QUESTION", "core_proposition": "남은 질문", "semantic_kind": "NEW_QUESTION"},
        ]}, speaker="B", turn=3)
        task = plan_turn_task(state, speaker="A", phase="final_focus")
        self.assertEqual(task.kind, TurnTaskKind.CRYSTALLIZE)

    def test_agreed_facets_do_not_keep_crossfire_alive(self):
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": "A 이유", "semantic_kind": "NEW_REASON"}]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [{"op": "ADD_PROPOSITION", "text": "B 이유", "semantic_kind": "NEW_REASON"}]}, speaker="B", turn=2)
        state = apply_patch(state, {"operations": [{"op": "CONCEDE_LOCAL", "proposition_id": "C2"}]}, speaker="A", turn=3)
        state = apply_patch(state, {"operations": [{"op": "CONCEDE_LOCAL", "proposition_id": "C1"}]}, speaker="B", turn=4)
        task = plan_turn_task(state, speaker="A", phase="crossfire")
        self.assertEqual(task.kind, TurnTaskKind.NO_VALUABLE_MOVE)


if __name__ == "__main__":
    unittest.main()
