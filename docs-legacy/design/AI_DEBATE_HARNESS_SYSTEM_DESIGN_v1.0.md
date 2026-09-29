# AI Debate Harness 시스템 설계서

> 문서 상태: **Baseline Design v1.0**  
> 목적: MVP 구현에 사용할 제품 구조, AI 역할, 토론 엔진, Persona, Debate State, UX 및 검증 계획을 정의한다.  
> 원칙: 문헌조사로 판단 가능한 설계는 본 문서에서 확정하고, 실제 모델 동작에 따라 달라지는 항목만 Prototype Validation으로 남긴다.

---

# 1. 프로젝트 개요

## 1.1 목표

본 프로젝트는 사용자가 입력한 주제를 기반으로 두 AI 토론자가 **실제로 상대의 이전 발언을 받아가며 토론하는 과정**을 관전할 수 있는 웹 기반 AI Debate Harness다.

서비스 가치의 우선순위는 다음과 같다.

1. **AI끼리 토론하는 과정을 보는 재미 — 80%**
2. **한 주제에 대한 서로 다른 관점 탐색 — 15%**
3. **어느 쪽이 더 설득력 있었는지 사용자 스스로 판단 — 5%**

따라서 이 서비스는 다음과 다르다.

- 단순 찬반 요약기
- 한 번의 LLM 호출로 전체 대본을 만드는 서비스
- AI가 정답이나 승자를 대신 결정하는 서비스
- 사용자를 설득하거나 행동을 지시하는 상담 서비스

---

# 2. 핵심 제품 원칙

## 2.1 토론은 순차적으로 생성한다

다음과 같은 요청 하나로 전체 토론을 생성하지 않는다.

```text
"이 주제로 A와 B의 토론 대본을 작성해줘."
```

대신 각 발언은 이전 발언과 현재 Debate State를 입력으로 받아 생성한다.

```text
A 발언
↓
State Update
↓
B가 A의 실제 발언을 분석
↓
B 행동 선택
↓
B 발언
↓
State Update
↓
...
```

---

## 2.2 좋은 토론은 두 개의 좋은 연설이 아니다

핵심은 상대가 **방금 한 말 때문에 다음 발언이 달라지는 것**이다.

관전형 토론 사례에서도 반복적으로 나타나는 기본 단위는 다음과 같다.

```text
Argument
↓
Immediate Counter
↓
Callback / Escalation
↓
새로운 Debate State
```

따라서 시스템은 독립적인 장문 답변 두 개보다 **상호작용 밀도**를 우선한다.

---

# 3. 전체 사용자 흐름

```text
사용자 주제 입력
        ↓
Topic Analyzer
        ↓
Context가 필요한가?
   ┌────┴─────┐
  NO          YES
   │           ↓
   │      Context Intake
   │           ↓
   │      Debate Readiness
   │           ↓
   │      Context Summary
   └─────┬─────┘
         ↓
Motion Normalization
         ↓
Motion + Side 확인
수정 최대 1회
         ↓
Persona Pair 선정
         ↓
Opening
         ↓
Crossfire
         ↓
선택적 Audience Question
         ↓
Rebuttal
         ↓
Final Focus
         ↓
Neutral Debate Summary
         ↓
사용자 선택
A / 모르겠다 / B
         ↓
세션 종료
```

MVP 세션은 일회성이다.

---

# 4. Topic Analyzer

Topic Analyzer는 사용자가 입력한 문장을 즉시 찬성/반대로 나누지 않는다.

먼저 입력의 성격을 구조화한다.

---

## 4.1 Topic 분류는 하나의 enum을 사용하지 않는다

기존의:

```text
NATURAL_DEBATE
PLAYFUL_DEBATE
REFRAMED_DEBATE
FACT_DOMINANT
USER_CONTEXT
```

구조는 폐기한다.

`FACT_DOMINANT`는 사실 상태이고, `USER_CONTEXT`는 맥락 상태이며, `PLAYFUL`은 처리 방식이므로 동일한 종류의 개념이 아니다.

따라서 서로 독립적인 축으로 관리한다.

---

## 4.2 claim_type

```text
FACT
DEFINITION
CAUSE
VALUE
POLICY
COMPARISON
INTERPRETATION
PERSONAL_DISPUTE
INFORMATIONAL
OTHER
```

예:

```text
"핫도그는 샌드위치야?"
→ DEFINITION

"대학 출석 의무화 어때?"
→ POLICY

"철수와 영희 중 누가 잘못했어?"
→ PERSONAL_DISPUTE

"파이썬 리스트가 뭐야?"
→ INFORMATIONAL
```

질문·키워드 형태부터 바로 Motion으로 만들지 않고 먼저 claim type을 판정한다.

---

# 5. Epistemic Status

토론 가능성과 현실에서의 사실적 지위는 별도로 관리한다.

```text
NON_FACTUAL
OPEN_EMPIRICAL
GENUINELY_CONTESTED
WEIGHT_DOMINANT_TRUE
WEIGHT_DOMINANT_FALSE
FORMALLY_SETTLED
UNKNOWN
```

