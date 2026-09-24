import unittest

from src.debate_engine.debate_contracts import DebateState
from etc.tools.integrated_debate import build_integration_schedule, commit_turn, state_integrity_issues
from src.debate_engine.stance_compliance import StanceAssignment, StanceAssessment, StanceLabel, finalize_utterance


class SemanticRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.assignment = StanceAssignment("A안", "B안")

    def test_local_concession_passes(self):
        speech = "상대가 초기 비용 문제에서는 맞습니다. 하지만 장기 효과를 고려하면 저는 여전히 A안을 지지합니다."
        result = finalize_utterance(lambda _: speech, self.assignment, phase="crossfire", semantic_check=lambda *_: StanceAssessment(StanceLabel.COMPATIBLE_WITH_ASSIGNED, True, "local concession"))
        self.assertTrue(result.committed)
        self.assertEqual(result.assessment.label, StanceLabel.COMPATIBLE_WITH_ASSIGNED)

    def test_subclaim_revision_passes(self):
        speech = "모든 경우에 효과적이라는 제 주장은 너무 넓었습니다. 대규모 조직에 한정하겠습니다. 그래도 제 최종 입장은 A안."
        result = finalize_utterance(lambda _: speech, self.assignment, phase="rebuttal", semantic_check=lambda *_: StanceAssessment(StanceLabel.COMPATIBLE_WITH_ASSIGNED, True, "subclaim revision"))
        self.assertTrue(result.committed)

    def test_explicit_reversal_rejected(self):
        result = finalize_utterance(lambda _: "결국 B안이 더 타당합니다.", self.assignment, phase="final_focus", semantic_check=lambda *_: StanceAssessment(StanceLabel.SUPPORTS_ASSIGNED, True, "bad semantic verdict"))
        self.assertFalse(result.committed)
        self.assertEqual(result.attempts, 2)

    def test_semantic_paraphrase_rejected(self):
        speech = "초기 비용을 감수하더라도 장기 선택은 각자가 결정하는 편이 더 옳습니다."
        result = finalize_utterance(lambda _: speech, self.assignment, phase="rebuttal", semantic_check=lambda *_: StanceAssessment(StanceLabel.CONTRADICTS_ASSIGNED, False, "opposing thesis by meaning"))
        self.assertFalse(result.committed)

    def test_ambiguous_final_rejected(self):
        result = finalize_utterance(lambda _: "결국 양쪽 모두 비슷하게 타당합니다.", self.assignment, phase="final_focus", semantic_check=lambda *_: StanceAssessment(StanceLabel.AMBIGUOUS, False, "no final position"))
        self.assertFalse(result.committed)

    def test_ambiguous_crossfire_rejected_with_semantic_guard(self):
        result = finalize_utterance(lambda _: "양쪽 모두 비슷합니다.", self.assignment, phase="crossfire", semantic_check=lambda *_: StanceAssessment(StanceLabel.AMBIGUOUS, False, "unclear"))
        self.assertFalse(result.committed)

    def test_repeated_violation_leaves_state_unchanged_and_skips_patch(self):
        state = DebateState()
        patch_calls = []
        result = commit_turn(state, lambda _: "결국 B안이 더 타당합니다.", self.assignment, phase="final_focus", semantic_check=lambda *_: StanceAssessment(StanceLabel.CONTRADICTS_ASSIGNED, False, "reversal"), extract_patch=lambda *_: patch_calls.append(1))
        self.assertFalse(result["committed"])
        self.assertEqual(state.model_dump(), DebateState().model_dump())
        self.assertEqual(patch_calls, [])

    def test_failed_patch_after_stance_pass_leaves_state_unchanged(self):
        from src.debate_engine.debate_contracts import apply_patch
        state = DebateState()

        def invalid_patch(speech, prior):
            return apply_patch(prior, {"operations": [{"op": "ASK_QUESTION", "core_proposition": "왜?", "target_proposition_id": "C404"}]}, speaker="A", turn=1), []

        result = commit_turn(state, lambda _: "제 최종 입장은 A안.", self.assignment, phase="final_focus", semantic_check=lambda *_: StanceAssessment(StanceLabel.SUPPORTS_ASSIGNED, True, "assigned"), extract_patch=invalid_patch)
        self.assertFalse(result["committed"])
        self.assertEqual(result["patch_error"][0]["code"], "missing_entity")
        self.assertEqual(state.model_dump(), DebateState().model_dump())

    def test_all_debate_phases_require_semantic_check(self):
        for phase in ("opening", "crossfire", "rebuttal", "final_focus", "audience_response"):
            with self.subTest(phase=phase):
                calls = []
                result = finalize_utterance(lambda _: "A안", self.assignment, phase=phase, semantic_check=lambda *_: (calls.append(1), StanceAssessment(StanceLabel.SUPPORTS_ASSIGNED, True, "okay"))[1])
                self.assertTrue(result.committed)
                self.assertEqual(calls, [1])

    def test_integration_schedule_has_hard_budget(self):
        scenario = {"sides": ["A안", "B안"], "personas": ["Socratic", "Pragmatist"]}
        schedule = build_integration_schedule(scenario, 6)
        self.assertEqual(len(schedule), 10)
        self.assertEqual([row["phase"] for row in schedule[:2]], ["opening", "opening"])
        self.assertEqual([row["phase"] for row in schedule[-2:]], ["rebuttal", "rebuttal"])

    def test_state_integrity_catches_dangling_reference(self):
        from src.debate_engine.debate_contracts import Relation
        state = DebateState(relations=[Relation(id="R1", from_proposition_id="C1", to_proposition_id="C2", relation_type="ATTACKS")])
        self.assertIn("dangling_relation:R1", state_integrity_issues(state))


if __name__ == "__main__":
    unittest.main()
