"""One-session live smoke diagnostic with a strict token budget.

The smoke is intentionally short but crosses the provider paths that matter most:
structured topic analysis, text generation, combined action/stance compliance,
state patch extraction/application, signed-session recovery, and neutral summary.
It can be fully TDD-tested by wrapping fake dependencies before any real API call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import AnalyzeTopicRequest, CreateMotionRequest, DebateSession, DebateStepRequest, NeutralSummaryRequest
from .live_service import LiveDebateWebService, LiveRuntimeDependencies
from .session_token import SessionTokenCodec
from src.debate_engine.debate_contracts import DebateState


class SmokeBudgetExceeded(RuntimeError):
    """Raised before starting another provider call when the remaining budget is too small."""


@dataclass(frozen=True)
class SmokePlan:
    topic: str = "핫도그는 샌드위치인가?"
    debate_turns: int = 3
    max_total_tokens: int = 20_000

    def __post_init__(self) -> None:
        if not 1 <= self.debate_turns <= 3:
            raise ValueError("debate_turns must be 1..3 for the minimal smoke")
        if self.max_total_tokens < 1_000:
            raise ValueError("max_total_tokens is too small for a useful live smoke")


def _usage(metadata: dict | None) -> dict[str, int]:
    raw = (metadata or {}).get("usage") or {}
    prompt = int(raw.get("prompt_tokens", raw.get("input_tokens", 0)) or 0)
    completion = int(raw.get("completion_tokens", raw.get("output_tokens", 0)) or 0)
    total = int(raw.get("total_tokens", prompt + completion) or 0)
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}


class MeteredDependencies(LiveRuntimeDependencies):
    """Records live-provider usage without changing the validated runtime contracts."""

    def __init__(self, inner: LiveRuntimeDependencies | None = None, *, max_total_tokens: int = 20_000, min_call_reserve_tokens: int = 100):
        self.inner = inner or LiveRuntimeDependencies()
        self.max_total_tokens = max_total_tokens
        self.min_call_reserve_tokens = min_call_reserve_tokens
        self.records: list[dict[str, Any]] = []
        self.compliance_failures = 0

    @property
    def total_tokens(self) -> int:
        return sum(record["usage"]["total_tokens"] for record in self.records)

    def _before(self) -> None:
        if self.total_tokens + self.min_call_reserve_tokens > self.max_total_tokens:
            raise SmokeBudgetExceeded(
                f"live smoke token budget exhausted: {self.total_tokens}/{self.max_total_tokens}"
            )

    def _record(self, purpose: str, metadata: dict | None, **details: Any) -> None:
        usage = _usage(metadata)
        self.records.append({"purpose": purpose, "usage": usage, **details})
        if self.total_tokens > self.max_total_tokens:
            raise SmokeBudgetExceeded(
                f"live smoke token budget exceeded after {purpose}: {self.total_tokens}/{self.max_total_tokens}"
            )

    def generate_text(self, provider, messages, timeout=90):
        self._before()
        result, metadata = self.inner.generate_text(provider, messages, timeout)
        self._record("utterance_generation", metadata, model=provider.get("model"), chars=len(result))
        return result, metadata

    def check_compliance(self, provider, **kwargs):
        self._before()
        result, metadata = self.inner.check_compliance(provider, **kwargs)
        action = getattr(result.action_fidelity, "value", str(result.action_fidelity))
        stance = getattr(result.stance_compliance, "value", str(result.stance_compliance))
        if action not in ("ALIGNED", "PARTIALLY_ALIGNED") or stance not in ("SUPPORTS_ASSIGNED", "COMPATIBLE_WITH_ASSIGNED"):
            self.compliance_failures += 1
        self._record("combined_compliance", metadata, model=provider.get("model"), action_fidelity=action, stance_compliance=stance)
        return result, metadata

    def extract_patch(self, provider, turn, state, timeout, feedback=None):
        self._before()
        patch, metadata = self.inner.extract_patch(provider, turn, state, timeout, feedback)
        counts: dict[str, int] = {}
        for op in patch.operations:
            counts[op.op] = counts.get(op.op, 0) + 1
        self._record("state_patch", metadata, model=provider.get("model"), turn=turn.get("turn"), operations=counts, repair=bool(feedback))
        return patch, metadata

    def structured(self, provider, messages, contract, tool_name, timeout=90):
        self._before()
        result, metadata = self.inner.structured(provider, messages, contract, tool_name, timeout)
        self._record(tool_name, metadata, model=provider.get("model"))
        return result, metadata

    def usage_summary(self) -> dict[str, int]:
        return {
            "prompt_tokens": sum(x["usage"]["prompt_tokens"] for x in self.records),
            "completion_tokens": sum(x["usage"]["completion_tokens"] for x in self.records),
            "total_tokens": self.total_tokens,
            "calls": len(self.records),
        }


def _state_issues(state: DebateState) -> list[str]:
    proposition_ids = {p.id for p in state.propositions}
    question_ids = {q.id for q in state.questions}
    issues: list[str] = []
    for relation in state.relations:
        if relation.from_proposition_id not in proposition_ids or relation.to_proposition_id not in proposition_ids:
            issues.append(f"dangling_relation:{relation.id}")
    for question in state.questions:
        if question.target_proposition_id and question.target_proposition_id not in proposition_ids:
            issues.append(f"dangling_question_target:{question.id}")
    for event in state.commitment_events:
        if event.proposition_id not in proposition_ids:
            issues.append(f"dangling_commitment:{event.proposition_id}")
    for event in state.question_response_events:
        if event.get("question_id") not in question_ids:
            issues.append(f"dangling_question_response:{event.get('question_id')}")
    return issues


def run_smoke(
    service: LiveDebateWebService,
    codec: SessionTokenCodec,
    deps: MeteredDependencies,
    plan: SmokePlan,
) -> dict[str, Any]:
    """Run one short diagnostic session. It does not require the debate to complete."""
    if deps.max_total_tokens > plan.max_total_tokens:
        raise ValueError("meter budget must not exceed smoke plan budget")

    analysis = service.analyze_topic(AnalyzeTopicRequest(topic=plan.topic))
    if analysis.interaction_state not in ("READY", "CONFIRMATION_REQUIRED"):
        raise RuntimeError(f"smoke topic routed away from debate: {analysis.interaction_state}")
    motion = service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
    session = DebateSession(
        motion=motion.motion,
        side_labels=motion.side_labels,
        personas=motion.personas,
        tone=motion.tone,
        context_summary=motion.context_summary,
        fact_anchor=motion.fact_anchor,
        truth_mode=motion.truth_mode,
    )

    speakers: list[str] = []
    phases: list[str] = []
    for _ in range(plan.debate_turns):
        step = service.debate_step(DebateStepRequest(session=session, command="NEXT"))
        if not step.utterance or not step.speaker:
            raise RuntimeError("smoke debate step did not produce an utterance")
        session = step.session
        speakers.append(step.speaker)
        phases.append(step.phase)

    if not session.engine_token:
        raise RuntimeError("live smoke did not produce a signed engine token")
    payload = codec.decode(session.engine_token)
    selected_models = payload["debater_models"]
    state = DebateState.model_validate(payload["debate_state"])
    state_issues = _state_issues(state)

    summary = service.neutral_summary(NeutralSummaryRequest(motion=session.motion, transcript=session.transcript))
    summary_ok = bool(summary.key_clashes and summary.side_a_strong_points and summary.side_b_strong_points)
    usage = deps.usage_summary()
    status = "PASS" if not state_issues and deps.compliance_failures == 0 and summary_ok else "FAIL"
    transcript = [item.model_dump(mode="json") for item in session.transcript]
    coverage = {
        "topic_analysis": "topic_analysis" in [record["purpose"] for record in deps.records],
        "utterance_generation": "utterance_generation" in [record["purpose"] for record in deps.records],
        "combined_compliance": "combined_compliance" in [record["purpose"] for record in deps.records],
        "state_patch": "state_patch" in [record["purpose"] for record in deps.records],
        "relation_extraction_observed": len(state.relations) > 0,
        "question_extraction_observed": len(state.questions) > 0,
        "signed_session_roundtrip": True,
        "neutral_summary": summary_ok,
    }
    return {
        "status": status,
        "topic": plan.topic,
        "claim_type": analysis.claim_type,
        "motion": motion.motion,
        "personas": list(motion.personas),
        "debater_models": selected_models,
        "debate_turns": len(session.transcript),
        "speakers": speakers,
        "phases": phases,
        "transcript": transcript,
        "coverage": coverage,
        "signed_session_roundtrip": True,
        "state_counts": {
            "propositions": len(state.propositions),
            "relations": len(state.relations),
            "questions": len(state.questions),
            "commitment_events": len(state.commitment_events),
        },
        "state_integrity_issues": state_issues,
        "compliance_failures": deps.compliance_failures,
        "summary_contract_ok": summary_ok,
        "call_purposes": [record["purpose"] for record in deps.records],
        "calls": deps.records,
        "usage": usage,
        "budget": {"max_total_tokens": plan.max_total_tokens, "remaining_tokens": plan.max_total_tokens - usage["total_tokens"]},
    }
