# Repetition / Progress Control 변경 요약

이번 변경은 실제 탕수육 14-turn 토론에서 확인된 의미 반복을 대상으로 하며 실제 Provider 재실험은 수행하지 않았다.

## 변경된 핵심

1. `ADD_PROPOSITION`에 semantic control metadata 추가
   - NEW_REASON / SAME_POINT / REFINEMENT / NEW_COUNTEREXAMPLE / QUALIFICATION / RELATED_DISTINCT
2. `ASK_QUESTION`에 question semantic grouping 추가
   - NEW_QUESTION / SAME_QUESTION / REFINEMENT
3. `src/debate_engine/debate_control.py` 추가
   - semantic facets
   - question groups
   - common ground
   - progress events
   - Turn Task planner
4. 새 C ID가 같은 semantic facet이면 Action×Target repetition guard를 우회하지 못함
5. 같은 질문의 paraphrase가 resolved QUD를 새 OPEN Q로 다시 만들지 않음
6. Crossfire/Rebuttal schedule을 quota가 아닌 cap으로 사용
   - progress 정체 → WEIGH
   - 적법한 고가치 move 없음 → Provider 호출 전에 phase 이동
7. Audience Question 원문을 양측 generation prompt에 직접 전달
8. Final Focus에서 내부 Q ID와 오래된 열린 질문 obligation을 제거
9. 기존 combined semantic validation에 Turn Task Fidelity를 추가
10. phase/tone별 짧은 Surface Budget 추가
11. Topic `tone_hint`를 treatment mode와 분리 가능하게 함

## 기존 Safety 유지

- Action eligibility
- Action–Target pair state
- Target quality
- Persona soft preference
- Action Fidelity
- Stance Compliance
- typed State Patch
- bounded repair
- signed session

## 로컬 검증

- unittest 276개 통과
- `src + api` line coverage: 이번 검증에서 미실측
- `python -m etc.tools.preflight` PASS
- 추가 Provider calls: 0

## 아직 실제 API에서 확인할 것

Structured output contract에 semantic metadata와 `task_fidelity`가 추가되었으므로 배포 전/후 실제 Provider에서는 **한 번의 최소 smoke**로 다음만 확인하면 된다.

- Patch가 semantic_kind/anchor를 정상 반환하는가
- compliance tool이 task_fidelity/task_reason을 정상 반환하는가
- 실제 반복 구간에서 SAME_POINT가 facet으로 묶이는가
- audience 원문이 A/B 답변에 반영되는가
- no valuable move에서 추가 생성 없이 phase가 이동하는가

정확한 반복 감소율, 최적 턴 수, 사용자 재미 개선율은 미실측이다.