핵심 원칙:

> **Debateability ≠ Epistemic Status**

예:

```text
"지구는 평평하다."
```

는 놀이로 토론할 수 있다.

그러나:

```text
평평한 지구
vs
구형 지구
```

를 현실 세계에서 동일한 증거 수준의 주장처럼 다루지는 않는다.

양측에 동일한 발언 기회를 주는 것과 동일한 사실적 신뢰도를 부여하는 것은 다른 문제다.

---

# 6. Treatment Mode

```text
NATURAL_DEBATE
PLAYFUL_DEBATE
REFRAMED_DEBATE
```

---

## NATURAL_DEBATE

입력 자체가 정상적으로 토론 가능한 경우.

예:

```text
대학은 출석을 의무화해야 하는가?
탕수육은 부먹이 더 나은가?
핫도그는 샌드위치인가?
```

---

## PLAYFUL_DEBATE

사실적으로 불리하거나 황당한 입장도 **명시적인 놀이 규칙 안에서** 방어할 수 있다.

허용:

- 말장난
- 비유
- absurd argument
- alternative definition
- fictional premise
- stipulated counterfactual
- devil's advocate

금지:

- 가짜 연구
- 가짜 통계
- 존재하지 않는 전문가
- 가짜 인용
- 실제 과학적 합의를 왜곡하는 주장
- fictional premise를 현실 사실처럼 표현

---

## REFRAMED_DEBATE

사용자 입력 자체는 토론형이 아니지만 인접한 토론으로 변환하는 경우다.

예:

```text
"파이썬 리스트가 뭐야?"
```

를 자동으로:

```text
"초보자는 파이썬에서 리스트부터 배워야 한다."
```

로 바꾸면 새로운 행위자와 가치판단을 추가하므로 단순 Normalization이 아니라 Reframe이다.

이 경우 사용자 확인이 반드시 필요하다.

---

# 7. Interaction State

```text
READY
CONFIRMATION_REQUIRED
CONTEXT_REQUIRED
INFORMATIONAL_FIRST
```

---

## INFORMATIONAL_FIRST

다음과 같은 입력:

```text
"파이썬 리스트가 뭐야?"
```

는 기본적으로 토론 요청으로 해석하지 않는다.

사용자가 원한다면 가까운 토론 주제를 별도로 제안할 수 있다.

---

# 8. Topic 품질 기준

좋은 Topic의 핵심 조건은 네 가지다.

```text
clarity
clashability
scope fidelity
epistemic honesty
```

`사회적으로 중요한가` 또는 `진지한 주제인가`는 기준으로 사용하지 않는다.

본 서비스에서는 쓸데없는 주제도 정상적인 1급 콘텐츠다.

---

# 9. Context Intake

개인 사건에서는 바로 Motion을 만들지 않는다.

예:

```text
"철수랑 영희가 싸웠는데 누가 잘못했어?"
```

이 상태에서 AI가 스스로 사건을 채우면 안 된다.

먼저 Context를 수집한다.

---

## 9.1 질문 방식

질문은 한 번에 하나만 표시한다.

가능하면 객관식으로 제공한다.

```text
영희가 늦는다는 사실을 철수에게 미리 전달했나요?

○ 직접 전달한 것을 확인했다
○ 영희는 전달했다고 말했다
○ 철수는 연락을 받지 못했다고 말했다
○ 잘 모르겠다
○ 직접 입력하기
```

항상 가능한 경우:

```text
잘 모르겠다
직접 입력
```

을 제공한다.

---

# 10. 사용자 Context의 출처

외부 검증 기능이 없으므로 사용자 입력을 객관적 진실이라고 인증하지 않는다.

```text
USER_OBSERVATION
사용자가 직접 보고 들었다고 말함

REPORTED_CLAIM
다른 사람의 주장을 전달함

USER_ASSUMPTION
사용자의 해석 또는 추측

UNKNOWN
알 수 없음
```

---

# 11. Debate Readiness

Context Intake는 질문 개수를 미리 고정하지 않는다.

다음 질문을 기준으로 종료한다.

> 남아 있는 미확인 정보가 토론의 핵심 대립축을 결정적으로 바꿀 수 있는가?

---

## 11.1 Context Completeness

진행도를 사용자에게 보여준다.

```text
상황 파악 72%
```

단 LLM이 임의로 숫자를 생성하지 않는다.

활성화된 Context Slot의 가중치로 계산한다.

```text
completeness =
획득한 active slot weight
/
전체 active slot weight
```

---

# 12. Context Summary

Context Intake 종료 후 사용자에게 현재 이해한 상황을 보여준다.

```text
현재까지 파악한 상황

[직접 확인했다고 제공한 정보]
- ...

[전달된 주장]
- A는 ...라고 말했다.
- B는 ...라고 말했다.

[사용자의 해석]
- ...

[확인되지 않은 내용]
- ...
```

