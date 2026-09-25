"""Deterministic mock service used for zero-token web development and tests."""
from __future__ import annotations

from .contracts import (
    AnalyzeTopicRequest,
    ContextQuestion,
    ContextStepRequest,
    ContextStepResponse,
    CreateMotionRequest,
    DebateSession,
    DebateStepRequest,
    DebateStepResponse,
    MotionResponse,
    NeutralSummaryRequest,
    NeutralSummaryResponse,
    TopicAnalysis,
    TranscriptItem,
)


PERSONA_PAIRS = {
    "FACT": ("Auditor", "Falsifier"),
    "CAUSE": ("Auditor", "Falsifier"),
    "DEFINITION": ("Socratic", "Falsifier"),
    "POLICY": ("Principlist", "Pragmatist"),
    "VALUE": ("Principlist", "Pragmatist"),
    "PERSONAL_DISPUTE": ("Socratic", "Synthesist"),
    "COMPARISON": ("Pragmatist", "Synthesist"),
    "OTHER": ("Falsifier", "Pragmatist"),
    "INTERPRETATION": ("Socratic", "Principlist"),
    "INFORMATIONAL": ("Socratic", "Falsifier"),
}


class MockDebateWebService:
    """Product-flow fake. It never calls an external model."""

    _base_schedule = [
        ("OPENING", "A"), ("OPENING", "B"),
        ("CROSSFIRE", "A"), ("CROSSFIRE", "B"), ("CROSSFIRE", "A"), ("CROSSFIRE", "B"), ("CROSSFIRE", "A"), ("CROSSFIRE", "B"),
        ("REBUTTAL", "A"), ("REBUTTAL", "B"),
        ("FINAL_FOCUS", "A"), ("FINAL_FOCUS", "B"),
    ]

    _tangsuyuk_lines = {
        ("OPENING", "A"): "소스를 부으면 튀김과 소스가 한 접시의 맛으로 자연스럽게 결합됩니다. 저는 그 완성된 조합을 더 중요하게 봅니다.",
        ("OPENING", "B"): "찍어 먹으면 바삭함과 소스 양을 각자 조절할 수 있습니다. 선택권을 남기는 쪽이 실제 식사에서는 더 유연합니다.",
        ("CROSSFIRE", "A"): "조절 가능성이 항상 맛의 완성도보다 앞선다고 보는 이유는 무엇인가요? 선택권 자체가 더 좋은 맛을 보장하진 않습니다.",
        ("CROSSFIRE", "B"): "완성도라는 기준부터 하나로 고정하기 어렵습니다. 소스를 부어 바삭함을 잃은 뒤에는 되돌릴 수 없다는 점은 어떻게 보시나요?",
        ("REBUTTAL", "A"): "바삭함 손실은 인정하지만 모든 조각을 오래 두고 먹는 것은 아닙니다. 즉 그 단점이 부먹의 결합된 맛을 항상 압도하지는 않습니다.",
        ("REBUTTAL", "B"): "그렇더라도 찍먹은 결합된 맛을 원할 때 만들 수 있고 바삭함도 남길 수 있습니다. 두 선택지를 동시에 보존한다는 점이 핵심입니다.",
        ("FINAL_FOCUS", "A"): "결국 기준은 탕수육을 한 접시의 완성된 요리로 볼 것인지입니다. 저는 소스와 튀김이 함께 만든 맛 때문에 부먹 쪽이 더 낫다고 봅니다.",
        ("FINAL_FOCUS", "B"): "핵심은 되돌릴 수 없는 선택을 누가 감수해야 하느냐입니다. 저는 각자가 소스 양과 식감을 조절할 수 있는 찍먹 쪽이 더 낫다고 봅니다.",
    }

    _hotdog_lines = {
        ("OPENING", "A"): "핫도그는 빵 사이에 속재료를 넣어 먹는 구조이므로 샌드위치 범주에 포함할 수 있습니다. 형태와 기능이라는 공통 기준을 적용해야 합니다.",
        ("OPENING", "B"): "핫도그는 고유한 이름과 조리 방식, 식문화가 확립된 별도 범주입니다. 빵과 속재료가 있다는 이유만으로 샌드위치라고 부르기는 어렵습니다.",
        ("CROSSFIRE", "A"): "고유한 이름이 있다는 사실이 구조적 분류를 배제하는 근거가 되나요? 하위 범주와 상위 범주는 동시에 성립할 수 있습니다.",
        ("CROSSFIRE", "B"): "구조만 기준으로 삼으면 속을 넣은 모든 빵을 샌드위치로 묶게 됩니다. 실제 언어 사용과 조리 관습의 경계는 어디에 두나요?",
        ("REBUTTAL", "A"): "생활 언어에서 별도 이름을 쓴다는 점은 인정합니다. 그래도 분류 기준을 형태와 기능으로 두면 핫도그는 샌드위치의 하위 유형이라는 결론이 더 일관됩니다.",
        ("REBUTTAL", "B"): "형태의 유사성만으로 같은 범주가 되지는 않습니다. 핫도그는 만드는 방식과 먹는 맥락까지 결합된 독자적 음식 범주입니다.",
        ("FINAL_FOCUS", "A"): "핵심은 이름보다 분류 기준입니다. 빵이 속재료를 감싸 한 끼를 구성한다는 기준에서 핫도그는 샌드위치에 속합니다.",
        ("FINAL_FOCUS", "B"): "핵심은 실제로 구별되는 음식 정체성입니다. 핫도그는 샌드위치와 비슷한 구조를 가졌어도 별도 범주로 보는 편이 타당합니다.",
    }

    def analyze_topic(self, request: AnalyzeTopicRequest) -> TopicAnalysis:
        topic = request.topic
        compact = topic.replace(" ", "")
        if any(token in compact for token in ("누가잘못", "싸웠", "내친구", "연인")):
            return TopicAnalysis(
                original_topic=topic, claim_type="PERSONAL_DISPUTE", epistemic_status="UNKNOWN",
                treatment_mode="NATURAL_DEBATE", interaction_state="CONTEXT_REQUIRED",
                normalized_motion=topic, side_labels=("입장 A", "입장 B"), context_required=True,
            )
        if topic.rstrip(" ?").endswith(("뭐야", "무엇인가")) and "핫도그" not in topic:
            return TopicAnalysis(
                original_topic=topic, claim_type="INFORMATIONAL", epistemic_status="UNKNOWN",
                treatment_mode="REFRAMED_DEBATE", interaction_state="INFORMATIONAL_FIRST",
                normalized_motion=topic, side_labels=("A", "B"), confirmation_reason="정보 질문은 바로 토론으로 바꾸지 않습니다.",
            )
        if "탕수육" in topic or "부먹" in topic or "찍먹" in topic:
            return TopicAnalysis(
                original_topic=topic, claim_type="COMPARISON", epistemic_status="NON_FACTUAL",
                treatment_mode="PLAYFUL_DEBATE", interaction_state="READY",
                normalized_motion="탕수육은 소스를 찍어 먹는 것보다 부어 먹는 편이 더 낫다.", side_labels=("부먹", "찍먹"),
            )
        if "핫도그" in topic and "샌드위치" in topic:
            return TopicAnalysis(
                original_topic=topic, claim_type="DEFINITION", epistemic_status="NON_FACTUAL",
                treatment_mode="NATURAL_DEBATE", interaction_state="READY",
                normalized_motion="핫도그는 샌드위치에 속한다.", side_labels=("샌드위치", "별도 범주"),
            )
        return TopicAnalysis(
            original_topic=topic, claim_type="OTHER", epistemic_status="UNKNOWN", treatment_mode="NATURAL_DEBATE",
            interaction_state="READY", normalized_motion=topic if topic.endswith(".") else topic + ".", side_labels=("A", "B"),
        )

    def context_step(self, request: ContextStepRequest) -> ContextStepResponse:
        questions = [
            ContextQuestion(id="ctx1", text="직접 확인한 사건의 순서를 가장 가깝게 고르면 무엇인가요?", options=["A가 먼저 행동했다", "B가 먼저 행동했다", "서로 거의 동시에 반응했다", "잘 모르겠다"]),
            ContextQuestion(id="ctx2", text="사전에 합의하거나 기대한 규칙이 있었나요?", options=["명확한 합의가 있었다", "암묵적인 기대만 있었다", "없었다", "잘 모르겠다"]),
            ContextQuestion(id="ctx3", text="현재 가장 판단하고 싶은 기준은 무엇인가요?", options=["약속 위반", "피해의 크기", "의사소통 책임", "잘 모르겠다"]),
        ]
        answered = len(request.answers)
        if answered >= len(questions):
            return ContextStepResponse(
                context_completeness=100, debate_ready=True, question=None,
                context_summary={"USER_OBSERVATION": [a.answer for a in request.answers], "REPORTED_CLAIM": [], "USER_ASSUMPTION": [], "UNKNOWN": []},
            )
        completeness = [25, 55, 80][answered]
        return ContextStepResponse(context_completeness=completeness, debate_ready=False, question=questions[answered])

    def create_motion(self, request: CreateMotionRequest) -> MotionResponse:
        side_labels = request.analysis.side_labels
        if request.edited_motion is not None:
            if request.edit_count >= 1:
                raise ValueError("Motion은 MVP에서 최대 1회만 수정할 수 있습니다.")
            motion = request.edited_motion
            edit_count = request.edit_count + 1
        elif request.analysis.claim_type == "PERSONAL_DISPUTE" and request.context_summary:
            motion = "이 사건에서 입장 A가 입장 B보다 더 큰 책임을 진다."
            edit_count = request.edit_count
        else:
            motion = request.analysis.normalized_motion
            edit_count = request.edit_count
        personas = PERSONA_PAIRS.get(request.analysis.claim_type, ("Falsifier", "Pragmatist"))
        tone = request.analysis.tone_hint or ("PLAYFUL" if request.analysis.treatment_mode == "PLAYFUL_DEBATE" else "SERIOUS")
        return MotionResponse(motion=motion, side_labels=side_labels, personas=personas, tone=tone, edit_count=edit_count, context_summary=request.context_summary, fact_anchor=request.analysis.fact_anchor, truth_mode=request.analysis.truth_mode)

    def start_session(self, motion: MotionResponse) -> DebateSession:
        return DebateSession(motion=motion.motion, side_labels=motion.side_labels, personas=motion.personas, tone=motion.tone)

    def _make_line(self, session: DebateSession, phase: str, speaker: str) -> str:
        if phase == "AUDIENCE_RESPONSE":
            stance = session.side_labels[0 if speaker == "A" else 1]
            return f"관객 질문 ‘{session.audience_question}’에 대해 {stance} 관점에서는 핵심 기준을 유지하되 그 상황을 예외로 따져봐야 합니다."
        if "핫도그" in session.motion:
            lines = self._hotdog_lines
        elif "탕수육" in session.motion:
            lines = self._tangsuyuk_lines
        else:
            lines = {}
        line = lines.get((phase, speaker))
        if line:
            # Vary repeated crossfire turns without changing the deterministic contract.
            if phase == "CROSSFIRE" and sum(x.phase == "CROSSFIRE" and x.speaker == speaker for x in session.transcript) > 0:
                return ("방금 기준을 더 좁혀보겠습니다. " if speaker == "A" else "그 기준을 실제 선택 상황에 적용해보죠. ") + line
            return line
        stance = session.side_labels[0 if speaker == "A" else 1]
        opponent = session.side_labels[1 if speaker == "A" else 0]
        return f"‘{session.motion}’ 논제에서 저는 {stance} 입장을 지지합니다. {opponent} 측 기준이 왜 우선해야 하는지 핵심 쟁점을 이어서 검토하겠습니다."

    def debate_step(self, request: DebateStepRequest) -> DebateStepResponse:
        session = request.session.model_copy(deep=True)
        if not session.debater_models:
            session.debater_models = {"A": "mock-debater-a", "B": "mock-debater-b"}
        if session.completed:
            return DebateStepResponse(session=session, phase="COMPLETE", completed=True)

        at_audience_gate = session.next_index == 8 and session.audience_status == "PENDING"
        if at_audience_gate:
            if request.command == "NEXT":
                return DebateStepResponse(session=session, phase="CROSSFIRE", awaiting_audience_question=True)
            if request.command == "SKIP_AUDIENCE":
                session.audience_status = "SKIPPED"
                return DebateStepResponse(session=session, phase="CROSSFIRE", awaiting_audience_question=False)
            if request.command == "AUDIENCE_QUESTION":
                if not request.audience_question:
                    raise ValueError("관객 질문이 필요합니다.")
                session.audience_status = "ASKED"
                session.audience_question = request.audience_question
                session.audience_response_index = 0
                return DebateStepResponse(session=session, phase="CROSSFIRE")

        if session.audience_status == "ASKED" and session.audience_response_index < 2:
            speaker = "A" if session.audience_response_index == 0 else "B"
            utterance = self._make_line(session, "AUDIENCE_RESPONSE", speaker)
            item = TranscriptItem(turn=len(session.transcript) + 1, phase="AUDIENCE_RESPONSE", speaker=speaker, side_label=session.side_labels[0 if speaker == "A" else 1], utterance=utterance)
            session.transcript.append(item)
            session.audience_response_index += 1
            if session.audience_response_index == 2:
                session.audience_status = "DONE"
            return DebateStepResponse(session=session, phase="AUDIENCE_RESPONSE", speaker=speaker, side_label=item.side_label, utterance=utterance)

        if session.next_index >= len(self._base_schedule):
            session.completed = True
            return DebateStepResponse(session=session, phase="COMPLETE", completed=True)

        phase, speaker = self._base_schedule[session.next_index]
        utterance = self._make_line(session, phase, speaker)
        item = TranscriptItem(turn=len(session.transcript) + 1, phase=phase, speaker=speaker, side_label=session.side_labels[0 if speaker == "A" else 1], utterance=utterance)
        session.transcript.append(item)
        session.next_index += 1
        if session.next_index >= len(self._base_schedule):
            session.completed = True
        return DebateStepResponse(session=session, phase=phase, speaker=speaker, side_label=item.side_label, utterance=utterance, completed=session.completed)

    def neutral_summary(self, request: NeutralSummaryRequest) -> NeutralSummaryResponse:
        if "핫도그" in request.motion:
            return NeutralSummaryResponse(
                key_clashes=["핫도그를 구조에 따라 샌드위치로 분류할지, 식문화와 관습에 따라 별도 범주로 볼지"],
                side_a_strong_points=["빵과 속재료의 형태와 기능을 일관된 분류 기준으로 제시한다."],
                side_b_strong_points=["고유한 조리 방식과 실제 언어 사용이 독자적 음식 범주를 만든다고 본다."],
                agreements=["핫도그와 샌드위치의 구조가 유사하다는 점"],
                unresolved=["구조적 분류와 문화적 분류 중 어느 기준을 우선할지"],
            )
        return NeutralSummaryResponse(
            key_clashes=["맛의 완성도를 우선할지, 선택권과 식감 보존을 우선할지"],
            side_a_strong_points=["소스와 튀김의 결합 자체를 하나의 완성된 맛으로 본다."],
            side_b_strong_points=["찍먹은 식감과 소스 양을 되돌릴 수 있게 조절한다."],
            agreements=["소스와 튀김이 만나는 방식이 경험에 영향을 준다는 점"],
            unresolved=["어떤 평가 기준을 우선해야 하는지는 취향과 상황에 따라 남는다."],
        )
