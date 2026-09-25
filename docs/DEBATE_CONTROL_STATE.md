# Debate Control State — 반복 토론 방지 설계

기존 `DebateState`는 무엇이 발화되었는지 기록하는 source of truth다. 반복 제어를 위해 이를 덮어쓰지 않고 그 위에 **Derived Control State**를 둔다.

```text
Raw DebateState
(Proposition / Relation / Question / Commitment)
        ↓
Semantic Facet / Question Group
        ↓
Progress Events
        ↓
Turn Task
        ↓
Eligible Action × Target
        ↓
Persona soft preference
        ↓
Generation
        ↓
Action + Stance + Task Fidelity
        ↓
State Patch
        ↓
Continue / Weigh / Phase change
```

## 1. Semantic Proposition annotation

`ADD_PROPOSITION`은 raw Proposition을 그대로 저장하면서 control-plane metadata를 함께 받는다.

- `NEW_REASON`: 기존에 없던 독립 이유
- `SAME_POINT`: 같은 논지의 말바꿈
- `REFINEMENT`: 같은 논지의 표현/정교화
- `NEW_COUNTEREXAMPLE`: 기존 주장에 대한 새 반례
- `QUALIFICATION`: 범위·조건·정도를 실제로 제한
- `RELATED_DISTINCT`: 관련 있지만 별개의 논지

`SAME_POINT / REFINEMENT / QUALIFICATION`은 `semantic_anchor_ref`가 필수다. 동일 speaker의 Proposition만 anchor할 수 있다. Raw C ID는 새로 생겨도 같은 semantic facet에 속하면 Action 반복 제한을 우회하지 못한다.

## 2. Question grouping

`ASK_QUESTION.semantic_kind`:

- `NEW_QUESTION`
- `SAME_QUESTION`
- `REFINEMENT`

표현만 바꾼 같은 질문은 `anchor_question_id`를 사용한다. `SAME_QUESTION`은 새로운 Q node를 만들지 않으므로 이미 해결된 질문을 새 Q ID로 다시 여는 것을 막는다.

## 3. Progress Event

새 Proposition ID 자체는 진전이 아니다.

진전으로 취급:

- `NEW_REASON`
- `NEW_COUNTEREXAMPLE`
- `QUALIFICATION`
- `RELATED_DISTINCT`
- 질문 해결
- 국소 양보
- 주장 수정

진전으로 취급하지 않음:

- `SAME_POINT`
- 단순 `REFINEMENT`
- 같은 질문 반복
- 해결된 질문을 새 근거 없이 다시 제기

Final Focus의 의도된 재진술은 Turn Task가 `CRYSTALLIZE`이므로 별도 허용한다.

## 4. Turn Task

Action을 고르기 전에 현재 턴의 conversational obligation을 고른다.

- `INTRODUCE_UNCOVERED_FACET`
- `ANSWER_OPEN_QUESTION`
- `ADDRESS_AUDIENCE`
- `ADDRESS_COUNTEREXAMPLE`
- `TEST_UNRESOLVED_REASON`
- `WEIGH_COMPETING_REASONS`
- `NARROW_DISAGREEMENT`
- `CRYSTALLIZE`
- `NO_VALUABLE_MOVE`

우선순위는 Audience 입력 → 열린 질문 → 새 반례 → unresolved reason → weighing/phase transition 순이다.

## 5. Adaptive phase

기존 schedule은 quota가 아니라 **최대 cap**이다. 최근 턴에서 semantic progress가 멈추면 probing을 계속하지 않고 `WEIGH_COMPETING_REASONS`로 전환한다. 해당 weighing까지 이미 소진되어 적법한 Action×Target이 없으면 추가 발언을 생성하지 않고 Crossfire/Rebuttal을 다음 단계로 넘긴다.

정확한 최적 턴 수는 미실측이며 고정하지 않는다.

## 6. Audience QUD

관객 입력은 임시 최우선 QUD로 취급한다. 원문을 A/B 생성 프롬프트에 직접 전달한다. 두 답변이 끝난 뒤 기존 Debate Agenda로 돌아간다.

## 7. 기존 Safety와의 관계

Control State는 기존 안전장치를 대체하지 않는다.

1. Turn Task
2. Action eligibility
3. Action–Target pair state
4. Target quality
5. Persona soft preference
6. 발언 생성
7. Action Fidelity + Stance Compliance + Turn Task Fidelity
8. typed State Patch

순서로 동작한다.

## 8. 회귀 자료

`etc/fixtures/tangsuyuk_repetition_14turn.json`은 실제 14-turn 탕수육 토론을 기준으로 `NEW_COUNTEREXAMPLE`, `REPHRASE_DOMINANT`, `AUDIENCE_NOT_GROUNDED`, `FINAL_CRYSTALLIZE_ALLOWED` 등을 구분해 보존한다.
