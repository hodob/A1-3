"""Combined semantic compliance plus typed bounded repair policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from html import escape
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


class FailureCode(str, Enum):
    STANCE_REVERSAL = "STANCE_REVERSAL"
    STANCE_AMBIGUOUS = "STANCE_AMBIGUOUS"
    ACTION_NOT_PERFORMED = "ACTION_NOT_PERFORMED"
    TARGET_NOT_USED = "TARGET_NOT_USED"
    ACTION_NOT_CORE = "ACTION_NOT_CORE"
    ACTION_PROTOCOL_VIOLATION = "ACTION_PROTOCOL_VIOLATION"
    TASK_OFF_TASK = "TASK_OFF_TASK"
    REPHRASE_ONLY = "REPHRASE_ONLY"
    TASK_ACTION_CONFLICT = "TASK_ACTION_CONFLICT"


class RetryStrategy(str, Enum):
    TARGETED_REPAIR = "TARGETED_REPAIR"
    REPLAN_AND_REGENERATE = "REPLAN_AND_REGENERATE"
    HARD_FAILURE = "HARD_FAILURE"


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
        "<role>당신은 토론 발언의 semantic compliance validator입니다.</role>"
        "<independent_checks>"
        "Action Fidelity, Stance Compliance, Turn Task Fidelity를 서로 독립적으로 판정하세요. "
        "한 영역의 실패를 이유로 다른 영역까지 낮추지 마세요."
        "</independent_checks>"
        "<action>"
        "선택된 action이 정확한 target에 required semantic effect를 실제 수행했는지 봅니다. "
        "Label: ALIGNED, PARTIALLY_ALIGNED, MISALIGNED, UNCLEAR. "
        "PARTIALLY_ALIGNED는 Action을 실제 target에 수행하지만 일부가 다른 전략으로 이동한 경우입니다. "
        "이 경우 primary_action_performed, target_used, action_is_core_function, additional_move_protocol_compliant를 각각 판정하세요."
        "</action>"
        "<stance>"
        "Assigned Thesis 자체의 의미적 reversal만 차단합니다. 국소 양보, 세부 수정, 불확실성 표현은 허용합니다. "
        "Label: SUPPORTS_ASSIGNED, COMPATIBLE_WITH_ASSIGNED, AMBIGUOUS, CONTRADICTS_ASSIGNED."
        "</stance>"
        "<turn_task>"
        "turn_task가 제공되면 그 과제를 실제로 진전시켰는지 판정하세요. "
        "Label: ADVANCES_TASK, PARTIAL, REPHRASES_ONLY, OFF_TASK. "
        "REPHRASES_ONLY는 기존 논지를 말만 바꿔 반복하고 새로운 해결, 비교, 반례 처리, 질문 해결이 없는 경우입니다. "
        "단, CRYSTALLIZE는 기존 논거의 짧은 압축과 weighing 자체가 과제이므로 충실한 압축은 ADVANCES_TASK입니다."
        "</turn_task>"
        "각 이유를 간결히 쓰고 compliance_verdict 도구를 호출하세요."
    )
    payload = {
        "action_contract": {
            "action": contract.action,
            "target_type": contract.target_type,
            "required_semantic_effect": contract.required_semantic_effect,
            "allowed_realization": contract.allowed_realization,
            "failure_patterns": contract.failure_patterns,
        },
        "target_id": target_id,
        "target_text": target_text,
        "utterance": utterance,
        "assigned_thesis": assignment.assigned_thesis,
        "opposing_thesis": assignment.opposing_thesis,
        "phase": phase,
        "turn_task": turn_task,
    }
    adapter = ProviderAdapter(CURRENT_PROVIDER)
    body = adapter.build_structured_body(
        provider["model"],
        [{"role": "system", "content": instructions}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        CombinedComplianceWireVerdict,
        "compliance_verdict",
    )
    started = time.monotonic()
    try:
        response_payload = request_completion(provider, body, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc.reason}") from exc
    verdict = adapter.parse_structured_response(response_payload, CombinedComplianceWireVerdict, "compliance_verdict")
    assessment = CombinedComplianceAssessment(
        verdict.action_fidelity,
        verdict.stance_compliance,
        verdict.action_reason,
        verdict.stance_reason,
        verdict.primary_action_performed,
        verdict.target_used,
        verdict.action_is_core_function,
        verdict.additional_move_protocol_compliant,
        verdict.task_fidelity,
        verdict.task_reason,
    )
    return assessment, {"usage": response_payload.get("usage"), "elapsed_seconds": round(time.monotonic() - started, 3)}


def _failure_codes(semantic: CombinedComplianceAssessment, stance: StanceLabel, *, turn_task: str | None, task_primary: bool = False) -> list[str]:
    failures: list[str] = []
    if stance == StanceLabel.CONTRADICTS_ASSIGNED:
        failures.append(FailureCode.STANCE_REVERSAL.value)
    elif stance == StanceLabel.AMBIGUOUS:
        failures.append(FailureCode.STANCE_AMBIGUOUS.value)

    if semantic.action_fidelity in (ActionFidelityLabel.MISALIGNED, ActionFidelityLabel.UNCLEAR):
        failures.append(FailureCode.ACTION_NOT_PERFORMED.value)
    elif semantic.action_fidelity == ActionFidelityLabel.PARTIALLY_ALIGNED and not task_primary:
        if not semantic.primary_action_performed:
            failures.append(FailureCode.ACTION_NOT_PERFORMED.value)
        if not semantic.target_used:
            failures.append(FailureCode.TARGET_NOT_USED.value)
        if not semantic.action_is_core_function:
            failures.append(FailureCode.ACTION_NOT_CORE.value)
        if not semantic.additional_move_protocol_compliant:
            failures.append(FailureCode.ACTION_PROTOCOL_VIOLATION.value)

    if turn_task is not None:
        if semantic.task_fidelity == TaskFidelityLabel.REPHRASES_ONLY:
            failures.append(FailureCode.REPHRASE_ONLY.value)
        elif semantic.task_fidelity == TaskFidelityLabel.OFF_TASK:
            failures.append(FailureCode.TASK_OFF_TASK.value)

    action_failures = {
        FailureCode.ACTION_NOT_PERFORMED.value,
        FailureCode.TARGET_NOT_USED.value,
        FailureCode.ACTION_NOT_CORE.value,
        FailureCode.ACTION_PROTOCOL_VIOLATION.value,
    }
    task_is_good = semantic.task_fidelity in (TaskFidelityLabel.ADVANCES_TASK, TaskFidelityLabel.PARTIAL)
    stance_is_good = stance in (StanceLabel.SUPPORTS_ASSIGNED, StanceLabel.COMPATIBLE_WITH_ASSIGNED)
    if turn_task and task_is_good and stance_is_good and action_failures.intersection(failures):
        failures.append(FailureCode.TASK_ACTION_CONFLICT.value)
    return failures


def _retry_strategy(failures: list[str], *, attempt: int, can_replan: bool) -> RetryStrategy:
    if attempt >= 3:
        return RetryStrategy.HARD_FAILURE
    planner_failures = {FailureCode.REPHRASE_ONLY.value, FailureCode.TASK_ACTION_CONFLICT.value}
    if attempt >= 2 and can_replan and planner_failures.intersection(failures):
        return RetryStrategy.REPLAN_AND_REGENERATE
    return RetryStrategy.TARGETED_REPAIR


def _repair_prompt(
    previous_draft: str,
    check: dict,
    *,
    assignment: StanceAssignment,
    action: str,
    target_text: str | None,
    turn_task: str | None,
    strategy: RetryStrategy,
) -> str:
    failure_lines = []
    for code in check.get("failure_codes", []):
        failure_lines.append(f'<violation code="{escape(code)}" />')
    for issue in check.get("surface_issues", []):
        failure_lines.append(
            f'<violation code="{escape(str(issue.get("code", "SURFACE")))}">'
            f'{escape(str(issue.get("message", "")))}</violation>'
        )
    preserve = []
    if check.get("stance_compliance") in (StanceLabel.SUPPORTS_ASSIGNED.value, StanceLabel.COMPATIBLE_WITH_ASSIGNED.value):
        preserve.append("현재 Assigned Stance와 일치하는 부분")
    if check.get("task_fidelity") in (TaskFidelityLabel.ADVANCES_TASK.value, TaskFidelityLabel.PARTIAL.value):
        preserve.append("이미 수행한 직접 답변 또는 Turn Task 진전")
    if check.get("action_fidelity") == ActionFidelityLabel.ALIGNED.value:
        preserve.append("이미 올바르게 수행한 Action의 핵심")
    preserve.append("현재 단계의 길이와 자연스러운 말투")

    return (
        f'<repair_request attempt="{int(check.get("attempt", 1)) + 1}" max_attempts="3">'
        f'<retry_strategy>{strategy.value}</retry_strategy>'
        f'<previous_draft>{escape(previous_draft)}</previous_draft>'
        f'<violations>{"".join(failure_lines)}</violations>'
        f'<preserve>{"; ".join(escape(item) for item in preserve)}</preserve>'
        f'<current_contract>'
        f'<assigned_stance>{escape(assignment.assigned_thesis)}</assigned_stance>'
        f'<turn_task>{escape(turn_task or "(없음)")}</turn_task>'
        f'<action>{escape(action)}</action>'
        f'<target>{escape(target_text or "(없음)")}</target>'
        f'</current_contract>'
        f'<instruction>'
        f'previous_draft 전체를 무시하고 처음부터 임의로 바꾸지 마세요. preserve 항목은 유지하고 violations만 고치세요. '
        f'{("전략이 재계획되었습니다. current_contract의 새 Action/Target을 기준으로 다시 작성하세요. " if strategy == RetryStrategy.REPLAN_AND_REGENERATE else "")}'
        f'출력은 수정된 토론 발언만 반환하세요.'
        f'</instruction>'
        f'</repair_request>'
    )


def finalize_compliant_utterance(
    generate: Callable[[str], str],
    assignment: StanceAssignment,
    action: str,
    target_text: str | None,
    phase: str,
    semantic_check: Callable[[str, StanceAssignment, str, str, str | None], CombinedComplianceAssessment],
    *,
    turn_task: str | None = None,
    on_check: Callable[[dict], None] | None = None,
    local_validate: Callable[[str], list[dict]] | None = None,
    on_replan: Callable[[dict], tuple[str, str | None] | None] | None = None,
    max_attempts: int = 3,
) -> GuardedUtterance:
    if max_attempts < 1 or max_attempts > 3:
        raise ValueError("max_attempts must be between 1 and 3")

    checks: list[dict] = []
    first: str | None = None
    feedback = ""
    current_action = action
    current_target_text = target_text
    final_assessment = CombinedComplianceAssessment(
        ActionFidelityLabel.UNCLEAR,
        StanceLabel.AMBIGUOUS,
        "검증되지 않음",
        "검증되지 않음",
        task_fidelity=TaskFidelityLabel.OFF_TASK,
        task_reason="검증되지 않음",
    )

    for attempt in range(1, max_attempts + 1):
        utterance = generate(feedback)
        first = first or utterance
        local_stance = validate_utterance(utterance, assignment, phase=phase)
        surface_issues = local_validate(utterance) if local_validate else []

        if surface_issues:
            semantic = CombinedComplianceAssessment(
                ActionFidelityLabel.ALIGNED,
                StanceLabel.SUPPORTS_ASSIGNED,
                "Surface validation이 먼저 실패하여 semantic action 검사를 생략했습니다.",
                "Surface validation이 먼저 실패하여 semantic stance 검사를 생략했습니다.",
                task_fidelity=TaskFidelityLabel.ADVANCES_TASK,
                task_reason="Surface validation이 먼저 실패하여 semantic task 검사를 생략했습니다.",
            )
            semantic_skipped = True
        else:
            semantic = semantic_check(utterance, assignment, phase, current_action, current_target_text)
            semantic_skipped = False

        stance = StanceLabel.CONTRADICTS_ASSIGNED if local_stance.label == StanceLabel.CONTRADICTS_ASSIGNED else semantic.stance_compliance
        task_primary = turn_task in {"ANSWER_OPEN_QUESTION", "ADDRESS_AUDIENCE"}
        failures = _failure_codes(semantic, stance, turn_task=turn_task, task_primary=task_primary)
        failures.extend(issue.get("code", "SURFACE_VIOLATION") for issue in surface_issues)
        failures = list(dict.fromkeys(failures))

        partial_ok = all((
            semantic.primary_action_performed,
            semantic.target_used,
            semantic.action_is_core_function,
            semantic.additional_move_protocol_compliant,
        ))
        action_ok = semantic.action_fidelity == ActionFidelityLabel.ALIGNED or (
            semantic.action_fidelity == ActionFidelityLabel.PARTIALLY_ALIGNED and (partial_ok or task_primary)
        )
        stance_ok = stance in (StanceLabel.SUPPORTS_ASSIGNED, StanceLabel.COMPATIBLE_WITH_ASSIGNED)
        task_ok = turn_task is None or semantic.task_fidelity in (TaskFidelityLabel.ADVANCES_TASK, TaskFidelityLabel.PARTIAL)
        accepted = not surface_issues and action_ok and stance_ok and task_ok
        strategy = RetryStrategy.HARD_FAILURE if accepted else _retry_strategy(
            failures, attempt=attempt, can_replan=on_replan is not None
        )

        check = {
            "attempt": attempt,
            "action": current_action,
            "target_text": current_target_text,
            "action_fidelity": semantic.action_fidelity.value,
            "stance_compliance": stance.value,
            "task_fidelity": semantic.task_fidelity.value,
            "action_reason": semantic.action_reason,
            "stance_reason": semantic.stance_reason,
            "task_reason": semantic.task_reason,
            "partial_policy": {
                "primary_action_performed": semantic.primary_action_performed,
                "target_used": semantic.target_used,
                "action_is_core_function": semantic.action_is_core_function,
                "additional_move_protocol_compliant": semantic.additional_move_protocol_compliant,
                "accepted": partial_ok if semantic.action_fidelity == ActionFidelityLabel.PARTIALLY_ALIGNED else None,
            },
            "surface_issues": surface_issues,
            "semantic_skipped": semantic_skipped,
            "failure_codes": failures,
            "retry_strategy": None if accepted else strategy.value,
            "accepted": accepted,
        }
        checks.append(check)
        if on_check is not None:
            on_check(check)

        final_assessment = CombinedComplianceAssessment(
            semantic.action_fidelity,
            stance,
            semantic.action_reason,
            semantic.stance_reason,
            semantic.primary_action_performed,
            semantic.target_used,
            semantic.action_is_core_function,
            semantic.additional_move_protocol_compliant,
            semantic.task_fidelity,
            semantic.task_reason,
        )
        if accepted:
            return GuardedUtterance(
                True,
                utterance,
                first,
                final_assessment,
                attempt,
                semantic.action_fidelity == ActionFidelityLabel.PARTIALLY_ALIGNED
                or semantic.task_fidelity == TaskFidelityLabel.PARTIAL,
                tuple(checks),
            )

        if attempt >= max_attempts:
            break

        if strategy == RetryStrategy.REPLAN_AND_REGENERATE and on_replan is not None:
            replanned = on_replan(check)
            if replanned is not None:
                current_action, current_target_text = replanned
            else:
                strategy = RetryStrategy.TARGETED_REPAIR

        feedback = _repair_prompt(
            utterance,
            check,
            assignment=assignment,
            action=current_action,
            target_text=current_target_text,
            turn_task=turn_task,
            strategy=strategy,
        )

    return GuardedUtterance(False, None, first, final_assessment, len(checks), False, tuple(checks))