이후 Motion을 만든다.

MVP에서는 이전 Context 답변을 자유롭게 수정하지 않는다.

향후 확장 시 특정 시점의 State Snapshot으로 돌아가는 Rollback 방식을 사용한다.

---

# 13. Motion Normalization

사용자 입력을 토론 가능한 proposition으로 정리한다.

```text
"탕수육 부먹 찍먹"

→

"탕수육은 소스를 찍어 먹는 것보다
부어 먹는 편이 더 낫다."
```

사용자의:

```text
actor
subject
polarity
modality
scope
time
comparison baseline
evaluation criterion
```

을 가능한 한 유지한다.

사용자가 제공하지 않은 요소를 추가하면 `REFRAME`으로 분류한다.

---

# 14. Motion Confirmation

Motion은 **모든 토론에서 사용자에게 보여준다.**

```text
오늘의 논제

"탕수육은 소스를 찍어 먹는 것보다
부어 먹는 것이 더 낫다."

부먹  VS  찍먹

[수정] [토론 시작]
```

사용자는 Motion을 **최대 1회 수정**할 수 있다.

---

# 15. Side Label

가능하면 `찬성 / 반대` 대신 주제에 맞는 이름을 사용한다.

```text
부먹 / 찍먹
샌드위치 / 별도 범주
출석 의무화 / 출석 자율화
젖어 있음 / 젖어 있지 않음
```

규칙:

1. 두 Label의 문법적 수준을 맞춘다.
2. 평가적 표현을 넣지 않는다.
3. 한쪽에만 권위적 표현을 붙이지 않는다.
4. Motion의 핵심 대립에서 직접 파생한다.
5. 자연스러운 Label 생성에 실패하면 `PRO / CON`을 사용한다.

---

# 16. Fact-Dominant Topic

현실 사실이 압도적으로 한쪽에 있는 경우 `fact_anchor`를 Debate보다 위에 둔다.

예:

```text
FACT ANCHOR
표준 산술에서 1+1=2이다.

PLAY MODE
A: "1+1=3"을 비유·언어유희·가정체계로 방어
B: 이를 반박
```

Playful side는 현실 증거를 조작해서 이겨서는 안 된다.

---

## 16.1 외부 검색이 없는 MVP의 한계

MVP는 웹 검색을 사용하지 않는다.

따라서 다음과 같이 시간이 지나며 변할 수 있는 사실은 강한 Fact Anchor를 생성하지 않는다.

- 최신 정치 상황
- 최신 연구 결과
- 최근 통계
- 현재 법률·정책 상태
- 최신 사건

모델이 신뢰할 수 있는 안정적인 일반지식이라고 보기 어려우면:

```text
epistemic_status = UNKNOWN
```

으로 두거나 사용자 자료를 우선한다.

---

# 17. Persona System

Persona는 캐릭터 설명문이 아니다.

본 시스템에서는 다음과 같이 정의한다.

> **토론 중 상대적으로 안정적으로 유지되는 행동 선호 정책**

Persona와 Stance는 완전히 분리한다.

---

# 18. MVP Persona Library

Persona는 6개로 고정한다.

## 18.1 Auditor

핵심:

- 근거 요구
- 논리 연결 검증
- 불확실성 확인

선호:

```text
REQUEST_SUPPORT
CHALLENGE_INFERENCE
CHECK_CONSISTENCY
```

Style:

```text
directness = HIGH
verbosity = LOW
humor = LOW
```

---

## 18.2 Socratic

핵심:

- 정의 확인
- 숨은 전제 탐색
- 모호한 주장 구체화

선호:

```text
CLARIFY_CLAIM
CHALLENGE_PREMISE
SEEK_COMMITMENT
```

Style:

```text
directness = MEDIUM
verbosity = MEDIUM
humor = LOW
```

---

## 18.3 Falsifier

핵심:

- 반례
- Edge Case
- 일반화 붕괴 테스트

선호:

```text
TEST_BOUNDARY
CHECK_CONSISTENCY
REFUTE_CLAIM
```

Style:

```text
directness = HIGH
verbosity = LOW
humor = MEDIUM
```

---

## 18.4 Pragmatist

핵심:

- 실제 결과
- 비용
- Trade-off
- 구현 가능성

선호:

```text
WEIGH_COMPARATIVE
REFUTE_CLAIM
DEFEND_CLAIM
```

Style:

```text
directness = HIGH
verbosity = MEDIUM
humor = MEDIUM
```

---

## 18.5 Principlist

핵심:

- 원칙
- 권리
- 기준
- 논리적 일관성

선호:

```text
CHALLENGE_PREMISE
CHECK_CONSISTENCY
EXTEND_ARGUMENT
```

Style:

```text
directness = MEDIUM
verbosity = MEDIUM
formality = HIGH
```

---

## 18.6 Synthesist

핵심:

- 강한 논거 인정
- 주장 범위 수정
- 충돌 압축
- 비교

선호:

