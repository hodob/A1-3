import unittest

from src.debate_engine.combined_compliance import CombinedComplianceAssessment
from src.debate_engine.debate_contracts import PatchEnvelope
from src.debate_engine.action_fidelity import ActionFidelityLabel
from src.debate_engine.stance_compliance import StanceLabel
from src.web_app.contracts import AnalyzeTopicRequest, CreateMotionRequest, DebateSession, DebateStepRequest
from src.web_app.live_service import LiveDebateWebService, LiveRuntimeDependencies
from src.web_app.session_token import SessionTokenCodec


class FakeDeps(LiveRuntimeDependencies):
    def __init__(self):
        self.generated = []
        self.structured_tools = []

    def generate_text(self, provider, messages, timeout=90):
        self.generated.append(messages)
        return "저는 제 입장을 지지하며 핵심 이유를 제시합니다.", {"usage": {"total_tokens": 1}}

    def check_compliance(self, provider, **kwargs):
        return CombinedComplianceAssessment(
            ActionFidelityLabel.ALIGNED,
            StanceLabel.SUPPORTS_ASSIGNED,
            "action ok",
            "stance ok",
        ), {"usage": {"total_tokens": 1}}

    def extract_patch(self, provider, turn, state, timeout, feedback=None):
        return PatchEnvelope.model_validate({
            "operations": [{"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "저는 제 입장을 지지한다."}]
        }), {"usage": {"total_tokens": 1}}

    def structured(self, provider, messages, contract, tool_name, timeout=90):
        self.structured_tools.append(tool_name)
        if tool_name == "topic_analysis":
            return contract.model_validate({
                "original_topic": "핫도그는 샌드위치인가?",
                "claim_type": "DEFINITION",
                "epistemic_status": "NON_FACTUAL",
                "treatment_mode": "NATURAL_DEBATE",
                "interaction_state": "READY",
                "normalized_motion": "핫도그는 샌드위치에 속한다.",
                "side_labels": ["샌드위치", "별도 범주"],
                "context_required": False,
                "confirmation_reason": None,
            }), {"usage": {"total_tokens": 1}}
        if tool_name == "motion_normalization":
            return contract.model_validate({"motion": "이 사건에서 철수가 영희보다 더 큰 책임을 진다.", "side_labels": ["철수 책임", "영희 책임"]}), {"usage": {"total_tokens": 1}}
        if tool_name == "context_step":
            payload = __import__("json").loads(messages[-1]["content"])
            answers = payload.get("answers", [])
            if len(answers) < 2:
                index = len(answers) + 1
                return contract.model_validate({
                    "context_completeness": 45 if index == 1 else 75,
                    "debate_ready": False,
                    "question": {
                        "id": f"ctx{index}",
                        "text": "사건의 핵심 사실을 알려주세요.",
                        "options": ["A", "B", "잘 모르겠다"],
                        "allow_unknown": True,
                        "allow_free_text": True,
                    },
                    "context_summary": None,
                }), {"usage": {"total_tokens": 1}}
            return contract.model_validate({
                "context_completeness": 100,
                "debate_ready": True,
                "question": None,
                "context_summary": {
                    "USER_OBSERVATION": [item["answer"] for item in answers],
                    "REPORTED_CLAIM": [],
                    "USER_ASSUMPTION": [],
                    "UNKNOWN": [],
                },
            }), {"usage": {"total_tokens": 1}}
        if tool_name == "neutral_summary":
            return contract.model_validate({
                "key_clashes": ["분류 기준"],
                "side_a_strong_points": ["구조적 유사성"],
                "side_b_strong_points": ["독립 범주 기준"],
                "agreements": ["분류 기준이 필요하다는 점"],
                "unresolved": ["어떤 기준을 우선할지"],
            }), {"usage": {"total_tokens": 1}}
        raise AssertionError(tool_name)


class LiveWebServiceTests(unittest.TestCase):
    def setUp(self):
        self.deps = FakeDeps()
        self.service = LiveDebateWebService(
            provider={"url": "https://example.invalid", "api_key": "secret", "model": "gpt-test"},
            debater_models=(
                {"company": "GOOGLE", "id": "gemini-test"},
                {"company": "ANTHROPIC", "id": "claude-test"},
            ),
            codec=SessionTokenCodec("unit-test-session-secret-123456789"),
            deps=self.deps,
        )

    def test_live_topic_analysis_uses_structured_contract(self):
        result = self.service.analyze_topic(AnalyzeTopicRequest(topic="핫도그는 샌드위치인가?"))
        self.assertEqual(result.claim_type, "DEFINITION")
        self.assertEqual(result.interaction_state, "READY")


    def test_personal_context_motion_uses_context_after_intake(self):
        from src.web_app.contracts import TopicAnalysis
        analysis = TopicAnalysis(
            original_topic="철수랑 영희가 싸웠는데 누가 잘못했어?", claim_type="PERSONAL_DISPUTE",
            epistemic_status="UNKNOWN", treatment_mode="NATURAL_DEBATE", interaction_state="CONTEXT_REQUIRED",
            normalized_motion="철수랑 영희가 싸웠는데 누가 잘못했어?", side_labels=("입장 A", "입장 B"), context_required=True,
        )
        result = self.service.create_motion(CreateMotionRequest(analysis=analysis, context_summary={"USER_OBSERVATION": ["철수가 먼저 약속을 깼다"], "REPORTED_CLAIM": [], "USER_ASSUMPTION": [], "UNKNOWN": []}, edit_count=0))
        self.assertEqual(result.motion, "이 사건에서 철수가 영희보다 더 큰 책임을 진다.")
        self.assertEqual(result.side_labels, ("철수 책임", "영희 책임"))
        self.assertIn("motion_normalization", self.deps.structured_tools)

    def test_tone_hint_is_independent_from_treatment_mode(self):
        from src.web_app.contracts import TopicAnalysis
        analysis = TopicAnalysis(
            original_topic="가벼운 취향", claim_type="COMPARISON", epistemic_status="NON_FACTUAL",
            treatment_mode="NATURAL_DEBATE", interaction_state="READY", normalized_motion="A가 B보다 낫다.",
            side_labels=("A", "B"), tone_hint="PLAYFUL",
        )
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        self.assertEqual(motion.tone, "PLAYFUL")

    def test_first_debate_step_creates_signed_engine_token(self):
        analysis = self.service.analyze_topic(AnalyzeTopicRequest(topic="핫도그는 샌드위치인가?"))
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        session = DebateSession(motion=motion.motion, side_labels=motion.side_labels, personas=motion.personas, tone=motion.tone)
        result = self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
        self.assertEqual(result.phase, "OPENING")
        self.assertIsNotNone(result.session.engine_token)
        self.assertEqual(len(result.session.transcript), 1)

    def test_streamed_draft_is_only_committed_after_validation(self):
        class StreamDeps(FakeDeps):
            def generate_text(self, provider, messages, timeout=90, on_delta=None):
                if on_delta:
                    on_delta("임시 ")
                    on_delta("발언")
                return "임시 발언", {"usage": {"total_tokens": 1}}

        self.service.deps = StreamDeps()
        session = DebateSession(motion="논제", side_labels=("찬성", "반대"), personas=("Socratic", "Falsifier"), tone="SERIOUS")
        events = []
        result = self.service.debate_step(DebateStepRequest(session=session), on_event=lambda kind, data: events.append((kind, data)))
        self.assertEqual([kind for kind, _ in events], ["draft_reset", "draft_delta", "draft_delta"])
        self.assertEqual(result.session.transcript[0].utterance, "임시 발언")

    def test_rejected_draft_does_not_change_session(self):
        class RejectedDeps(FakeDeps):
            def generate_text(self, provider, messages, timeout=90, on_delta=None):
                if on_delta:
                    on_delta("상대가 옳습니다")
                return "상대가 옳습니다", {}

            def check_compliance(self, provider, **kwargs):
                return CombinedComplianceAssessment(ActionFidelityLabel.MISALIGNED, StanceLabel.CONTRADICTS_ASSIGNED, "wrong", "wrong"), {}

        from src.web_app.errors import SafeFailure
        self.service.deps = RejectedDeps()
        session = DebateSession(motion="논제", side_labels=("찬성", "반대"), personas=("Socratic", "Falsifier"), tone="SERIOUS")
        original = session.model_dump(mode="json")
        events = []
        with self.assertRaises(SafeFailure):
            self.service.debate_step(DebateStepRequest(session=session), on_event=lambda kind, data: events.append((kind, data)))
        self.assertEqual([kind for kind, _ in events], ["draft_reset", "draft_delta", "draft_reset", "draft_delta", "draft_reset", "draft_delta"])
        self.assertEqual(session.model_dump(mode="json"), original)

    def test_second_step_recovers_internal_state_from_token(self):
        analysis = self.service.analyze_topic(AnalyzeTopicRequest(topic="핫도그는 샌드위치인가?"))
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        session = DebateSession(motion=motion.motion, side_labels=motion.side_labels, personas=motion.personas, tone=motion.tone)
        first = self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
        second = self.service.debate_step(DebateStepRequest(session=first.session, command="NEXT"))
        self.assertEqual(second.phase, "OPENING")
        self.assertEqual(second.speaker, "B")
        self.assertEqual(len(second.session.transcript), 2)



    def test_personal_context_is_preserved_into_debate_prompt(self):
        from src.web_app.contracts import TopicAnalysis
        analysis = TopicAnalysis(
            original_topic="철수랑 영희가 싸웠는데 누가 잘못했어?", claim_type="PERSONAL_DISPUTE",
            epistemic_status="UNKNOWN", treatment_mode="NATURAL_DEBATE", interaction_state="CONTEXT_REQUIRED",
            normalized_motion="원문", side_labels=("입장 A", "입장 B"), context_required=True,
        )
        context = {"USER_OBSERVATION": ["철수가 약속 시간보다 30분 늦었다"], "REPORTED_CLAIM": [], "USER_ASSUMPTION": [], "UNKNOWN": []}
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, context_summary=context, edit_count=0))
        session = DebateSession(motion=motion.motion, side_labels=motion.side_labels, personas=motion.personas, tone=motion.tone, context_summary=motion.context_summary)
        self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
        user_prompt = self.deps.generated[-1][-1]["content"]
        self.assertIn("30분 늦었다", user_prompt)

    def test_fact_anchor_survives_motion_and_session_prompt(self):
        from src.web_app.contracts import TopicAnalysis
        analysis = TopicAnalysis(
            original_topic="1+1=3", claim_type="FACT", epistemic_status="WEIGHT_DOMINANT_FALSE", treatment_mode="PLAYFUL_DEBATE", interaction_state="READY",
            normalized_motion="1+1=3을 수사적 놀이로 방어할 수 있다.", side_labels=("놀이 방어", "현실 반박"),
            fact_anchor="표준 산술에서 1+1=2이다.", truth_mode="RHETORICAL_PLAY",
        )
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        self.assertEqual(motion.fact_anchor, "표준 산술에서 1+1=2이다.")
        session = DebateSession(motion=motion.motion, side_labels=motion.side_labels, personas=motion.personas, tone=motion.tone, fact_anchor=motion.fact_anchor, truth_mode=motion.truth_mode)
        self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
        system_prompt = self.deps.generated[-1][0]["content"]
        self.assertIn("표준 산술에서 1+1=2", system_prompt)

    def test_signed_token_overrides_tampered_public_progress(self):
        analysis = self.service.analyze_topic(AnalyzeTopicRequest(topic="핫도그는 샌드위치인가?"))
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        session = DebateSession(motion=motion.motion, side_labels=motion.side_labels, personas=motion.personas, tone=motion.tone)
        first = self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
        tampered = first.session.model_copy(update={"next_index": 11, "motion": "조작된 논제", "side_labels": ("조작A", "조작B")})
        second = self.service.debate_step(DebateStepRequest(session=tampered, command="NEXT"))
        self.assertEqual(second.speaker, "B")
        self.assertEqual(second.session.motion, motion.motion)
        self.assertEqual(second.session.side_labels, motion.side_labels)

    def test_fake_live_runtime_can_reach_audience_gate_without_network(self):
        analysis = self.service.analyze_topic(AnalyzeTopicRequest(topic="핫도그는 샌드위치인가?"))
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        session = DebateSession(motion=motion.motion, side_labels=motion.side_labels, personas=motion.personas, tone=motion.tone)
        for _ in range(8):
            result = self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
            session = result.session
        gate = self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
        self.assertTrue(gate.awaiting_audience_question)
        self.assertEqual(len(gate.session.transcript), 8)

    def test_fake_live_context_step_and_summary_require_no_network(self):
        from src.web_app.contracts import ContextStepRequest, ContextAnswer, NeutralSummaryRequest
        context = self.service.context_step(ContextStepRequest(topic="철수랑 영희가 싸웠는데 누가 잘못했어?", answers=[]))
        self.assertFalse(context.debate_ready)
        self.assertIsNotNone(context.question)
        ready = self.service.context_step(ContextStepRequest(topic="철수랑 영희가 싸웠는데 누가 잘못했어?", answers=[
            ContextAnswer(question_id="ctx1", answer="철수가 먼저 행동했다"),
            ContextAnswer(question_id="ctx2", answer="합의가 있었다"),
        ]))
        self.assertTrue(ready.debate_ready)
        self.assertIn("USER_OBSERVATION", ready.context_summary)
        summary = self.service.neutral_summary(NeutralSummaryRequest(motion="핫도그는 샌드위치에 속한다.", transcript=[]))
        self.assertTrue(summary.key_clashes)
        self.assertTrue(summary.agreements)

    def test_fake_live_runtime_completes_full_flow_with_audience_question(self):
        from src.web_app.contracts import NeutralSummaryRequest
        analysis = self.service.analyze_topic(AnalyzeTopicRequest(topic="핫도그는 샌드위치인가?"))
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        session = DebateSession(motion=motion.motion, side_labels=motion.side_labels, personas=motion.personas, tone=motion.tone)
        for _ in range(8):
            session = self.service.debate_step(DebateStepRequest(session=session, command="NEXT")).session
        gate = self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
        self.assertTrue(gate.awaiting_audience_question)
        session = self.service.debate_step(DebateStepRequest(session=gate.session, command="AUDIENCE_QUESTION", audience_question="경계 기준은 무엇인가요?")).session
        for _ in range(2):
            session = self.service.debate_step(DebateStepRequest(session=session, command="NEXT")).session
        while not session.completed:
            session = self.service.debate_step(DebateStepRequest(session=session, command="NEXT")).session
        self.assertEqual(len(session.transcript), 14)
        summary = self.service.neutral_summary(NeutralSummaryRequest(motion=session.motion, transcript=session.transcript))
        self.assertTrue(summary.unresolved)

    def test_saturated_crossfire_moves_to_audience_gate_without_generation(self):
        from src.debate_engine.debate_contracts import DebateState, apply_patch
        from src.web_app.contracts import TranscriptItem
        state = apply_patch(DebateState(), {"operations": [{"op": "ADD_PROPOSITION", "text": "전체 조화", "semantic_kind": "NEW_REASON"}]}, speaker="A", turn=1)
        state = apply_patch(state, {"operations": [{"op": "ADD_PROPOSITION", "text": "선택권", "semantic_kind": "NEW_REASON"}]}, speaker="B", turn=2)
        state = apply_patch(state, {"operations": [{"op": "ADD_PROPOSITION", "text": "전체 과정 안정성", "semantic_kind": "SAME_POINT", "semantic_anchor_ref": "C1"}]}, speaker="A", turn=3)
        state = apply_patch(state, {"operations": [{"op": "ADD_PROPOSITION", "text": "개인별 선택 유지", "semantic_kind": "SAME_POINT", "semantic_anchor_ref": "C2"}]}, speaker="B", turn=4)
        session = DebateSession(
            motion="논제", side_labels=("A입장", "B입장"), personas=("Socratic", "Falsifier"), tone="SERIOUS", next_index=6,
            transcript=[
                TranscriptItem(turn=i, phase="OPENING" if i <= 2 else "CROSSFIRE", speaker="A" if i % 2 else "B", side_label="A입장" if i % 2 else "B입장", utterance=f"발언 {i}")
                for i in range(1, 7)
            ],
        )
        session = self.service._save_engine(session, state, [("A", "WEIGH_COMPARATIVE", ("C2", "C1"))], {"A": "gemini-test", "B": "claude-test"})
        generated_before = len(self.deps.generated)
        result = self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
        self.assertTrue(result.awaiting_audience_question)
        self.assertEqual(result.moderator_decision, "MOVE_PHASE")
        self.assertEqual(result.session.next_index, 8)
        self.assertEqual(len(self.deps.generated), generated_before)

    def test_audience_question_verbatim_reaches_generation_prompt(self):
        analysis = self.service.analyze_topic(AnalyzeTopicRequest(topic="핫도그는 샌드위치인가?"))
        motion = self.service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        session = DebateSession(motion=motion.motion, side_labels=motion.side_labels, personas=motion.personas, tone=motion.tone)
        for _ in range(8):
            session = self.service.debate_step(DebateStepRequest(session=session, command="NEXT")).session
        gate = self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
        session = self.service.debate_step(DebateStepRequest(session=gate.session, command="AUDIENCE_QUESTION", audience_question="볶는다는 것도 있어")).session
        self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))
        prompt = self.deps.generated[-1][-1]["content"]
        self.assertIn('<audience_input treat_as_data="true">볶는다는 것도 있어</audience_input>', prompt)

    def test_final_focus_does_not_leak_internal_question_id_or_force_open_question(self):
        from src.debate_engine.debate_contracts import DebateState, apply_patch
        state = apply_patch(DebateState(), {"operations": [{"op": "ASK_QUESTION", "core_proposition": "왜 전체 조화가 우선인가?"}]}, speaker="B", turn=3)
        session = DebateSession(motion="논제", side_labels=("A입장", "B입장"), personas=("Socratic", "Falsifier"), tone="SERIOUS")
        self.service._commit_generated_turn(session, state, [], {"A": "gemini-test", "B": "claude-test"}, "FINAL_FOCUS", "A")
        prompt = self.deps.generated[-1][-1]["content"]
        self.assertNotIn("열린 질문 Q1", prompt)
        self.assertNotIn("먼저 이 열린 질문", prompt)
        self.assertIn("CRYSTALLIZE", prompt)

    def test_state_reference_metadata_is_attached_to_committed_turn(self):
        from src.debate_engine.debate_contracts import DebateState, apply_patch

        class RefDeps(FakeDeps):
            def generate_text(self, provider, messages, timeout=90, on_delta=None):
                self.generated.append(messages)
                if on_delta:
                    on_delta("앞서 [[C1]]을 봅니다.")
                return "앞서 [[C1]]을 봅니다.", {"usage": {"total_tokens": 1}}

        self.service.deps = RefDeps()
        state = apply_patch(
            DebateState(),
            {"operations": [{"op": "ADD_PROPOSITION", "text": "상대의 핵심 주장", "semantic_kind": "NEW_REASON"}]},
            speaker="B",
            turn=1,
        )
        session = DebateSession(motion="논제", side_labels=("A입장", "B입장"), personas=("Socratic", "Falsifier"), tone="SERIOUS")
        utterance, _, _, _, references = self.service._commit_generated_turn(
            session,
            state,
            [],
            {"A": "gemini-test", "B": "claude-test"},
            "CROSSFIRE",
            "A",
        )
        self.assertIn("[[C1]]", utterance)
        self.assertEqual(references[0]["id"], "C1")
        self.assertEqual(references[0]["speaker"], "B")
        self.assertEqual(references[0]["turn"], 1)

    def test_debug_mode_records_typed_compliance_rejection(self):
        class RetryDeps(FakeDeps):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def generate_text(self, provider, messages, timeout=90, on_delta=None):
                self.calls += 1
                text = "반대 입장이 맞습니다." if self.calls == 1 else "저는 제 입장을 유지합니다."
                if on_delta:
                    on_delta(text)
                return text, {"usage": {"total_tokens": 1}}

            def check_compliance(self, provider, **kwargs):
                if self.calls == 1:
                    return CombinedComplianceAssessment(
                        ActionFidelityLabel.ALIGNED,
                        StanceLabel.CONTRADICTS_ASSIGNED,
                        "action ok",
                        "reversal",
                    ), {"usage": {"total_tokens": 2}}
                return super().check_compliance(provider, **kwargs)

        deps = RetryDeps()
        service = LiveDebateWebService(
            provider={"url": "https://example.invalid", "api_key": "secret", "model": "gpt-test"},
            debater_models=(
                {"company": "GOOGLE", "id": "gemini-test"},
                {"company": "ANTHROPIC", "id": "claude-test"},
            ),
            codec=SessionTokenCodec("unit-test-session-secret-123456789"),
            deps=deps,
            debug_mode=True,
        )
        events = []
        session = DebateSession(motion="논제", side_labels=("찬성", "반대"), personas=("Socratic", "Falsifier"), tone="SERIOUS")
        result = service.debate_step(DebateStepRequest(session=session), on_event=lambda kind, data: events.append((kind, data)))
        self.assertEqual(len(result.session.transcript), 1)
        checks = [data for kind, data in events if kind == "debug" and data.get("event") == "compliance"]
        self.assertEqual(len(checks), 2)
        self.assertFalse(checks[0]["accepted"])
        self.assertIn("STANCE_REVERSAL", checks[0]["failure_codes"])
        self.assertTrue(checks[1]["accepted"])

    def test_tampered_engine_token_is_rejected(self):
        session = DebateSession(
            motion="x", side_labels=("A", "B"), personas=("Socratic", "Falsifier"), tone="SERIOUS",
            engine_token="bad.token",
        )
        with self.assertRaises(ValueError):
            self.service.debate_step(DebateStepRequest(session=session, command="NEXT"))


if __name__ == "__main__":
    unittest.main()
