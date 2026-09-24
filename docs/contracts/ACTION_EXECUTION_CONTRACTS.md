# Strategic Action Execution Contracts

`Action Eligibility`는 현재 State에서 Action을 선택해도 되는지 판정한다. `Action Fidelity`는 생성된 실제 발언이 선택한 Action과 target을 수행했는지 판정한다. C14가 challenge 가능한 전제여도 발언이 C14를 지지하면 Eligibility는 통과하고 Fidelity는 실패한다.

| Action | Target type | Required semantic effect | Allowed realization | Failure patterns |
|---|---|---|---|---|
| CLARIFY_CLAIM | PROPOSITION | 의미·범위·용어·조건을 더 명확하게 하도록 요구 | 정의, 적용 범위, 해석 구분 요청 | 반박만 함, 무관한 질문, 명확한 내용 반복 요구 |
| REQUEST_SUPPORT | PROPOSITION | 근거·이유·정당화를 실제로 요구 | 근거, 추론 연결, 사례·자료 요청 | 자기 근거만 제시, 즉시 반박, 충분한 근거 재요구 |
| CHALLENGE_PREMISE | PROPOSITION | truth·necessity·applicability·assumption status 중 하나를 문제 삼음 | 전제 이유, 항상 성립 여부, 숨은 가정 질문 | target 지지, 다른 주장 공격, clarification만 함 |
| CHALLENGE_INFERENCE | PROPOSITION_OR_RELATION | 근거에서 결론으로 가는 추론의 타당성·충분성을 문제 삼음 | 논리적 비약, 보장 여부, 대안 설명 | 전제 사실성만 공격, 결론 반복, 연결을 다루지 않음 |
| TEST_BOUNDARY | PROPOSITION | 반례·경계 사례·적용 범위로 target 시험 | 반례, 극단 사례, 조건 변화 | 일반 반박, 범위와 무관한 예시, 무관한 사례 |
| CHECK_CONSISTENCY | PROPOSITION_AND_COMMITMENT | target과 기존 commitment의 실제 tension 식별 | 두 발언 대조, 기준 일관 적용 요구 | 모순 발명, 단순 반박, 수리된 모순 반복 |
| SEEK_COMMITMENT | PROPOSITION_OR_QUESTION | 특정 명제·선택·기준에 명시적 commitment 요구 | 예/아니오, 우선 기준, 조건부 동의 요구 | 열린 설명만 요청, 자기 입장 반복, 무관한 결론 강요 |
| PRESS_UNANSWERED | QUESTION | PARTIAL/EVADED 열린 질문의 미해결 핵심 재요구 | 미답 부분 지적, 좁힌 후속 질문 | DIRECT/RESOLVED 반복, 새 질문 교체, 답변 무시 |
| CONCEDE_LOCAL | PROPOSITION | 특정 상대 proposition을 수용하되 Assigned Thesis 유지 | 그 점 인정, 반례 수용, 장점 인정 | 동의 없는 언급, 즉시 부정, thesis reversal |
| REVISE_CLAIM | OWN_PROPOSITION | 자신의 기존 명제 범위·조건·내용을 실제 변경 | 범위 축소, 조건 추가, 철회 후 대체 | 재진술, 상대 주장 수정, 내용 불변 |
| REFUTE_CLAIM | OPPONENT_PROPOSITION | target이 거짓·부적절하거나 결론 지지에 실패함을 이유와 함께 주장 | 직접 반박, 반례, 근거 부족 설명 | target 지지, 다른 주장만 반박, 질문만 함 |
| DEFEND_CLAIM | OWN_PROPOSITION | 공격받은 target을 이유·구분·한정으로 방어 | 근거 보강, 반박 답변, qualification | target 철회, 무관한 새 주장, 공격 무시 |
| EXTEND_ARGUMENT | NONE_OR_OWN_PROPOSITION | 입장을 지지하는 새로운 관련 이유·결과 추가 | supporting reason, 관련 함의, opening argument | 상대 강화, 무관한 화제, 내용 없는 반복 |
| WEIGH_COMPARATIVE | TWO_CONSIDERATIONS | 두 competing consideration을 같은 차원에서 비교하고 우선순위 설명 | 비용·크기·확률·범위·시점 비교 | 한쪽만 반복, 다른 차원 혼합, 우선순위 없음 |
| CRYSTALLIZE | CURRENT_CLASH | 기존 논증을 핵심 clash로 압축하고 새 substantive argument 금지 | 충돌 요약, 기존 이유 1~2개, 최종 weighing | 새 근거·사례·통계, 전체 나열, 중립 요약 |

Fidelity 결과는 `ALIGNED`, `PARTIALLY_ALIGNED`, `MISALIGNED`, `UNCLEAR`다. `ALIGNED`는 required semantic effect가 발언의 중심 기능이다. `PARTIALLY_ALIGNED`는 선택 Action을 실제로 수행하지만 일부가 다른 전략으로 이동한 경우다. `PARTIALLY_ALIGNED`는 primary Action 수행, target 실제 사용, 선택 Action이 핵심 기능 중 하나, 추가 move가 Protocol 위반이 아님을 모두 만족할 때만 확정하고 diagnostic flag를 남긴다. 하나라도 실패하거나 결과가 `MISALIGNED`·`UNCLEAR`이면 한 번 재생성하며 재실패 시 safe failure다.