```text
CONCEDE_LOCAL
REVISE_CLAIM
WEIGH_COMPARATIVE
CRYSTALLIZE
```

Style:

```text
directness = MEDIUM
verbosity = MEDIUM
humor = LOW
```

---

# 19. Persona 내부 표현

MVP에서는 Big Five와 MBTI를 runtime 제어에 사용하지 않는다.

```text
Persona
├─ debate_traits
├─ behavior_anchors
└─ style
```

Trait 강도는:

```text
LOW
MEDIUM
HIGH
```

를 기본으로 사용한다.

임의의 `0.73`과 같은 정밀한 수치는 사용하지 않는다.

---

# 20. Behavior Anchors

각 Persona에는 구체적인 행동 규칙이 존재한다.

예: Auditor

```text
DO
- 중요한 경험적 주장에는 근거를 요구한다.
- 근거에서 결론으로 넘어가는 추론을 점검한다.
- 충분한 답을 받았다면 동일한 질문을 반복하지 않는다.
- 강한 반박은 인정한다.

AVOID
- 모든 문장에 citation을 요구하지 않는다.
- 이미 제공된 근거를 다시 요구하지 않는다.
- 상대가 불리하다는 이유로 사실을 만들어내지 않는다.
```

---

# 21. Persona Re-grounding

Persona Card는 첫 Turn에만 주지 않는다.

매 발언 생성 시 compact form으로 재주입한다.

```text
GLOBAL QUALITY CONTRACT
PERSONA CARD
CURRENT STANCE
CURRENT PHASE
RELEVANT DEBATE STATE
OPPONENT LAST TURN
TURN OBJECTIVE
```

Few-shot Persona Example은 MVP 기본 설정에서 사용하지 않는다.

필요성이 실측으로 확인될 경우 추가한다.

---

# 22. Persona Pairing

Topic 유형에 따라 기능적으로 다른 Persona를 조합한다.

기본 Pair:

```text
FACT / CAUSE
Auditor × Falsifier

DEFINITION
Socratic × Falsifier

POLICY / VALUE
Principlist × Pragmatist

PERSONAL_DISPUTE
Socratic × Synthesist

PLAYFUL
Falsifier × Pragmatist

COMPARISON
Pragmatist × Synthesist
```

Pair 선택 후 어느 Persona가 어느 입장을 맡을지는 별도로 배정한다.

특정 Persona가 항상 특정 종류의 입장을 맡지 않는다.

Persona 특성은 사용자에게 사전에 공개하지 않는다.

---

# 23. Debate Protocol

MVP 프로토콜:

```text
1. Opening A
2. Opening B

3. Crossfire

4. Optional Audience Question

5. Rebuttal A
6. Rebuttal B

7. Final Focus A
8. Final Focus B

9. Neutral Debate Summary

10. User Selection
```

---

# 24. Opening

Opening은 짧게 유지한다.

역할:

- Thesis 제시
- 핵심 Reason 1~2개 제시
- 첫 Clash 형성

장문의 에세이를 생성하지 않는다.

---

# 25. Debate Engine

핵심 아키텍처:

```text
Opponent Utterance
        ↓
Local State Extraction
        ↓
Candidate State Patch
        ↓
Reconciliation / Validation
        ↓
Debate State Update
        ↓
Protocol & Preconditions
        ↓
Eligible Action × Target
        ↓
Action Selection
        ↓
Speech Realization
        ↓
Grounding / Repetition Check
        ↓
State Patch
        ↓
Continue / Phase Change
```

---

# 26. Debate State 기본 구조

Debate State는 **얇은 Typed Proposition Graph + Dialogue State**를 사용한다. 완전한 Toulmin/AIF 구조를 runtime에 넣지 않는다.

Authoritative State:

```text
Propositions
Relations
Questions
Commitment Events
Provenance
```

Derived State:

```text
Current Commitments
Concession View
Revision View
Open Clashes
Argument Importance
Action Candidates
Entertainment Signals
```

---

# 27. Proposition

기본 Node는 하나다.

```text
PROPOSITION
```

`Claim`, `Premise`, `Evidence`를 서로 배타적인 영구 Node Type으로 만들지 않는다.

역할은 Relation에 의해 결정된다.

```text
C2 SUPPORTS C1
C3 SUPPORTS C2
```

C2는 첫 번째 관계에서는 근거이고 두 번째 관계에서는 결론이다.

---

# 28. Relation

MVP Authoritative Relation:

```text
SUPPORTS
ATTACKS
CONTRADICTS
QUALIFIES
```

중요:

```text
ATTACKS ≠ CONTRADICTS
```

예:

```text
"그 근거는 약하다."
→ ATTACKS

"X가 일어났다."
"X는 일어나지 않았다."
→ CONTRADICTS
```

---

# 29. Warrant 정책

Implicit Warrant를 자동으로 생성하지 않는다.

명시적으로 발화된 경우에만 Proposition 또는 Relation metadata로 저장한다.

---

# 30. Question State

Question은 First-class Entity로 저장한다.

