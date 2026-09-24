import unittest

from pydantic import ValidationError

from src.web_app.contracts import (
    AnalyzeTopicRequest,
    ContextStepRequest,
    CreateMotionRequest,
    DebateStepRequest,
    NeutralSummaryRequest,
)
from src.web_app.mock_service import MockDebateWebService


class WebMvpContractTests(unittest.TestCase):
    def setUp(self):
        self.service = MockDebateWebService()

    def test_topic_rejects_blank_input(self):
        with self.assertRaises(ValidationError):
            AnalyzeTopicRequest(topic="   ")

    def test_topic_rejects_overlong_input(self):
        with self.assertRaises(ValidationError):
            AnalyzeTopicRequest(topic="가" * 2001)

    def test_tangsuyuk_analysis_is_ready_and_normalized(self):
        result = self.service.analyze_topic(AnalyzeTopicRequest(topic="탕수육 부먹 찍먹"))
        self.assertEqual(result.interaction_state, "READY")
        self.assertEqual(result.claim_type, "COMPARISON")
        self.assertIn("부어", result.normalized_motion)
        self.assertEqual(len(result.side_labels), 2)

    def test_hotdog_mock_utterance_matches_selected_motion(self):
        analysis = self.service.analyze_topic(AnalyzeTopicRequest(topic="핫도그는 샌드위치인가?"))
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        session = self.service.start_session(motion)

        first = self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))

        self.assertIn("핫도그", first.utterance)
        self.assertIn("샌드위치", first.utterance)
        self.assertNotIn("소스", first.utterance)
        self.assertNotIn("튀김", first.utterance)

        summary = self.service.neutral_summary(
            NeutralSummaryRequest(motion=motion.motion, transcript=first.session.transcript)
        )
        summary_text = " ".join(summary.key_clashes + summary.side_a_strong_points + summary.side_b_strong_points)
        self.assertIn("샌드위치", summary_text)
        self.assertNotIn("탕수육", summary_text)

    def test_personal_dispute_routes_to_context(self):
        result = self.service.analyze_topic(AnalyzeTopicRequest(topic="철수랑 영희가 싸웠는데 누가 잘못했어?"))
        self.assertEqual(result.interaction_state, "CONTEXT_REQUIRED")

    def test_context_progress_is_backend_computed_and_eventually_ready(self):
        req = ContextStepRequest(topic="철수랑 영희가 싸웠는데 누가 잘못했어?", answers=[])
        first = self.service.context_step(req)
        self.assertFalse(first.debate_ready)
        self.assertGreater(first.context_completeness, 0)
        second = self.service.context_step(ContextStepRequest(topic=req.topic, answers=[{"question_id": first.question.id, "answer": "직접 봤다"}]))
        self.assertGreaterEqual(second.context_completeness, first.context_completeness)

    def test_motion_can_be_edited_once_only(self):
        analysis = self.service.analyze_topic(AnalyzeTopicRequest(topic="탕수육 부먹 찍먹"))
        first = self.service.create_motion(CreateMotionRequest(analysis=analysis, edited_motion="탕수육은 부먹이 찍먹보다 낫다.", edit_count=0))
        self.assertEqual(first.edit_count, 1)
        with self.assertRaises(ValueError):
            self.service.create_motion(CreateMotionRequest(analysis=analysis, edited_motion="다시 수정", edit_count=1))

    def test_mock_debate_reaches_audience_prompt_then_final_focus(self):
        analysis = self.service.analyze_topic(AnalyzeTopicRequest(topic="탕수육 부먹 찍먹"))
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        session = self.service.start_session(motion)
        phases = []
        audience_seen = False
        for _ in range(20):
            result = self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
            session = result.session
            if result.utterance:
                phases.append(result.phase)
            if result.awaiting_audience_question:
                audience_seen = True
                result = self.service.debate_step(DebateStepRequest(session=session, command="SKIP_AUDIENCE"))
                session = result.session
            if result.completed:
                break
        self.assertTrue(audience_seen)
        self.assertIn("OPENING", phases)
        self.assertIn("CROSSFIRE", phases)
        self.assertIn("REBUTTAL", phases)
        self.assertIn("FINAL_FOCUS", phases)
        self.assertTrue(session.completed)

    def test_audience_question_is_answered_by_both_sides(self):
        analysis = self.service.analyze_topic(AnalyzeTopicRequest(topic="탕수육 부먹 찍먹"))
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        session = self.service.start_session(motion)
        while True:
            result = self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
            session = result.session
            if result.awaiting_audience_question:
                break
        result = self.service.debate_step(DebateStepRequest(session=session, command="AUDIENCE_QUESTION", audience_question="둘 다 눅눅해지면요?"))
        session = result.session
        answers = []
        for _ in range(2):
            result = self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
            session = result.session
            answers.append(result.phase)
        self.assertEqual(answers, ["AUDIENCE_RESPONSE", "AUDIENCE_RESPONSE"])

    def test_neutral_summary_has_no_winner_field(self):
        analysis = self.service.analyze_topic(AnalyzeTopicRequest(topic="탕수육 부먹 찍먹"))
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        result = self.service.neutral_summary(NeutralSummaryRequest(motion=motion.motion, transcript=[]))
        data = result.model_dump()
        self.assertNotIn("winner", data)
        self.assertTrue(result.key_clashes)


if __name__ == "__main__":
    unittest.main()
