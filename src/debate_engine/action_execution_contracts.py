"""Semantic execution contracts for the 15 strategic actions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionContract:
    action: str
    target_type: str
    required_semantic_effect: str
    allowed_realization: tuple[str, ...]
    failure_patterns: tuple[str, ...]


def _c(action, target, required, allowed, failures):
    return ExecutionContract(action, target, required, tuple(allowed), tuple(failures))


CONTRACTS = {item.action: item for item in (
    _c("CLARIFY_CLAIM", "PROPOSITION", "target의 의미, 범위, 용어 또는 조건을 더 명확하게 만들도록 요구한다.", ["용어 정의 요청", "적용 범위 확인", "두 가능한 해석 구분"], ["target 반박만 함", "무관한 질문", "이미 명확한 내용을 그대로 반복 요구"]),
    _c("REQUEST_SUPPORT", "PROPOSITION", "target claim의 근거, 이유 또는 정당화를 실제로 요구한다.", ["근거 질문", "추론 연결 요청", "사례나 자료 요청"], ["자기 근거만 제시", "target을 곧바로 반박", "이미 충분한 근거를 이유 없이 재요구"]),
    _c("CHALLENGE_PREMISE", "PROPOSITION", "target premise의 truth, necessity, applicability 또는 assumption status 중 하나를 문제 삼는다.", ["전제 이유 질문", "항상 성립하는지 질문", "숨은 가정 지적"], ["target을 그대로 지지", "다른 주장만 공격", "단순 clarification"]),
    _c("CHALLENGE_INFERENCE", "PROPOSITION_OR_RELATION", "근거에서 target 결론으로 넘어가는 추론의 타당성 또는 충분성을 문제 삼는다.", ["논리적 비약 지적", "근거가 결론을 보장하는지 질문", "대안 설명 제시"], ["전제의 사실성만 공격", "결론을 반복", "추론 연결을 다루지 않음"]),
    _c("TEST_BOUNDARY", "PROPOSITION", "counterexample, edge case 또는 적용 범위 테스트로 target의 경계를 시험한다.", ["반례 제시", "극단·경계 사례 질문", "조건 변화 테스트"], ["일반 반박만 함", "범위를 시험하지 않는 예시", "target과 무관한 사례"]),
    _c("CHECK_CONSISTENCY", "PROPOSITION_AND_COMMITMENT", "target과 기록된 기존 commitment 사이의 실제 tension을 식별한다.", ["두 발언 인용 후 불일치 질문", "기준의 일관 적용 요구"], ["기록되지 않은 모순 발명", "단순 반박", "수리된 모순을 반복"]),
    _c("SEEK_COMMITMENT", "PROPOSITION_OR_QUESTION", "상대가 특정 proposition, 선택지 또는 기준에 명시적으로 commit하도록 요구한다.", ["예/아니오 입장 요구", "우선 기준 선택 요구", "조건부 동의 범위 확인"], ["열린 설명만 요청", "자기 입장 반복", "무관한 결론 강요"]),
    _c("PRESS_UNANSWERED", "QUESTION", "PARTIAL/EVADED 상태의 열린 질문에서 아직 해결되지 않은 핵심을 다시 요구한다.", ["미답 부분 지적", "동일 핵심에 좁힌 후속 질문"], ["DIRECT/RESOLVED 질문 반복", "새 질문으로 교체", "답변 내용을 무시"]),
    _c("CONCEDE_LOCAL", "PROPOSITION", "상대의 특정 proposition을 명시적으로 수용하되 Assigned Thesis는 뒤집지 않는다.", ["그 점은 인정", "해당 반례 수용", "국소적 장점 인정"], ["동의 없이 들었다고만 함", "즉시 같은 내용을 부정", "전체 thesis reversal"]),
    _c("REVISE_CLAIM", "OWN_PROPOSITION", "기존 자신의 proposition의 범위, 조건 또는 내용을 실제로 변경한다.", ["범위 축소", "조건 추가", "기존 표현 철회 후 대체"], ["같은 주장 재진술", "상대 주장만 수정", "수정한다고 말하지만 내용 불변"]),
    _c("REFUTE_CLAIM", "OPPONENT_PROPOSITION", "target이 거짓, 부적절 또는 결론 지지에 실패함을 이유와 함께 주장한다.", ["직접 반박", "반례로 무효화", "근거 부족이 결론을 약화함을 설명"], ["target 지지", "다른 주장만 반박", "질문만 하고 반박하지 않음"]),
    _c("DEFEND_CLAIM", "OWN_PROPOSITION", "공격받은 target을 이유, 구분 또는 한정으로 실제 방어한다.", ["기존 근거 보강", "반박에 답변", "정당한 qualification"], ["target 철회", "무관한 새 주장", "공격을 무시"]),
    _c("EXTEND_ARGUMENT", "NONE_OR_OWN_PROPOSITION", "현재 입장을 지지하는 새로운 관련 이유 또는 결과를 추가한다.", ["새 supporting reason", "기존 근거의 관련 함의", "초기 argument 제시"], ["상대 입장 강화", "무관한 새 화제", "내용 없는 반복"]),
    _c("WEIGH_COMPARATIVE", "TWO_CONSIDERATIONS", "살아 있는 두 competing consideration을 같은 comparison dimension에서 비교하고 우선순위를 설명한다.", ["비용 기준 비교", "효과 크기·확률·범위·시점 비교", "tradeoff 판정"], ["한쪽 주장만 반복", "서로 다른 차원을 비교", "우선순위 설명 없음"]),
    _c("CRYSTALLIZE", "CURRENT_CLASH", "기존 논증을 핵심 clash와 가장 중요한 이유로 압축하며 새 substantive argument를 만들지 않는다.", ["핵심 충돌 요약", "기존 이유 1~2개로 정리", "최종 weighing 압축"], ["새 근거·사례·통계 추가", "전체 대화 나열", "입장 없는 중립 요약"]),
)}