```json
{
  "id": "Q5",
  "asker": "A",
  "target_id": "C12",
  "core_proposition": "...",
  "response_status": "PARTIAL",
  "resolution": "OPEN"
}
```

---

# 31. Response Status

```text
DIRECT
QUALIFIED
PARTIAL
EVADED
FRAME_REJECTED_VALID
UNCLEAR
```

질문에 대한 응답 상태와 질문 해결 여부를 분리한다.

---

# 32. Commitment Event

Commitment는 실제 Belief나 Truth가 아니다.

토론자가 공개적으로 책임지고 있는 입장을 의미한다.

```text
ASSERT
CONCEDE
WITHDRAW
REVISE
```

Event는 Append-only로 저장한다.

---

# 33. Revision

기존 Claim을 덮어쓰지 않는다.

```text
old claim
   ↓ REVISE
new claim
```

두 Claim과 Revision Event를 모두 보존한다.

---

# 34. State Update

LLM이 전체 State를 매 Turn 다시 작성하지 않는다.

```text
New Turn
↓
Local Extraction
↓
Candidate Patch
↓
Relevant Existing Node Retrieval
↓
Dedup / Revision / Contradiction Reconciliation
↓
Deterministic Validation
↓
Patch Apply
↓
Append Event Log
```

연구에서도 전체 State rewrite보다 patch 방식과 extraction/reconciliation의 분리가 권장된다.

---

# 35. Storage

MVP:

```text
JSON-shaped State
+
in-memory / request-carried indexes
+
Append-only Patch/Event Log
```

Graph DB를 사용하지 않는다.

---

# 36. Debate Action과 Response Obligation

`ANSWER` 자체를 Strategic Action으로 취급하지 않는다.

질문을 받으면 먼저 **Response Obligation**을 처리한다.

```text
DIRECT
QUALIFIED
FRAME_REPAIR
UNCERTAINTY
```

그 후 필요하면 Strategic Action을 수행한다.

예:

```text
response_mode = DIRECT
strategic_action = CONCEDE_LOCAL
```

---

# 37. Strategic Action Set v1

MVP는 15개 Strategic Action을 사용한다.

## Probe / Crossfire

```text
CLARIFY_CLAIM
REQUEST_SUPPORT
CHALLENGE_PREMISE
CHALLENGE_INFERENCE
TEST_BOUNDARY
CHECK_CONSISTENCY
SEEK_COMMITMENT
PRESS_UNANSWERED
```

## State Change

```text
CONCEDE_LOCAL
REVISE_CLAIM
```

## Argumentation / Late Phase

```text
REFUTE_CLAIM
DEFEND_CLAIM
EXTEND_ARGUMENT
WEIGH_COMPARATIVE
CRYSTALLIZE
```

---

# 38. Action Selection

MVP는 **Rule-Assisted Structured Selection**을 사용한다.

```text
Debate State
↓
불가능한 Action 제거
↓
Eligible Action × Target 생성
↓
LLM이 전략적으로 선택
↓
Persona를 반영해 표현
```

Rule Engine:

> 무엇이 불가능한지 결정

LLM:

> 가능한 행동 중 무엇이 지금 가장 적절한지 결정

Persona:

> 적절한 행동들 중 무엇을 선호하는지 영향

---

# 39. Persona × Action

예:

```text
clarification_seeking HIGH
→ CLARIFY_CLAIM 선호

evidence_demand HIGH
→ REQUEST_SUPPORT 선호

counterexample_seeking HIGH
→ TEST_BOUNDARY 선호

revision_on_evidence HIGH
→ REVISE_CLAIM 선호
```

Persona는 Precondition을 무시할 수 없다.

---

# 40. Press

`PRESS_UNANSWERED`는 다음 상황에서만 후보가 된다.

```text
이전에 명확한 질문이 있었고
AND
Response = PARTIAL 또는 EVADED
AND
핵심 내용이 아직 해결되지 않았고
AND
중요한 쟁점이고
AND
추가 Press가 새 정보를 만들 가능성이 있을 때
```

`DIRECT` 답변에는 동일 질문을 다시 Press하지 않는다.

정당한 `FRAME_REJECTED_VALID`도 회피로 간주하지 않는다.

---

# 41. Concession과 Revision

구분한다.

```text
CONCEDE_LOCAL
"그 점은 인정합니다."
```

```text
REVISE_CLAIM
"그 근거를 고려하면 제 주장의 범위를 수정하겠습니다."
```

양보는 패배와 동일하지 않다.

---

# 42. Weighing

`WEIGH_COMPARATIVE` 하나의 Action을 사용한다.

MVP Dimension:

```text
MAGNITUDE
PROBABILITY
SCOPE
TIMEFRAME
```

다른 비교 기준은 실제 필요성이 확인될 때 확장한다.

---

# 43. Compound Action

한 Turn은:

```text
1 Primary Action
+
0~1 Compatible Secondary Action
```

을 허용한다.

예:

