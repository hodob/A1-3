"""One provider call, two independent validation domains."""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
import urllib.error
import urllib.request
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from .action_execution_contracts import CONTRACTS
from .action_fidelity import ActionFidelityLabel
from .provider_adapter import CURRENT_PROVIDER, ProviderAdapter
from .stance_compliance import StanceAssignment, StanceLabel, validate_utterance


class CombinedComplianceWireVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_fidelity: ActionFidelityLabel
    stance_compliance: StanceLabel
    action_reason: str = Field(min_length=1)
    stance_reason: str = Field(min_length=1)
    primary_action_performed: bool
    target_used: bool
    action_is_core_function: bool
    additional_move_protocol_compliant: bool


@dataclass(frozen=True)
class CombinedComplianceAssessment:
    action_fidelity: ActionFidelityLabel
    stance_compliance: StanceLabel
    action_reason: str
    stance_reason: str
    primary_action_performed: bool = True
    target_used: bool = True
    action_is_core_function: bool = True
    additional_move_protocol_compliant: bool = True


@dataclass(frozen=True)
class GuardedUtterance:
    committed: bool
    utterance: str | None
    raw_utterance: str | None
    assessment: CombinedComplianceAssessment
    attempts: int
    diagnostic_flag: bool
    checks: tuple[dict, ...]


def judge_combined(provider: dict, *, action: str, target_id: str | None, target_text: str | None, utterance: str, assignment: StanceAssignment, phase: str, timeout: float) -> tuple[CombinedComplianceAssessment, dict]:
    contract = CONTRACTS[action]
    instructions = (
        "서로 독립적인 두 계약을 한 번에 판정하세요. Action Fidelity는 선택된 action이 정확한 target에 required semantic effect를 실제 수행했는지 봅니다. "
        "Action label: ALIGNED, PARTIALLY_ALIGNED, MISALIGNED, UNCLEAR. ALIGNED는 required effect가 중심 기능입니다. PARTIALLY_ALIGNED는 Action을 실제 target에 수행하지만 일부가 다른 전략으로 이동한 경우입니다. "
        "PARTIALLY_ALIGNED이면 primary_action_performed, target_used, action_is_core_function, additional_move_protocol_compliant를 각각 판정하세요. Stance Compliance는 Assigned Thesis 자체의 의미적 reversal만 차단하며 국소 양보·세부 수정·불확실성은 허용합니다. "
        "Stance label: SUPPORTS_ASSIGNED, COMPATIBLE_WITH_ASSIGNED, AMBIGUOUS, CONTRADICTS_ASSIGNED. action과 stance의 이유를 각각 쓰고 compliance_verdict 도구를 호출하세요."
    )
    payload = {
        "action_contract": {"action": contract.action, "target_type": contract.target_type, "required_semantic_effect": contract.required_semantic_effect, "allowed_realization": contract.allowed_realization, "failure_patterns": contract.failure_patterns},
        "target_id": target_id, "target_text": target_text, "utterance": utterance,
        "assigned_thesis": assignment.assigned_thesis, "opposing_thesis": assignment.opposing_thesis, "phase": phase,
    }
    adapter = ProviderAdapter(CURRENT_PROVIDER)
    body = adapter.build_structured_body(provider["model"], [{"role": "system", "content": instructions}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], CombinedComplianceWireVerdict, "compliance_verdict")
    request = urllib.request.Request(provider["url"], data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"}, method="POST")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc.reason}") from exc
    verdict = adapter.parse_structured_response(response_payload, CombinedComplianceWireVerdict, "compliance_verdict")
    assessment = CombinedComplianceAssessment(verdict.action_fidelity, verdict.stance_compliance, verdict.action_reason, verdict.stance_reason, verdict.primary_action_performed, verdict.target_used, verdict.action_is_core_function, verdict.additional_move_protocol_compliant)
    return assessment, {"usage": response_payload.get("usage"), "elapsed_seconds": round(time.monotonic() - started, 3)}


def finalize_compliant_utterance(
    generate: Callable[[str], str], assignment: StanceAssignment, action: str, target_text: str | None, phase: str,
    semantic_check: Callable[[str, StanceAssignment, str, str, str | None], CombinedComplianceAssessment],
) -> GuardedUtterance:
    checks = []
    first = None
    feedback = ""
    for attempt in (1, 2):
        utterance = generate(feedback)
        first = first or utterance
        local_stance = validate_utterance(utterance, assignment, phase=phase)
        semantic = semantic_check(utterance, assignment, phase, action, target_text)
        stance = StanceLabel.CONTRADICTS_ASSIGNED if local_stance.label == StanceLabel.CONTRADICTS_ASSIGNED else semantic.stance_compliance
        partial_ok = all((semantic.primary_action_performed, semantic.target_used, semantic.action_is_core_function, semantic.additional_move_protocol_compliant))
        action_ok = semantic.action_fidelity == ActionFidelityLabel.ALIGNED or (semantic.action_fidelity == ActionFidelityLabel.PARTIALLY_ALIGNED and partial_ok)
        stance_ok = stance in (StanceLabel.SUPPORTS_ASSIGNED, StanceLabel.COMPATIBLE_WITH_ASSIGNED)
        checks.append({"attempt": attempt, "action_fidelity": semantic.action_fidelity.value, "stance_compliance": stance.value, "action_reason": semantic.action_reason, "stance_reason": semantic.stance_reason, "partial_policy": {"primary_action_performed": semantic.primary_action_performed, "target_used": semantic.target_used, "action_is_core_function": semantic.action_is_core_function, "additional_move_protocol_compliant": semantic.additional_move_protocol_compliant, "accepted": partial_ok if semantic.action_fidelity == ActionFidelityLabel.PARTIALLY_ALIGNED else None}, "accepted": action_ok and stance_ok})
        if action_ok and stance_ok:
            return GuardedUtterance(True, utterance, first, CombinedComplianceAssessment(semantic.action_fidelity, stance, semantic.action_reason, semantic.stance_reason), attempt, semantic.action_fidelity == ActionFidelityLabel.PARTIALLY_ALIGNED, tuple(checks))
        feedback = (
            f"이전 출력 검증 실패: action_fidelity={semantic.action_fidelity.value}, stance_compliance={stance.value}. "
            f"Action은 {action}이며 target은 {target_text or '(없음)'}입니다. Assigned Stance는 {assignment.assigned_thesis}입니다. "
            "국소 양보·세부 수정은 가능하지만 선택 Action을 target에 실제 수행하고 입장을 명확히 유지해 한 번만 다시 작성하세요."
        )
    final = CombinedComplianceAssessment(semantic.action_fidelity, stance, semantic.action_reason, semantic.stance_reason)
    return GuardedUtterance(False, None, first, final, 2, False, tuple(checks))
