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
from typing import Callable
from html import escape as xml_escape

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
from src.debate_engine.debate_control import TurnTask, TurnTaskKind, plan_turn_task
from src.debate_engine.combined_compliance import finalize_compliant_utterance, judge_combined
from src.debate_engine.surface_contract import extract_state_references, validate_surface
from src.debate_engine.debate_contracts import DebateState, PatchEnvelope, PatchValidationError
from src.debate_engine.debate_harness import call_model, speech_messages
from src.debate_engine.provider_adapter import CURRENT_PROVIDER, ProviderAdapter
from src.debate_engine.provider_transport import request_completion
from src.debate_engine.stance_compliance import StanceAssignment
from src.debate_engine.state_harness import call_patch, extract_and_apply
from src.runtime_config import DebaterModelConfig


class LiveRuntimeDependencies:
    def generate_text(self, provider, messages, timeout=90, on_delta=None):
        return call_model(provider, messages, timeout=timeout, on_delta=on_delta)

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


class NoValuableMove(RuntimeError):
    def __init__(self, task: TurnTask):
        self.task = task
        super().__init__(task.description)


class LiveDebateWebService:
    _base_schedule = [
        ("OPENING", "A"), ("OPENING", "B"),
        ("CROSSFIRE", "A"), ("CROSSFIRE", "B"), ("CROSSFIRE", "A"), ("CROSSFIRE", "B"), ("CROSSFIRE", "A"), ("CROSSFIRE", "B"),
        ("REBUTTAL", "A"), ("REBUTTAL", "B"),
        ("FINAL_FOCUS", "A"), ("FINAL_FOCUS", "B"),
    ]

    def __init__(self, provider: dict, debater_models: tuple[DebaterModelConfig, ...], codec: SessionTokenCodec, deps: LiveRuntimeDependencies | None = None, *, timeout: float = 90, rng: random.Random | None = None, debug_mode: bool = False):
        self.provider = provider
        self.debater_models = tuple(DebaterModelConfig.model_validate(item) for item in debater_models)
        if len(self.debater_models) < 2 or len({item.company for item in self.debater_models}) != len(self.debater_models) or len({item.id for item in self.debater_models}) != len(self.debater_models):
            raise ValueError("debater_models must contain distinct companies and models")
        self.codec = codec
        self.deps = deps or LiveRuntimeDependencies()
        self.timeout = timeout
        self.rng = rng or random.SystemRandom()
        self.debug_mode = bool(debug_mode)

    def _debug(self, on_event: Callable[[str, dict], None] | None, event: str, **payload) -> None:
        if self.debug_mode and on_event is not None:
            on_event("debug", {"event": event, **payload})

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
            "side_labels는 대칭적이고 비평가적인 두 짧은 이름으로 만드세요. treatment_mode와 별개로 표현 강도를 위한 tone_hint도 고르세요: 가벼운 음식 취향·말장난·저위험 비교는 PLAYFUL, 개인 분쟁·정책·사실 민감 주제는 SERIOUS가 기본입니다. topic_analysis 도구를 호출하세요."
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
        tone = request.analysis.tone_hint or ("PLAYFUL" if request.analysis.treatment_mode == "PLAYFUL_DEBATE" else "SERIOUS")
        return MotionResponse(motion=motion, side_labels=side_labels, personas=personas, tone=tone, edit_count=edit_count, context_summary=request.context_summary, fact_anchor=request.analysis.fact_anchor, truth_mode=request.analysis.truth_mode)

    def neutral_summary(self, request: NeutralSummaryRequest) -> NeutralSummaryResponse:
        system = (
            "토론을 중립적으로 정리하세요. 승자, 점수, 어느 쪽이 더 낫다는 판정을 하지 마세요. "
            "transcript의 [[C24]], [[Q3]] 같은 State reference marker는 내부 citation 문법이므로 요약 결과에 그대로 복사하지 말고 자연어 의미만 반영하세요. "
            "핵심 clash, A/B의 강한 논점, 합의, 미해결 쟁점을 각각 짧은 목록으로 반환하고 neutral_summary 도구를 호출하세요."
        )
        payload = {"motion": request.motion, "transcript": [x.model_dump() for x in request.transcript]}
        result, _ = self.deps.structured(self.provider, [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], NeutralSummaryResponse, "neutral_summary", self.timeout)
        return result

    def _new_engine(self, session: DebateSession) -> dict:
        selected_models = self._select_debater_models()
        clean = session.model_copy(update={"engine_token": None, "debater_models": selected_models, "debug_enabled": self.debug_mode})
        return {"session": clean.model_dump(mode="json"), "debate_state": DebateState().model_dump(mode="json"), "action_history": [], "debater_models": selected_models}

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
        session = session.model_copy(update={"debater_models": selected_models, "debug_enabled": self.debug_mode})
        return session, state, history, selected_models

    def _save_engine(self, session: DebateSession, state: DebateState, history: list[tuple[str, str, tuple[str, ...]]], selected_models: dict[str, str]) -> DebateSession:
        clean = session.model_copy(update={"engine_token": None, "debater_models": selected_models, "debug_enabled": self.debug_mode})
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

    def _commit_generated_turn(self, session: DebateSession, state: DebateState, history, selected_models: dict[str, str], phase: str, speaker: str, on_event: Callable[[str, dict], None] | None = None, *, turn_task: TurnTask | None = None) -> tuple[str, DebateState, list, TurnTask, list[dict]]:
        phase_lower = phase.lower()
        turn_number = len(session.transcript) + 1
        task = turn_task or plan_turn_task(
            state,
            speaker=speaker,
            phase=phase_lower,
            audience_question=session.audience_question if phase_lower == "audience_response" else None,
        )
        if task.kind == TurnTaskKind.NO_VALUABLE_MOVE:
            raise NoValuableMove(task)

        raw_options = eligible_actions(state, speaker, phase_lower, turn_task=task)
        selected = select_action_for_speaker(
            raw_options,
            history,
            speaker,
            state=state,
            current_turn=turn_number,
            persona=session.personas[0 if speaker == "A" else 1],
        )
        if selected is None:
            raise NoValuableMove(TurnTask(TurnTaskKind.NO_VALUABLE_MOVE, (), f"{task.kind.value}를 수행할 적법한 Action×Target 후보가 없습니다."))

        def reference_info(ref_id: str) -> dict | None:
            proposition = next((p for p in state.propositions if p.id == ref_id), None)
            if proposition is not None:
                return {"id": ref_id, "speaker": proposition.speaker, "turn": proposition.turn, "text": proposition.text, "kind": "CLAIM"}
            question = next((q for q in state.questions if q.id == ref_id), None)
            if question is not None:
                return {"id": ref_id, "speaker": question.asker, "turn": question.source_turn_id, "text": question.core_proposition, "kind": "QUESTION"}
            return None

        def target_contract(candidate) -> tuple[str | None, str | None]:
            target_texts = []
            for ref_id in candidate.target_ids:
                info = reference_info(ref_id)
                if info:
                    target_texts.append(f"{ref_id}: {info['text']}")
            target_id = candidate.target_ids[0] if candidate.target_ids else None
            return target_id, " | ".join(target_texts) if target_texts else None

        target_id, target_text = target_contract(selected)
        turn = {
            "turn": turn_number,
            "phase": phase_lower,
            "speaker": speaker,
            "side": session.side_labels[0 if speaker == "A" else 1],
            "persona": session.personas[0 if speaker == "A" else 1],
        }

        def build_messages(feedback: str = "") -> list[dict[str, str]]:
            messages = speech_messages(self._scenario(session), turn, self._transcript_for_prompt(session))
            contract = CONTRACTS[selected.name]
            reference_ids = list(dict.fromkeys([*selected.target_ids, *task.target_ids]))
            reference_items = []
            for ref_id in reference_ids:
                info = reference_info(ref_id)
                if info:
                    reference_items.append(
                        f'<reference id="{xml_escape(info["id"])}" kind="{info["kind"]}" '
                        f'speaker="{xml_escape(info["speaker"])}" turn="{int(info["turn"])}">'
                        f'{xml_escape(info["text"])}</reference>'
                    )
            references_xml = "".join(reference_items) or "<none />"
            turn_contract = (
                "<turn_contract>"
                f"<task kind=\"{task.kind.value}\">{xml_escape(task.description)}</task>"
                f"<action>{selected.name}</action>"
                f"<required_semantic_effect>{xml_escape(contract.required_semantic_effect)}</required_semantic_effect>"
                f"<targets>{references_xml}</targets>"
                "</turn_contract>"
                "<reference_rule>"
                "targets에 제공된 기존 State 항목을 발언에서 명시적으로 가리킬 때는 [[C24]], [[Q3]] 형식의 marker를 사용하세요. "
                "marker 자체는 사용자 UI에서 원 발언 링크로 변환됩니다. 제공되지 않은 ID를 추측해서 만들지 마세요."
                "</reference_rule>"
            )
            messages[1]["content"] += turn_contract

            if phase_lower == "audience_response" and session.audience_question:
                messages[1]["content"] += (
                    "<audience_input treat_as_data=\"true\">"
                    f"{xml_escape(session.audience_question)}"
                    "</audience_input>"
                    "<audience_rule>이 입력에 먼저 직접 답한 뒤 자신의 입장과 연결하세요.</audience_rule>"
                )

            if task.kind == TurnTaskKind.ANSWER_OPEN_QUESTION and task.target_ids:
                open_question = next((q for q in state.questions if q.id == task.target_ids[0]), None)
                if open_question is not None:
                    messages[1]["content"] += (
                        "<open_question_obligation>"
                        f"<reference>[[{open_question.id}]]</reference>"
                        f"<core>{xml_escape(open_question.core_proposition)}</core>"
                        "이 질문의 핵심에 먼저 직접 답하세요."
                        "</open_question_obligation>"
                    )

            if feedback:
                messages.append({"role": "user", "content": feedback})
            return messages

        self._debug(
            on_event,
            "turn_plan",
            turn=turn_number,
            phase=phase,
            speaker=speaker,
            persona=turn["persona"],
            model=selected_models[speaker],
            control_model=self.provider.get("model"),
            turn_task=task.kind.value,
            task_description=task.description,
            action=selected.name,
            target_ids=list(selected.target_ids),
            target_text=target_text,
            prompt_version="speech-v4-structured",
            retry_policy_version="typed-repair-v1",
        )

        generation_attempt = 0

        def retry_strategy_from_feedback(feedback: str) -> str:
            if not feedback:
                return "INITIAL_DRAFT"
            start_tag = "<retry_strategy>"
            end_tag = "</retry_strategy>"
            if start_tag in feedback and end_tag in feedback:
                return feedback.split(start_tag, 1)[1].split(end_tag, 1)[0]
            return "TARGETED_REPAIR"

        def generate(feedback: str):
            nonlocal generation_attempt
            generation_attempt += 1
            current = build_messages(feedback)
            debater_provider = {**self.provider, "model": selected_models[speaker], "stream": True}
            retry_strategy = retry_strategy_from_feedback(feedback)
            self._debug(
                on_event,
                "draft_reset",
                turn=turn_number,
                speaker=speaker,
                phase=phase,
                attempt=generation_attempt,
                max_attempts=3,
                reason=retry_strategy,
                feedback=feedback or None,
                model=selected_models[speaker],
            )
            if on_event is None:
                utterance, metadata = self.deps.generate_text(debater_provider, current, self.timeout)
            else:
                on_event(
                    "draft_reset",
                    {
                        "speaker": speaker,
                        "phase": phase,
                        "side_label": turn["side"],
                        "attempt": generation_attempt,
                        "max_attempts": 3,
                        "retry_strategy": retry_strategy,
                    },
                )
                utterance, metadata = self.deps.generate_text(
                    debater_provider,
                    current,
                    self.timeout,
                    on_delta=lambda piece: on_event("draft_delta", {"text": piece}),
                )
            self._debug(
                on_event,
                "draft_completed",
                turn=turn_number,
                speaker=speaker,
                attempt=generation_attempt,
                model=selected_models[speaker],
                utterance=utterance,
                usage=(metadata or {}).get("usage"),
                finish_reason=(metadata or {}).get("finish_reason"),
            )
            return utterance

        assignment = StanceAssignment(turn["side"], session.side_labels[1 if speaker == "A" else 0])
        compliance_metadata: list[dict] = []

        def semantic_check(utterance, assigned, current_phase, action, checked_target_text):
            current_target_id = selected.target_ids[0] if selected.target_ids else None
            result, metadata = self.deps.check_compliance(
                self.provider,
                action=action,
                target_id=current_target_id,
                target_text=checked_target_text,
                utterance=utterance,
                assignment=assigned,
                phase=current_phase,
                timeout=self.timeout,
                turn_task=f"{task.kind.value}: {task.description}",
            )
            compliance_metadata.append(metadata or {})
            return result

        def local_validate(utterance: str) -> list[dict]:
            exposed_reference_ids = set(selected.target_ids) | set(task.target_ids)
            return [
                issue.as_dict()
                for issue in validate_surface(
                    utterance,
                    phase=phase_lower,
                    allowed_reference_ids=exposed_reference_ids,
                )
            ]

        def on_check(check: dict):
            metadata = {} if check.get("semantic_skipped") else (compliance_metadata[-1] if compliance_metadata else {})
            self._debug(
                on_event,
                "compliance",
                turn=turn_number,
                speaker=speaker,
                model=self.provider.get("model"),
                usage=metadata.get("usage"),
                **check,
            )

        def on_replan(check: dict) -> tuple[str, str | None] | None:
            nonlocal selected, target_id, target_text
            prior = [*history, (speaker, selected.name, selected.target_ids)]
            alternatives = eligible_actions(state, speaker, phase_lower, turn_task=task)
            candidate = select_action_for_speaker(
                alternatives,
                prior,
                speaker,
                state=state,
                current_turn=turn_number,
                persona=turn["persona"],
            )
            if candidate is None or (candidate.name, candidate.target_ids) == (selected.name, selected.target_ids):
                return None
            old = selected
            selected = candidate
            target_id, target_text = target_contract(selected)
            self._debug(
                on_event,
                "turn_replanned",
                turn=turn_number,
                speaker=speaker,
                failure_codes=check.get("failure_codes", []),
                from_action=old.name,
                from_target_ids=list(old.target_ids),
                to_action=selected.name,
                to_target_ids=list(selected.target_ids),
                target_text=target_text,
            )
            return selected.name, target_text

        checked = finalize_compliant_utterance(
            generate,
            assignment,
            selected.name,
            target_text,
            phase_lower,
            semantic_check,
            turn_task=task.kind.value,
            on_check=on_check,
            local_validate=local_validate,
            on_replan=on_replan,
            max_attempts=3,
        )
        if not checked.committed:
            self._debug(
                on_event,
                "turn_failed",
                turn=turn_number,
                speaker=speaker,
                attempts=checked.attempts,
                checks=list(checked.checks),
            )
            raise SafeFailure("utterance compliance rejected")

        references = extract_state_references(checked.utterance, state)

        def extractor(feedback):
            return self.deps.extract_patch(
                self.provider,
                {
                    "turn": turn_number,
                    "speaker": speaker,
                    "phase": phase_lower,
                    "turn_task": task.kind.value,
                    "action": selected.name,
                    "target_ids": list(selected.target_ids),
                    "target_text": target_text,
                    "speech": checked.utterance,
                },
                state,
                self.timeout,
                feedback,
            )

        try:
            candidate_state, patch_attempts = extract_and_apply(
                state,
                speaker,
                turn_number,
                extractor,
                utterance=checked.utterance,
            )
        except PatchValidationError as exc:
            self._debug(
                on_event,
                "state_patch_failed",
                turn=turn_number,
                speaker=speaker,
                issues=[issue.as_dict() for issue in exc.issues],
            )
            raise SafeFailure("state patch rejected") from exc

        compact_attempts = []
        for attempt in patch_attempts:
            item = {"valid": bool(attempt.get("valid"))}
            if attempt.get("patch") is not None:
                item["patch"] = attempt["patch"]
            if attempt.get("issues") is not None:
                item["issues"] = attempt["issues"]
            metadata = attempt.get("metadata") or {}
            if metadata.get("usage") is not None:
                item["usage"] = metadata.get("usage")
            if metadata.get("context_counts") is not None:
                item["context_counts"] = metadata.get("context_counts")
            compact_attempts.append(item)

        self._debug(
            on_event,
            "state_patch",
            turn=turn_number,
            speaker=speaker,
            model=self.provider.get("model"),
            attempts=compact_attempts,
            state_counts_before={
                "propositions": len(state.propositions),
                "relations": len(state.relations),
                "questions": len(state.questions),
                "commitment_events": len(state.commitment_events),
            },
            state_counts_after={
                "propositions": len(candidate_state.propositions),
                "relations": len(candidate_state.relations),
                "questions": len(candidate_state.questions),
                "commitment_events": len(candidate_state.commitment_events),
            },
        )
        history = [*history, (speaker, selected.name, selected.target_ids)]
        self._debug(
            on_event,
            "turn_committed",
            turn=turn_number,
            speaker=speaker,
            model=selected_models[speaker],
            attempts=checked.attempts,
            diagnostic_flag=checked.diagnostic_flag,
            action=selected.name,
            target_ids=list(selected.target_ids),
            turn_task=task.kind.value,
            references=references,
        )
        return checked.utterance, candidate_state, history, task, references

    def debate_step(self, request: DebateStepRequest, on_event: Callable[[str, dict], None] | None = None) -> DebateStepResponse:
        session, state, history, selected_models = self._load_engine(request.session)
        if session.completed:
            session = self._save_engine(session, state, history, selected_models)
            return DebateStepResponse(session=session, phase="COMPLETE", completed=True)

        def save() -> DebateSession:
            return self._save_engine(session, state, history, selected_models)

        # Audience gate occurs after Crossfire, including an adaptive early close.
        gate = session.next_index == 8 and session.audience_status == "PENDING"
        if gate:
            if request.command == "NEXT":
                session = save()
                return DebateStepResponse(session=session, phase="CROSSFIRE", awaiting_audience_question=True, moderator_decision="AUDIENCE_GATE")
            if request.command == "SKIP_AUDIENCE":
                session.audience_status = "SKIPPED"
                session = save()
                return DebateStepResponse(session=session, phase="CROSSFIRE", moderator_decision="AUDIENCE_SKIPPED")
            if request.command == "AUDIENCE_QUESTION":
                if not request.audience_question:
                    raise ValueError("관객 질문이 필요합니다.")
                session.audience_status = "ASKED"
                session.audience_question = request.audience_question
                session.audience_response_index = 0
                session = save()
                return DebateStepResponse(session=session, phase="CROSSFIRE", moderator_decision="AUDIENCE_QUD_OPENED")

        if session.audience_status == "ASKED" and session.audience_response_index < 2:
            phase, speaker = "AUDIENCE_RESPONSE", ("A" if session.audience_response_index == 0 else "B")
            task = plan_turn_task(state, speaker=speaker, phase="audience_response", audience_question=session.audience_question)
            utterance, state, history, task, references = self._commit_generated_turn(session, state, history, selected_models, phase, speaker, on_event, turn_task=task)
            item = TranscriptItem(turn=len(session.transcript)+1, phase=phase, speaker=speaker, side_label=session.side_labels[0 if speaker == "A" else 1], utterance=utterance, references=references)
            session.transcript.append(item)
            session.audience_response_index += 1
            if session.audience_response_index == 2:
                session.audience_status = "DONE"
            session = self._save_engine(session, state, history, selected_models)
            return DebateStepResponse(session=session, phase=phase, speaker=speaker, side_label=item.side_label, utterance=utterance, turn_task=task.kind.value, moderator_decision="CONTINUE")

        if session.next_index >= len(self._base_schedule):
            session.completed = True
            session = save()
            return DebateStepResponse(session=session, phase="COMPLETE", completed=True, moderator_decision="COMPLETE")

        # A fixed schedule is now a cap, not a quota. If the control plane says there is
        # no valuable Crossfire/Rebuttal move, advance the phase before spending tokens.
        while session.next_index < len(self._base_schedule):
            phase, speaker = self._base_schedule[session.next_index]
            task = plan_turn_task(state, speaker=speaker, phase=phase.lower())
            if task.kind == TurnTaskKind.NO_VALUABLE_MOVE:
                if phase == "CROSSFIRE":
                    session.next_index = 8
                    if session.audience_status == "PENDING":
                        session = save()
                        return DebateStepResponse(session=session, phase="CROSSFIRE", awaiting_audience_question=True, turn_task=task.kind.value, moderator_decision="MOVE_PHASE")
                    continue
                if phase == "REBUTTAL":
                    session.next_index = 10
                    continue

            try:
                utterance, state, history, task, references = self._commit_generated_turn(session, state, history, selected_models, phase, speaker, on_event, turn_task=task)
            except NoValuableMove:
                if phase == "CROSSFIRE":
                    session.next_index = 8
                    if session.audience_status == "PENDING":
                        session = save()
                        return DebateStepResponse(session=session, phase="CROSSFIRE", awaiting_audience_question=True, turn_task=task.kind.value, moderator_decision="MOVE_PHASE")
                    continue
                if phase == "REBUTTAL":
                    session.next_index = 10
                    continue
                raise

            item = TranscriptItem(turn=len(session.transcript)+1, phase=phase, speaker=speaker, side_label=session.side_labels[0 if speaker == "A" else 1], utterance=utterance, references=references)
            session.transcript.append(item)
            session.next_index += 1
            if session.next_index >= len(self._base_schedule):
                session.completed = True
            session = self._save_engine(session, state, history, selected_models)
            return DebateStepResponse(session=session, phase=phase, speaker=speaker, side_label=item.side_label, utterance=utterance, completed=session.completed, turn_task=task.kind.value, moderator_decision="CONTINUE")

        session.completed = True
        session = save()
        return DebateStepResponse(session=session, phase="COMPLETE", completed=True, moderator_decision="COMPLETE")