```text
CONCEDE_LOCAL
+
WEIGH_COMPARATIVE
```

---

# 44. 반복 방지

단순 Action 빈도가 아니라:

```text
Action × Target
```

을 기준으로 관리한다.

```text
REQUEST_SUPPORT(C12)
REQUEST_SUPPORT(C12)
REQUEST_SUPPORT(C12)
```

는 반복.

```text
REQUEST_SUPPORT(C12)
CHALLENGE_INFERENCE(C15)
REQUEST_SUPPORT(C19)
```

는 정상적인 전략 변화일 수 있다.

---

# 45. Entertainment Signals

Derived State에 다음과 같은 기회를 표시할 수 있다.

```text
callback_opportunity
contradiction_opportunity
edge_case_opportunity
novel_consequence_opportunity
```

이는 새로운 Strategic Action은 아니다.

Action Selector가 재미있는 타이밍을 포착하는 보조 신호다.

---

# 46. Humor 원칙

관전형 콘텐츠 조사에서 재미는 별도 농담보다 **논증 자체가 웃긴 방향으로 진행될 때** 강하게 나타났다.

우선순위:

```text
Callback
>
Absurd Consequence
>
Analogy
>
Exaggeration
>
Standalone Joke
```

---

# 47. Sarcasm / Teasing 경계

허용 대상:

```text
Claim
Logic
Analogy
Definition
Example
Rhetorical Move
```

기본적으로 피할 대상:

```text
상대의 지능
인격
외모
정체성
실제 취약점
```

```text
"그 논리를 따르면 냉장고도 샌드위치가 되겠는데?"
```

는 가능하다.

```text
"그것도 이해 못 하냐?"
```

는 기본 Style에서 사용하지 않는다.

---

# 48. Gotcha

Gotcha는 실제 State에 기록된 모순만 사용한다.

```text
Claim A
+
Claim B
+
실질적 불일치
```

가 존재할 때:

```text
CHECK_CONSISTENCY
```

를 사용할 수 있다.

상대가 설명·Qualification·Concession으로 Repair하면 같은 Gotcha를 반복하지 않는다.

---

# 49. Topic Seriousness

Persona 자체는 유지한다.

주제에 따라 Surface Style만 조절한다.

## Playful

허용:

- Faux outrage
- 과장
- Absurd analogy
- 가벼운 teasing
- Sarcasm

## Serious / Personal

강화:

- 사실 명확성
- uncertainty 표현
- concession
- 존중하는 challenge

감소:

- humor
- sarcasm
- 과장

---

# 50. Moderator

Moderator는 세 번째 토론자나 Judge가 아니다.

**State / Tempo Controller**다.

주요 권한:

```text
반복 Micro-topic 종료
무의미한 Press 차단
Peak 이후 다음 Phase 전환
Seriousness mismatch 억제
Crossfire 종료 판단
```

관전형 사례에서도 Moderator의 핵심 가치는 승자 판정보다 tempo control에 있었다.

---

# 51. Crossfire 종료

두 구조를 같이 사용한다.

```text
Hard Budget
+
State-based Early Termination
```

추가 핵심 개념:

```text
NOVELTY EXHAUSTION
```

최근 Turn들에서 다음 변화가 거의 없으면 종료 방향으로 간다.

```text
새 Claim
새 Counterexample
새 Commitment
새 Contradiction
새 Callback
새 Consequence
새 Concession
새 Revision
```

---

# 52. Audience Question

Crossfire 이후:

```text
관객 질문이 있나요?

[질문하기]
[계속 보기]
```

사용자가 질문하면 **양측 모두 동일한 질문에 답한다.**

MVP에서는 한쪽 토론자만 지정하는 기능은 제공하지 않는다.

---

# 53. Rebuttal

Crossfire:

```text
탐색
검증
Commitment 획득
Clash 발견
```

Rebuttal:

```text
이미 드러난 Clash를 직접 해결
```

주요 Action:

```text
REFUTE_CLAIM
DEFEND_CLAIM
CHALLENGE_INFERENCE
CONCEDE_LOCAL
EXTEND_ARGUMENT
WEIGH_COMPARATIVE
```

---

# 54. Final Focus

새로운 핵심 Argument를 만들지 않는다.

기본 흐름:

```text
EXTEND_ARGUMENT
↓
WEIGH_COMPARATIVE
↓
CRYSTALLIZE
```

각 토론자는 최종적으로 가장 중요한 이유 1~2개를 남긴다.

---

# 55. Neutral Debate Summary

Final Focus 이후 별도의 Neutral Summarizer가 정리한다.

승자를 결정하지 않는다.

출력:

```text
핵심 Clash

A의 강한 논점

B의 강한 논점

양측이 합의한 부분

남아 있는 미해결 쟁점
```

Neutral Summary는 사용자 선택 **전에** 보여준다.

---

# 56. User Selection

```text
어느 쪽이 더 설득력 있었나요?

[A]
[아직 모르겠다]
[B]
```

