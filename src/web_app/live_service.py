"""Live web orchestration over the validated Debate Engine.

Network operations are isolated behind LiveRuntimeDependencies so orchestration can be
TDD-tested without spending provider tokens.
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request

from .contracts import (
    AnalyzeTopicRequest, ContextStepRequest, ContextStepResponse, CreateMotionRequest,
    DebateSession, DebateStepRequest, DebateStepResponse, MotionNormalizationDraft, MotionResponse,
    NeutralSummaryRequest, NeutralSummaryResponse, TopicAnalysis, TranscriptItem,
)
from .mock_service import PERSONA_PAIRS
from .session_token import SessionTokenCodec, SessionTokenError
from .errors import SafeFailure
from src.debate_engine.action_execution_contracts import CONTRACTS
from src.debate_engine.action_pair_state import filter_available_pairs
from src.debate_engine.action_policy import eligible_actions, select_action_for_speaker
from src.debate_engine.combined_compliance import finalize_compliant_utterance, judge_combined
from src.debate_engine.debate_contracts import DebateState, PatchEnvelope, PatchValidationError
from src.debate_engine.debate_harness import call_model, speech_messages
from src.debate_engine.provider_adapter import CURRENT_PROVIDER, ProviderAdapter
from src.debate_engine.provider_transport import request_completion
from src.debate_engine.stance_compliance import StanceAssignment
from src.debate_engine.state_harness import call_patch, extract_and_apply
from src.runtime_config import DebaterModelConfig


class LiveRuntimeDependencies:
    def generate_text(self, provider, messages, timeout=90):
        return call_model(provider, messages, timeout=timeout)

    def check_compliance(self, provider, **kwargs):
        return judge_combined(provider, **kwargs)

    def extract_patch(self, provider, turn, state, timeout, feedback=None):
        return call_patch(provider, turn, state, timeout, feedback)

    def structured(self, provider, messages, contract, tool_name, timeout=90):
        adapter = ProviderAdapter(CURRENT_PROVIDER)
        body = adapter.build_structured_body(provider["model"], messages, contract, tool_name)
        started = time.monotonic()
        try:
            payload = request_completion(provider, body, timeout=timeout)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"LLM HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM 연결 실패: {exc.reason}") from exc
        result = adapter.parse_structured_response(payload, contract, tool_name)
        return result, {"usage": payload.get("usage"), "elapsed_seconds": round(time.monotonic() - started, 3)}


class LiveDebateWebService:
    _base_schedule = [
        ("OPENING", "A"), ("OPENING", "B"),
        ("CROSSFIRE", "A"), ("CROSSFIRE", "B"), ("CROSSFIRE", "A"), ("CROSSFIRE", "B"), ("CROSSFIRE", "A"), ("CROSSFIRE", "B"),
        ("REBUTTAL", "A"), ("REBUTTAL", "B"),
        ("FINAL_FOCUS", "A"), ("FINAL_FOCUS", "B"),
    ]

    def __init__(self, provider: dict, debater_models: tuple[DebaterModelConfig, ...], codec: SessionTokenCodec, deps: LiveRuntimeDependencies | None = None, *, timeout: float = 90, rng: random.Random | None = None):
        self.provider = provider
        self.debater_models = tuple(DebaterModelConfig.model_validate(item) for item in debater_models)
        if len(self.debater_models) < 2 or len({item.company for item in self.debater_models}) != len(self.debater_models) or len({item.id for item in self.debater_models}) != len(self.debater_models):
            raise ValueError("debater_models must contain distinct companies and models")
        self.codec = codec
        self.deps = deps or LiveRuntimeDependencies()
        self.timeout = timeout
        self.rng = rng or random.SystemRandom()

    def _select_debater_models(self) -> dict[str, str]:
        selected = self.rng.sample(self.debater_models, 2)
        return {"A": selected[0].id, "B": selected[1].id}

    def _validate_debater_models(self, selected: dict) -> dict[str, str]:
        by_id = {item.id: item.company for item in self.debater_models}
        if set(selected) != {"A", "B"} or any(not isinstance(value, str) or value not in by_id for value in selected.values()) or by_id[selected["A"]] == by_id[selected["B"]]:
            raise ValueError("세션 모델 검증에 실패했습니다. 토론을 다시 시작해주세요.")
        return selected

    def analyze_topic(self, request: AnalyzeTopicRequest) -> TopicAnalysis:
        system = (
            "사용자 입력을 AI 토론 Harness용으로 분석하세요. claim_type, epistemic_status, treatment_mode, interaction_state를 계약 enum으로 고르세요. "
            "개인 사건에서 판단에 필요한 사실이 부족하면 CONTEXT_REQUIRED, 정보 설명 질문이면 INFORMATIONAL_FIRST입니다. "
            "사실 우세 주제를 거짓 대 현실의 동등한 증거 토론으로 만들지 마세요. Motion은 사용자 의미를 보존하고, 새 actor/criterion을 추가하면 CONFIRMATION_REQUIRED로 처리하세요. "
            "side_labels는 대칭적이고 비평가적인 두 짧은 이름으로 만드세요. topic_analysis 도구를 호출하세요."
        )
        result, _ = self.deps.structured(self.provider, [{"role": "system", "content": system}, {"role": "user", "content": request.topic}], TopicAnalysis, "topic_analysis", self.timeout)
        # The user's input is authoritative even if a provider rewrites original_topic.
        return result.model_copy(update={"original_topic": request.topic})

    def context_step(self, request: ContextStepRequest) -> ContextStepResponse:
        system = (
            "개인 사건 토론의 맥락을 한 질문씩 수집하세요. 사용자가 주지 않은 사건 사실을 만들지 마세요. "
            "객관식 options에는 가능하면 '잘 모르겠다'가 포함되어야 합니다. completeness는 필요한 active slot 확보 정도를 0~100으로 반환하세요. "
            "핵심 대립축을 바꿀 미확인 정보가 없으면 debate_ready=true와 provenance 그룹별 context_summary를 반환하세요. context_step 도구를 호출하세요."
        )
        payload = {"topic": request.topic, "answers": [x.model_dump() for x in request.answers]}
        result, _ = self.deps.structured(self.provider, [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], ContextStepResponse, "context_step", self.timeout)
        return result

    def create_motion(self, request: CreateMotionRequest) -> MotionResponse:
        side_labels = request.analysis.side_labels
        if request.edited_motion is not None:
            if request.edit_count >= 1:
                raise ValueError("Motion은 MVP에서 최대 1회만 수정할 수 있습니다.")
            motion, edit_count = request.edited_motion, request.edit_count + 1
        elif request.analysis.claim_type == "PERSONAL_DISPUTE" and request.context_summary:
            instructions = (
                "사용자가 제공한 개인 사건 맥락만 사용해 판단 가능한 토론 Motion 하나를 만드세요. 빠진 사실을 채우지 말고, "
                "누가 더 책임이 있는지처럼 사용자가 요청한 판단 목적을 보존하세요. 양측 label은 대칭적이고 비평가적으로 만드세요. motion_normalization 도구를 호출하세요."
            )
            payload = {"topic": request.analysis.original_topic, "context_summary": request.context_summary}
            draft, _ = self.deps.structured(self.provider, [{"role": "system", "content": instructions}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], MotionNormalizationDraft, "motion_normalization", self.timeout)
            motion, side_labels, edit_count = draft.motion, draft.side_labels, request.edit_count
        else:
            motion, edit_count = request.analysis.normalized_motion, request.edit_count
        personas = PERSONA_PAIRS.get(request.analysis.claim_type, ("Falsifier", "Pragmatist"))
        tone = "PLAYFUL" if request.analysis.treatment_mode == "PLAYFUL_DEBATE" else "SERIOUS"
        return MotionResponse(motion=motion, side_labels=side_labels, personas=personas, tone=tone, edit_count=edit_count, context_summary=request.context_summary, fact_anchor=request.analysis.fact_anchor, truth_mode=request.analysis.truth_mode)

    def neutral_summary(self, request: NeutralSummaryRequest) -> NeutralSummaryResponse:
        system = (
            "토론을 중립적으로 정리하세요. 승자, 점수, 어느 쪽이 더 낫다는 판정을 하지 마세요. "
            "핵심 clash, A/B의 강한 논점, 합의, 미해결 쟁점을 각각 짧은 목록으로 반환하고 neutral_summary 도구를 호출하세요."
        )
        payload = {"motion": request.motion, "transcript": [x.model_dump() for x in request.transcript]}
        result, _ = self.deps.structured(self.provider, [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], NeutralSummaryResponse, "neutral_summary", self.timeout)
        return result

    def _new_engine(self, session: DebateSession) -> dict:
        clean = session.model_copy(update={"engine_token": None})
        return {"session": clean.model_dump(mode="json"), "debate_state": DebateState().model_dump(mode="json"), "action_history": [], "debater_models": self._select_debater_models()}

    def _load_engine(self, public: DebateSession) -> tuple[DebateSession, DebateState, list[tuple[str, str, tuple[str, ...]]], dict[str, str]]:
        if not public.engine_token:
            payload = self._new_engine(public)
        else:
            try:
                payload = self.codec.decode(public.engine_token)
            except SessionTokenError as exc:
                raise ValueError("세션 검증에 실패했습니다. 토론을 다시 시작해주세요.") from exc
        session = DebateSession.model_validate(payload["session"]).model_copy(update={"engine_token": public.engine_token})
        state = DebateState.model_validate(payload["debate_state"])
        history = [(x[0], x[1], tuple(x[2])) for x in payload.get("action_history", [])]
        selected_models = self._validate_debater_models(payload.get("debater_models", {}))
        return session, state, history, selected_models

    def _save_engine(self, session: DebateSession, state: DebateState, history: list[tuple[str, str, tuple[str, ...]]], selected_models: dict[str, str]) -> DebateSession:
        clean = session.model_copy(update={"engine_token": None})
        token = self.codec.encode({"session": clean.model_dump(mode="json"), "debate_state": state.model_dump(mode="json"), "action_history": [[a, b, list(c)] for a, b, c in history], "debater_models": selected_models})
        return clean.model_copy(update={"engine_token": token})

    @staticmethod
    def _scenario(session: DebateSession) -> dict:
        context = json.dumps(session.context_summary, ensure_ascii=False) if session.context_summary else "(없음)"
        fact_anchor = session.fact_anchor or "제공되지 않은 구체적 통계·연구·사건 사실을 만들지 않는다."
        return {
            "motion": session.motion,
            "sides": list(session.side_labels),
            "personas": list(session.personas),
            "tone": session.tone,
            "context": context,
            "fact_anchor": fact_anchor,
            "truth_mode": session.truth_mode,
        }

    @staticmethod
    def _transcript_for_prompt(session: DebateSession) -> list[dict]:
        return [{"speaker": x.speaker, "side": x.side_label, "speech": x.utterance} for x in session.transcript]

    def _commit_generated_turn(self, session: DebateSession, state: DebateState, history, selected_models: dict[str, str], phase: str, speaker: str) -> tuple[str, DebateState, list]:
        phase_lower = phase.lower()
        turn_number = len(session.transcript) + 1
        raw_options = eligible_actions(state, speaker, phase_lower)
        selected = select_action_for_speaker(raw_options, history, speaker, state=state, current_turn=turn_number, persona=session.personas[0 if speaker == "A" else 1])
        if selected is None:
            raise SafeFailure("no eligible debate action")
        target_id = selected.target_ids[0] if selected.target_ids else None
        target_text = next((p.text for p in state.propositions if p.id == target_id), None)
        if target_text is None and target_id:
            target_text = next((q.core_proposition for q in state.questions if q.id == target_id), None)
        turn = {"turn": turn_number, "phase": phase_lower, "speaker": speaker, "side": session.side_labels[0 if speaker == "A" else 1], "persona": session.personas[0 if speaker == "A" else 1]}
        messages = speech_messages(self._scenario(session), turn, self._transcript_for_prompt(session))
        contract = CONTRACTS[selected.name]
        messages[1]["content"] += f"\n선택 Action: {selected.name}, target_ids: {list(selected.target_ids)}, target_text: {target_text or '(없음)'}. Execution Contract: {contract.required_semantic_effect}"
        open_question = next((q for q in reversed(state.questions) if q.asker != speaker and q.resolution == "OPEN"), None)
        if open_question:
            messages[1]["content"] += f"\n먼저 열린 질문 {open_question.id}에 답하세요: {open_question.core_proposition}"

        def generate(feedback: str):
            current = messages if not feedback else [*messages, {"role": "user", "content": feedback}]
            debater_provider = {**self.provider, "model": selected_models[speaker], "stream": True}
            return self.deps.generate_text(debater_provider, current, self.timeout)[0]

        assignment = StanceAssignment(turn["side"], session.side_labels[1 if speaker == "A" else 0])

        def semantic_check(utterance, assigned, current_phase, action, checked_target_text):
            result, _ = self.deps.check_compliance(
                self.provider, action=action, target_id=target_id, target_text=checked_target_text,
                utterance=utterance, assignment=assigned, phase=current_phase, timeout=self.timeout,
            )
            return result

        checked = finalize_compliant_utterance(generate, assignment, selected.name, target_text, phase_lower, semantic_check)
        if not checked.committed:
            raise SafeFailure("utterance compliance rejected")

        def extractor(feedback):
            return self.deps.extract_patch(self.provider, {"turn": turn_number, "speaker": speaker, "speech": checked.utterance}, state, self.timeout, feedback)

        try:
            candidate, _ = extract_and_apply(state, speaker, turn_number, extractor, utterance=checked.utterance)
        except PatchValidationError as exc:
            raise SafeFailure("state patch rejected") from exc
        history = [*history, (speaker, selected.name, selected.target_ids)]
        return checked.utterance, candidate, history

    def debate_step(self, request: DebateStepRequest) -> DebateStepResponse:
        session, state, history, selected_models = self._load_engine(request.session)
        if session.completed:
            session = self._save_engine(session, state, history, selected_models)
            return DebateStepResponse(session=session, phase="COMPLETE", completed=True)

        gate = session.next_index == 8 and session.audience_status == "PENDING"
        if gate:
            if request.command == "NEXT":
                session = self._save_engine(session, state, history, selected_models)
                return DebateStepResponse(session=session, phase="CROSSFIRE", awaiting_audience_question=True)
            if request.command == "SKIP_AUDIENCE":
                session.audience_status = "SKIPPED"
                session = self._save_engine(session, state, history, selected_models)
                return DebateStepResponse(session=session, phase="CROSSFIRE")
            if request.command == "AUDIENCE_QUESTION":
                if not request.audience_question:
                    raise ValueError("관객 질문이 필요합니다.")
                session.audience_status = "ASKED"
                session.audience_question = request.audience_question
                session.audience_response_index = 0
                session = self._save_engine(session, state, history, selected_models)
                return DebateStepResponse(session=session, phase="CROSSFIRE")

        if session.audience_status == "ASKED" and session.audience_response_index < 2:
            phase, speaker = "AUDIENCE_RESPONSE", ("A" if session.audience_response_index == 0 else "B")
            utterance, state, history = self._commit_generated_turn(session, state, history, selected_models, phase, speaker)
            item = TranscriptItem(turn=len(session.transcript)+1, phase=phase, speaker=speaker, side_label=session.side_labels[0 if speaker == "A" else 1], utterance=utterance)
            session.transcript.append(item)
            session.audience_response_index += 1
            if session.audience_response_index == 2:
                session.audience_status = "DONE"
            session = self._save_engine(session, state, history, selected_models)
            return DebateStepResponse(session=session, phase=phase, speaker=speaker, side_label=item.side_label, utterance=utterance)

        if session.next_index >= len(self._base_schedule):
            session.completed = True
            session = self._save_engine(session, state, history, selected_models)
            return DebateStepResponse(session=session, phase="COMPLETE", completed=True)

        phase, speaker = self._base_schedule[session.next_index]
        utterance, state, history = self._commit_generated_turn(session, state, history, selected_models, phase, speaker)
        item = TranscriptItem(turn=len(session.transcript)+1, phase=phase, speaker=speaker, side_label=session.side_labels[0 if speaker == "A" else 1], utterance=utterance)
        session.transcript.append(item)
        session.next_index += 1
        if session.next_index >= len(self._base_schedule):
            session.completed = True
        session = self._save_engine(session, state, history, selected_models)
        return DebateStepResponse(session=session, phase=phase, speaker=speaker, side_label=item.side_label, utterance=utterance, completed=session.completed)
