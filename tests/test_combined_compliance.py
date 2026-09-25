import unittest

from src.debate_engine.combined_compliance import CombinedComplianceAssessment, TaskFidelityLabel, finalize_compliant_utterance
from src.debate_engine.action_fidelity import ActionFidelityLabel
from src.debate_engine.stance_compliance import StanceAssignment, StanceLabel
from src.debate_engine.debate_contracts import DebateState
from etc.tools.integrated_debate import commit_guarded_turn


class CombinedComplianceTests(unittest.TestCase):
    def setUp(self):
        self.assignment = StanceAssignment("A안", "B안")

    def test_partial_action_and_compatible_stance_are_accepted_with_flag(self):
        assessment = CombinedComplianceAssessment(ActionFidelityLabel.PARTIALLY_ALIGNED, StanceLabel.COMPATIBLE_WITH_ASSIGNED, "일부 수행", "양보 후 유지")
        result = finalize_compliant_utterance(lambda _: "발언", self.assignment, "CHALLENGE_PREMISE", "target", "crossfire", lambda *_: assessment)
        self.assertTrue(result.committed)
        self.assertTrue(result.diagnostic_flag)

    def test_misaligned_action_regenerates_once(self):
        verdicts = iter([
            CombinedComplianceAssessment(ActionFidelityLabel.MISALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "다른 target", "유지"),
            CombinedComplianceAssessment(ActionFidelityLabel.ALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "수행", "유지"),
        ])
        prompts = []
        result = finalize_compliant_utterance(lambda feedback: (prompts.append(feedback), "발언")[1], self.assignment, "CHALLENGE_PREMISE", "target", "crossfire", lambda *_: next(verdicts))
        self.assertTrue(result.committed)
        self.assertEqual(result.attempts, 2)
        self.assertIn("ACTION_NOT_PERFORMED", prompts[1])

    def test_repeated_action_failure_is_safe(self):
        bad = CombinedComplianceAssessment(ActionFidelityLabel.MISALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "target 지지", "유지")
        result = finalize_compliant_utterance(lambda _: "발언", self.assignment, "CHALLENGE_PREMISE", "target", "crossfire", lambda *_: bad)
        self.assertFalse(result.committed)
        self.assertEqual(result.attempts, 3)

    def test_ambiguous_stance_regenerates(self):
        bad = CombinedComplianceAssessment(ActionFidelityLabel.ALIGNED, StanceLabel.AMBIGUOUS, "수행", "입장 불명")
        result = finalize_compliant_utterance(lambda _: "발언", self.assignment, "CRYSTALLIZE", None, "final_focus", lambda *_: bad)
        self.assertFalse(result.committed)

    def test_repeated_fidelity_failure_skips_patch_and_state_change(self):
        bad = CombinedComplianceAssessment(ActionFidelityLabel.MISALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "target 지지", "유지")
        patch_calls = []
        state = DebateState()
        result = commit_guarded_turn(state, lambda _: "발언", self.assignment, action="CHALLENGE_PREMISE", target_text="target", phase="crossfire", combined_check=lambda *_: bad, extract_patch=lambda *_: patch_calls.append(1))
        self.assertFalse(result["committed"])
        self.assertEqual(patch_calls, [])
        self.assertEqual(result["state"].model_dump(), state.model_dump())

    def test_rephrase_only_is_rejected_when_turn_task_requires_progress(self):
        bad = CombinedComplianceAssessment(
            ActionFidelityLabel.ALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "action ok", "stance ok",
            task_fidelity=TaskFidelityLabel.REPHRASES_ONLY, task_reason="same point again",
        )
        result = finalize_compliant_utterance(
            lambda _: "같은 말을 다시 합니다.", self.assignment, "CRYSTALLIZE", None, "final_focus", lambda *_: bad,
            turn_task="WEIGH_COMPETING_REASONS",
        )
        self.assertFalse(result.committed)
        self.assertEqual(result.attempts, 3)


    def test_retry_feedback_contains_typed_code_and_previous_draft(self):
        verdicts = iter([
            CombinedComplianceAssessment(ActionFidelityLabel.MISALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "wrong action", "stance ok"),
            CombinedComplianceAssessment(ActionFidelityLabel.ALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "ok", "ok"),
        ])
        prompts = []
        result = finalize_compliant_utterance(
            lambda feedback: (prompts.append(feedback), "첫 발언" if len(prompts) == 1 else "수정 발언")[1],
            self.assignment,
            "CHALLENGE_PREMISE",
            "target",
            "crossfire",
            lambda *_: next(verdicts),
        )
        self.assertTrue(result.committed)
        self.assertIn("ACTION_NOT_PERFORMED", prompts[1])
        self.assertIn("<previous_draft>첫 발언</previous_draft>", prompts[1])
        self.assertIn("<retry_strategy>TARGETED_REPAIR</retry_strategy>", prompts[1])

    def test_compliance_callback_records_rejections_and_acceptance(self):
        verdicts = iter([
            CombinedComplianceAssessment(ActionFidelityLabel.MISALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "wrong", "ok"),
            CombinedComplianceAssessment(ActionFidelityLabel.ALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "ok", "ok"),
        ])
        checks = []
        result = finalize_compliant_utterance(
            lambda _: "발언",
            self.assignment,
            "CHALLENGE_PREMISE",
            "target",
            "crossfire",
            lambda *_: next(verdicts),
            on_check=checks.append,
        )
        self.assertTrue(result.committed)
        self.assertEqual([x["accepted"] for x in checks], [False, True])
        self.assertIn("ACTION_NOT_PERFORMED", checks[0]["failure_codes"])

    def test_direct_response_task_accepts_partial_secondary_action(self):
        partial = CombinedComplianceAssessment(
            ActionFidelityLabel.PARTIALLY_ALIGNED,
            StanceLabel.SUPPORTS_ASSIGNED,
            "질문 답변이 중심이고 secondary action은 일부 수행",
            "stance ok",
            primary_action_performed=True,
            target_used=False,
            action_is_core_function=False,
            additional_move_protocol_compliant=True,
            task_fidelity=TaskFidelityLabel.ADVANCES_TASK,
            task_reason="질문에 직접 답함",
        )
        result = finalize_compliant_utterance(
            lambda _: "직접 답변",
            self.assignment,
            "WEIGH_COMPARATIVE",
            "target",
            "crossfire",
            lambda *_: partial,
            turn_task="ANSWER_OPEN_QUESTION",
        )
        self.assertTrue(result.committed)
        self.assertEqual(result.attempts, 1)

    def test_task_primary_accepts_misaligned_secondary_action_when_task_advances(self):
        assessment = CombinedComplianceAssessment(
            ActionFidelityLabel.MISALIGNED,
            StanceLabel.SUPPORTS_ASSIGNED,
            "secondary action was not performed",
            "stance ok",
            task_fidelity=TaskFidelityLabel.ADVANCES_TASK,
            task_reason="직접 질문에 답함",
        )
        result = finalize_compliant_utterance(
            lambda _: "질문에 직접 답합니다.",
            self.assignment,
            "WEIGH_COMPARATIVE",
            "target",
            "crossfire",
            lambda *_: assessment,
            turn_task="ANSWER_OPEN_QUESTION",
        )
        self.assertTrue(result.committed)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.checks[0]["failure_codes"], [])

    def test_repair_prompt_contains_observed_location_and_admissible_repairs(self):
        verdicts = iter([
            CombinedComplianceAssessment(
                ActionFidelityLabel.MISALIGNED,
                StanceLabel.SUPPORTS_ASSIGNED,
                "target comparison missing",
                "stance ok",
                task_fidelity=TaskFidelityLabel.OFF_TASK,
                task_reason="question was not answered",
            ),
            CombinedComplianceAssessment(
                ActionFidelityLabel.ALIGNED,
                StanceLabel.SUPPORTS_ASSIGNED,
                "ok",
                "ok",
                task_fidelity=TaskFidelityLabel.ADVANCES_TASK,
                task_reason="ok",
            ),
        ])
        prompts = []
        result = finalize_compliant_utterance(
            lambda feedback: (prompts.append(feedback), "draft")[1],
            self.assignment,
            "WEIGH_COMPARATIVE",
            "target",
            "crossfire",
            lambda *_: next(verdicts),
            turn_task="WEIGH_COMPETING_REASONS",
        )
        self.assertTrue(result.committed)
        self.assertIn('location="action_execution"', prompts[1])
        self.assertIn("<observed>target comparison missing</observed>", prompts[1])
        self.assertIn("<allowed_repairs>", prompts[1])
        self.assertIn("<forbidden>", prompts[1])

    def test_third_attempt_can_replan_after_repeated_task_action_conflict(self):
        bad = CombinedComplianceAssessment(
            ActionFidelityLabel.PARTIALLY_ALIGNED,
            StanceLabel.SUPPORTS_ASSIGNED,
            "action not core",
            "stance ok",
            primary_action_performed=True,
            target_used=True,
            action_is_core_function=False,
            additional_move_protocol_compliant=True,
            task_fidelity=TaskFidelityLabel.ADVANCES_TASK,
            task_reason="task advanced",
        )
        good = CombinedComplianceAssessment(
            ActionFidelityLabel.ALIGNED,
            StanceLabel.SUPPORTS_ASSIGNED,
            "new action aligned",
            "stance ok",
            task_fidelity=TaskFidelityLabel.ADVANCES_TASK,
            task_reason="task advanced",
        )
        verdicts = iter([bad, bad, good])
        prompts = []
        semantic_actions = []
        replans = []

        def semantic(*args):
            semantic_actions.append(args[3])
            return next(verdicts)

        def replan(check):
            replans.append(check["failure_codes"])
            return ("DEFEND_CLAIM", "new target")

        result = finalize_compliant_utterance(
            lambda feedback: (prompts.append(feedback), f"draft-{len(prompts)}")[1],
            self.assignment,
            "WEIGH_COMPARATIVE",
            "old target",
            "crossfire",
            semantic,
            turn_task="TEST_UNRESOLVED_REASON",
            on_replan=replan,
        )
        self.assertTrue(result.committed)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(len(replans), 1)
        self.assertIn("TASK_ACTION_CONFLICT", replans[0])
        self.assertEqual(semantic_actions[-1], "DEFEND_CLAIM")
        self.assertIn("REPLAN_AND_REGENERATE", prompts[2])
        self.assertIn("<action>DEFEND_CLAIM</action>", prompts[2])

    def test_local_surface_failure_skips_semantic_call_then_repairs(self):
        semantic_calls = []
        prompts = []

        def local_validate(text):
            return [{"code": "RAW_STATE_ID_LEAK", "message": "raw id"}] if text == "C1" else []

        def semantic(*_):
            semantic_calls.append(1)
            return CombinedComplianceAssessment(ActionFidelityLabel.ALIGNED, StanceLabel.SUPPORTS_ASSIGNED, "ok", "ok")

        result = finalize_compliant_utterance(
            lambda feedback: (prompts.append(feedback), "C1" if len(prompts) == 1 else "[[C1]]")[1],
            self.assignment,
            "EXTEND_ARGUMENT",
            None,
            "crossfire",
            semantic,
            local_validate=local_validate,
        )
        self.assertTrue(result.committed)
        self.assertEqual(len(semantic_calls), 1)
        self.assertIn("RAW_STATE_ID_LEAK", prompts[1])


if __name__ == "__main__":
    unittest.main()