AI가 최종 Winner를 선택하지 않는다.

---

# 57. Global Quality Contract

모든 Persona보다 우선한다.

```text
사용자가 제공하지 않은 사건 사실을 만들지 않는다.

존재하지 않는 근거나 통계를 만들지 않는다.

상대가 실제로 하지 않은 주장을 공격하지 않는다.

상대의 실제 질문에 답한다.

유효한 반론은 인정할 수 있다.

필요할 경우 불확실성을 표현한다.

패배한 Subclaim은 수정할 수 있다.

기존 Concession을 이유 없이 다시 부정하지 않는다.

Fact Anchor보다 Persona나 Assigned Stance가 우선할 수 없다.
```

---

# 58. Prompt Priority

```text
1. Global Truth / Quality Contract
2. Topic Epistemic Rules
3. Debate Protocol
4. Assigned Stance
5. Persona
6. Current Debate State
7. Phase Objective
8. Surface Style
```

---

# 59. Backend 구조

과제 요구에 따라:

```text
/api/
```

폴더 아래 Python Vercel Serverless Functions를 사용한다.

Frontend:

```javascript
fetch('/api/...')
```

로 Backend를 호출한다.

---

# 60. API 구성

초기 구조:

```text
/api/analyze-topic
/api/context-step
/api/create-motion
/api/debate-step
/api/neutral-summary
```

필요하다면 구현 시 일부 Endpoint를 합칠 수 있다.

---

# 61. debate-step 내부 흐름

```text
Request
↓
Current Debate State
↓
New Utterance Extraction
↓
Candidate Patch
↓
Reconciliation
↓
State Update
↓
Eligible Action Generation
↓
Action Selection
↓
Persona-conditioned Realization
↓
Output Validation
↓
State Patch
↓
Response
```

---

# 62. Frontend 구조

최소 세 영역을 제공한다.

## Home

- 서비스 설명
- 주제 입력

## Debate

- Context Intake
- Motion Confirmation
- Debate
- Audience Question
- Neutral Summary
- User Selection

## How It Works

- 시스템 구조
- Persona 설명
- Crossfire 원리
- 데이터/AI 제한사항

Responsive Mobile UI를 지원한다.

---

# 63. Failure UX

## Empty Input

```text
토론할 주제를 입력해주세요.
```

## Loading

현재 단계 표시:

```text
주제를 분석하고 있습니다...
상황을 파악하고 있습니다...
토론자가 생각하고 있습니다...
```

## API Error

```text
응답을 불러오지 못했습니다.
다시 시도해주세요.
```

## Invalid Structured Output

Raw JSON 오류를 사용자에게 노출하지 않는다.

## Long Input

입력 길이 제한과 안내 메시지를 제공한다.

---

# 64. API Key

API Key는 Frontend에 노출하지 않는다.

```text
Browser
↓
Vercel Python Function
↓
Environment Variable
↓
LLM API
```

---

# 65. 세션 정책

MVP:

```text
No Account
No DB
No History
No localStorage requirement
```

페이지 새로고침 또는 세션 종료 후 토론 복원을 보장하지 않는다.

---

# 66. MVP 포함

- Text topic input
- Topic Analyzer
- Context Intake
- Context Completeness
- Context Summary
- Motion Normalization
- Motion 수정 1회
- Topic-specific Side Label
- Fact Anchor / Play Mode
- 6 Persona Library
- Topic-based Persona Pairing
- Opening
- Crossfire
- Debate State
- Rule-assisted Action Selection
- Audience Question
- Rebuttal
- Final Focus
- Neutral Summary
- User Selection
- Responsive UI
- Loading / Failure UX
- Vercel Python Serverless Backend

---

# 67. MVP 제외

- 웹 검색
- PDF 업로드
- 이미지
- 음성
- 사용자 계정
- Database
- 과거 Debate 저장
- Context 답변 자유 수정
- 실시간 다중 사용자
- Persona 사용자 생성
- Persona 직접 선택
- 3명 이상 토론
- Fine-tuning
- Persona RAG
- Graph DB
- 실시간 외부 사실 검증
- AI Winner Judge

---

# 68. Prototype Validation Plan

이제 남은 항목은 추가 문헌조사가 아니라 실제 사용하는 LLM에서 측정한다.

## 68.1 Persona Qualification

검증:

```text
6 Persona가 실제로 구별되는가
Stance를 바꿔도 동일한 성향인가
20~30 Turn 후에도 유지되는가
Persona가 사실성과 논리를 악화시키지 않는가
```

---

## 68.2 Claim Identity

평가 Label:

```text
SAME
REVISION
QUALIFICATION
CONTRADICTION
RELATED_NEW
UNRELATED
```

특히 False Merge를 최소화한다.

---

## 68.3 Question Response Classification

```text
DIRECT
QUALIFIED
PARTIAL
EVADED
FRAME_REJECTED_VALID
```

을 실제 Debate 문장으로 검증한다.

---

## 68.4 Incremental State Drift

