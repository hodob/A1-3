"""One provider call, three independent validation domains: action, stance, and turn-task progress."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import time
import urllib.error
import urllib.request
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from .action_execution_contracts import CONTRACTS
from .action_fidelity import ActionFidelityLabel
from .provider_adapter import CURRENT_PROVIDER, ProviderAdapter
from .provider_transport import request_completion
from .stance_compliance import StanceAssignment, StanceLabel, validate_utterance


class TaskFidelityLabel(str, Enum):
    ADVANCES_TASK = "ADVANCES_TASK"
    PARTIAL = "PARTIAL"
    REPHRASES_ONLY = "REPHRASES_ONLY"
    OFF_TASK = "OFF_TASK"


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
    task_fidelity: TaskFidelityLabel
    task_reason: str = Field(min_length=1)


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
    task_fidelity: TaskFidelityLabel = TaskFidelityLabel.ADVANCES_TASK
    task_reason: str = "Turn task was not separately evaluated."


@dataclass(frozen=True)
class GuardedUtterance:
    committed: bool
    utterance: str | None
    raw_utterance: str | None
    assessment: CombinedComplianceAssessment
    attempts: int
    diagnostic_flag: bool
    checks: tuple[dict, ...]


def judge_combined(provider: dict, *, action: str, target_id: str | None, target_text: str | None, utterance: str, assignment: StanceAssignment, phase: str, timeout: float, turn_task: str | None = None) -> tuple[CombinedComplianceAssessment, dict]:
    contract = CONTRACTS[action]
    instructions = (
        "서로 독립적인 두 계약을 한 번에 판정하세요. Action Fidelity는 선택된 action이 정확한 target에 required semantic effect를 실제 수행했는지 봅니다. "
        "Action label: ALIGNED, PARTIALLY_ALIGNED, MISALIGNED, UNCLEAR. ALIGNED는 required effect가 중심 기능입니다. PARTIALLY_ALIGNED는 Action을 실제 target에 수행하지만 일부가 다른 전략으로 이동한 경우입니다. "
        "PARTIALLY_ALIGNED이면 primary_action_performed, target_used, action_is_core_function, additional_move_protocol_compliant를 각각 판정하세요. Stance Compliance는 Assigned Thesis 자체의 의미적 reversal만 차단하며 국소 양보·세부 수정·불확실성은 허용합니다. "
        "Stance label: SUPPORTS_ASSIGNED, COMPATIBLE_WITH_ASSIGNED, AMBIGUOUS, CONTRADICTS_ASSIGNED. "
        "turn_task가 제공되면 그 과제를 실제로 진전시켰는지도 독립적으로 판정하세요. Task label: ADVANCES_TASK, PARTIAL, REPHRASES_ONLY, OFF_TASK. "
        "REPHRASES_ONLY는 기존 논지를 말만 바꿔 반복하고 새로운 해결·비교·반례 처리·질문 해결이 없는 경우입니다. 단, turn_task가 CRYSTALLIZE이면 기존 논거를 짧게 압축·weighing하는 것이 과제 자체이므로 새 근거가 없어도 충실한 압축은 ADVANCES_TASK입니다. action, stance, task의 이유를 쓰고 compliance_verdict 도구를 호출하세요."
    )
    payload = {
        "action_contract": {"action": contract.action, "target_type": contract.target_type, "required_semantic_effect": contract.required_semantic_effect, "allowed_realization": contract.allowed_realization, "failure_patterns": contract.failure_patterns},
        "target_id": target_id, "target_text": target_text, "utterance": utterance,
        "assigned_thesis": assignment.assigned_thesis, "opposing_thesis": assignment.opposing_thesis, "phase": phase, "turn_task": turn_task,
    }
    adapter = ProviderAdapter(CURRENT_PROVIDER)
    body = adapter.build_structured_body(provider["model"], [{"role": "system", "content": instructions}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], CombinedComplianceWireVerdict, "compliance_verdict")
    started = time.monotonic()
    try:
        response_payload = request_completion(provider, body, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc.reason}") from exc
    verdict = adapter.parse_structured_response(response_payload, CombinedComplianceWireVerdict, "compliance_verdict")
    assessment = CombinedComplianceAssessment(verdict.action_fidelity, verdict.stance_compliance, verdict.action_reason, verdict.stance_reason, verdict.primary_action_performed, verdict.target_used, verdict.action_is_core_function, verdict.additional_move_protocol_compliant, verdict.task_fidelity, verdict.task_reason)
    return assessment, {"usage": response_payload.get("usage"), "elapsed_seconds": round(time.monotonic() - started, 3)}


def finalize_compliant_utterance(
    generate: Callable[[str], str], assignment: StanceAssignment, action: str, target_text: str | None, phase: str,
    semantic_check: Callable[[str, StanceAssignment, str, str, str | None], CombinedComplianceAssessment],
    *, turn_task: str | None = None, on_check: Callable[[dict], None] | None = None,
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
        task_ok = turn_task is None or semantic.task_fidelity in (TaskFidelityLabel.ADVANCES_TASK, TaskFidelityLabel.PARTIAL)
        accepted = action_ok and stance_ok and task_ok
        checks.append({"attempt": attempt, "action_fidelity": semantic.action_fidelity.value, "stance_compliance": stance.value, "task_fidelity": semantic.task_fidelity.value, "action_reason": semantic.action_reason, "stance_reason": semantic.stance_reason, "task_reason": semantic.task_reason, "partial_policy": {"primary_action_performed": semantic.primary_action_performed, "target_used": semantic.target_used, "action_is_core_function": semantic.action_is_core_function, "additional_move_protocol_compliant": semantic.additional_move_protocol_compliant, "accepted": partial_ok if semantic.action_fidelity == ActionFidelityLabel.PARTIALLY_ALIGNED else None}, "accepted": accepted})
        if accepted:
            return GuardedUtterance(True, utterance, first, CombinedComplianceAssessment(semantic.action_fidelity, stance, semantic.action_reason, semantic.stance_reason, semantic.primary_action_performed, semantic.target_used, semantic.action_is_core_function, semantic.additional_move_protocol_compliant, semantic.task_fidelity, semantic.task_reason), attempt, semantic.action_fidelity == ActionFidelityLabel.PARTIALLY_ALIGNED or semantic.task_fidelity == TaskFidelityLabel.PARTIAL, tuple(checks))
        feedback = (
            f"이전 출력 검증 실패: action_fidelity={semantic.action_fidelity.value}, stance_compliance={stance.value}, task_fidelity={semantic.task_fidelity.value}. "
            f"Action은 {action}이며 target은 {target_text or '(없음)'}입니다. Turn Task는 {turn_task or '(없음)'}입니다. Assigned Stance는 {assignment.assigned_thesis}입니다. "
            "국소 양보·세부 수정은 가능하지만 선택 Action을 target에 실제 수행하고 입장을 명확히 유지해 한 번만 다시 작성하세요."
        )
    final = CombinedComplianceAssessment(semantic.action_fidelity, stance, semantic.action_reason, semantic.stance_reason, semantic.primary_action_performed, semantic.target_used, semantic.action_is_core_function, semantic.additional_move_protocol_compliant, semantic.task_fidelity, semantic.task_reason)
    return GuardedUtterance(False, None, first, final, 2, False, tuple(checks))