긴 Debate에서 State 오류가 누적되는지 측정한다.

```text
Turn 5
Turn 10
Turn 20
Turn 30
```

시점별 Human-corrected State와 비교한다.

---

## 68.5 Action Confusion

특히 다음 경계를 확인한다.

```text
CHALLENGE_PREMISE
vs
CHALLENGE_INFERENCE

REQUEST_SUPPORT
vs
CHALLENGE_INFERENCE

TEST_BOUNDARY
vs
REFUTE_CLAIM

CONCEDE_LOCAL
vs
REVISE_CLAIM
```

---

## 68.6 Crossfire Length

실제 사용자 관전 품질을 기준으로:

```text
Short
Medium
Adaptive
```

를 비교한다.

---

## 68.7 Turn Length

Crossfire 발언의 적절한 길이를 측정한다.

설계 원칙은 고정한다.

> 한 Turn은 상대의 핵심 한 점에 반응하고 하나의 새로운 Twist를 추가할 정도로 짧게 한다.

정확한 Token Cap만 실측으로 정한다.

---

## 68.8 Press / Callback 빈도

몇 회라는 문헌적 정답을 찾지 않는다.

다음을 측정한다.

```text
새 State 변화 없이 반복되는가
사용자가 피곤하다고 느끼는가
Callback이 실제 반박을 강화하는가
```

---

## 68.9 Tone Threshold

Playful / Serious 간 Style 강도를 실제 결과를 보고 조정한다.

---

## 68.10 Motion UX

측정:

```text
Motion 수정률
Motion 거부율
"내가 말한 주제가 아니다" 비율
```

을 통해 Reframe 정책을 조정한다.

---

# 69. 개발 순서

## Phase 1 — Core Data Structures

구현:

```text
Topic Analysis Schema
Persona Schema
Debate State Schema
Action Schema
```

---

## Phase 2 — State Parser

```text
Turn
→ Extraction
→ Patch
→ Reconciliation
→ State
```

구현.

---

## Phase 3 — Action Selector

15 Action + Preconditions + Target Selection 구현.

---

## Phase 4 — Persona Layer

6 Persona Card를 적용.

Stance Crossover Test 수행.

---

## Phase 5 — Debate Prototype

UI 없이:

```text
Opening
Crossfire
Rebuttal
Final Focus
```

전체 Flow 실행.

---

## Phase 6 — Validation

Persona / State / Action / Tempo 검증.

---

## Phase 7 — Context + Topic Pipeline

Topic Analyzer, Context Intake, Motion Confirmation 연결.

---

## Phase 8 — Web MVP

Vanilla HTML/CSS/JS와 Vercel Python API 연결.

---

# 70. 최종 아키텍처

```text
                    USER INPUT
                         │
                         ▼
                  TOPIC ANALYZER
          ┌──────────────┼───────────────┐
          │              │               │
      Claim Type    Epistemic Status   Context Need
          │              │               │
          └──────────────┼───────────────┘
                         ▼
                   MOTION / SIDES
                         │
                         ▼
                 PERSONA PAIRING
                         │
                         ▼
                    DEBATE ENGINE
                         │
       ┌─────────────────┼──────────────────┐
       │                 │                  │
    Protocol         Debate State        Persona
       │                 │                  │
       │                 │                  │
 무엇이 가능한가   무엇이 의미 있는가    무엇을 선호하는가
       │                 │                  │
       └─────────────────┼──────────────────┘
                         ▼
                ACTION + TARGET
                         │
                         ▼
               SURFACE REALIZATION
                         │
                         ▼
                  STATE UPDATE
                         │
                         ▼
                    MODERATOR
              Continue / Phase Change
                         │
                         ▼
                NEUTRAL SUMMARY
                         │
                         ▼
                   USER CHOICE
```

---

# 71. 시스템 정의

본 프로젝트에서 **Persona**는:

> 캐릭터 설정문이 아니라 안정적인 토론 행동 선호 정책이다.

**Debate State**는:

> 전체 대화를 다시 읽기 위한 기록이 아니라 다음 행동을 결정하기 위한 최소 구조화 상태다.

**Crossfire**는:

> 질문을 반복하는 구간이 아니라 현재 Argument State를 의미 있게 변화시키는 제한된 전략 게임이다.

**Entertainment**는:

> 농담을 별도로 붙이는 것이 아니라 상대의 직전 발언을 활용해 새로운 반박·모순·반례·Callback을 만드는 데서 발생한다.

그리고 전체 Harness의 핵심은 다음과 같다.

```text
Protocol
→ 무엇을 할 수 있는가

Debate State
→ 지금 무엇이 의미 있는가

Persona
→ 무엇을 선호하는가

Action Selector
→ 지금 실제로 무엇을 할 것인가

Surface Realizer
→ 그 행동을 어떻게 표현할 것인가

Moderator
→ 언제 멈추고 다음 단계로 넘어갈 것인가
```

이 구조를 MVP의 기준 아키텍처로 사용한다.