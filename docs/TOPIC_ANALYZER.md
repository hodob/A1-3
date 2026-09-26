# Topic Analyzer

Topic Analyzer는 사용자의 입력을 하나의 주제 유형으로만 분류하지 않는다. 이후 시스템이 내려야 하는 결정을 서로 다른 분석 정보로 분리하고, 각 정보가 다른 제어 책임을 맡도록 구성한다.

현재 구현에서 이 값들은 Python `Enum` 클래스가 아니라 `TopicAnalysis` Pydantic DTO의 `Literal` 타입으로 제한한다.

## 분석 정보와 책임

| 계약 필드 | 주된 책임 |
|---|---|
| `claim_type` | 무슨 종류의 논쟁인지 분류 |
| `epistemic_status` | 현실에서 사실적으로 어떤 상태인지 구분 |
| `treatment_mode` | 입력을 어떤 방식으로 토론할지 결정 |
| `interaction_state` | 사용자에게 다음에 무엇을 요구할지 결정 |
| `truth_mode` | 현실 사실과 가정·놀이의 경계 설정 |
| `tone_hint` | 발언의 표현 스타일 결정 |

각 필드는 서로 완전히 무관한 값이 아니라 연관될 수 있다. 다만 같은 책임을 중복해서 표현하기보다 서로 다른 downstream 결정을 담당하도록 나눈다.

## 함수 관점에서 본 Topic Analyzer

Topic Analyzer를 하나의 분류 함수로 보면 이 구조를 더 간단히 이해할 수 있다.

사용자 입력을 `x`라고 할 때, 하나의 label만 반환하는 일반적인 분류는 다음처럼 표현할 수 있다.

```text
f(x) = y
```

하지만 Topic Analyzer는 입력을 하나의 `topic_type`으로 압축하지 않는다. 서로 다른 책임을 가진 여러 분석 결과를 동시에 만든다.

```text
f(x) = (
  claim_type,
  epistemic_status,
  treatment_mode,
  interaction_state,
  truth_mode,
  tone_hint
)
```

위 표현은 `TopicAnalysis` DTO 전체 필드를 나타내기 위한 식이 아니라, 이 문서에서 다루는 여섯 분석 정보를 추상화한 표현이다.

집합의 관점에서는 다음처럼 볼 수 있다.

```text
f : X → C × E × T × I × R × S
```

- `X` — 사용자 입력의 집합
- `C` — Claim Type의 가능한 값 집합
- `E` — Epistemic Status의 가능한 값 집합
- `T` — Treatment Mode의 가능한 값 집합
- `I` — Interaction State의 가능한 값 집합
- `R` — Truth Mode의 가능한 값 집합
- `S` — Tone Hint의 가능한 값 집합

즉 하나의 입력을 하나의 거대한 복합 enum으로 분류하는 대신, 서로 다른 의미 공간의 값으로 나눠 반환하는 구조다.

예를 들어 입력이 다음과 같다고 하자.

> “철수와 영희 중 누가 더 잘못했어?”

개념적으로는 다음처럼 볼 수 있다.

```text
x = "철수와 영희 중 누가 더 잘못했어?"

f(x) = (
  PERSONAL_DISPUTE,
  UNKNOWN,
  NATURAL_DEBATE,
  CONTEXT_REQUIRED,
  REAL_WORLD,
  SERIOUS
)
```

이를 하나의 값으로 합치면 다음과 같은 형태가 필요해진다.

```text
PERSONAL_DISPUTE_UNKNOWN_NATURAL_CONTEXT_REQUIRED_REAL_WORLD_SERIOUS
```

이 방식은 논쟁 종류, 사실 상태, 진행 상태, 현실성 프레임, 표현 스타일처럼 성격이 다른 개념을 하나의 분류 체계에 섞는다. 한 책임의 값이 늘어날 때 조합 가능한 전체 상태 수도 함께 증가한다.

현재 구조는 이를 각각의 분리된 출력 차원으로 둔다.

```text
C(x) = PERSONAL_DISPUTE
E(x) = UNKNOWN
T(x) = NATURAL_DEBATE
I(x) = CONTEXT_REQUIRED
R(x) = REAL_WORLD
S(x) = SERIOUS
```

여기서 “분리”는 각 값이 통계적으로나 논리적으로 완전히 독립이라는 뜻이 아니다. 예를 들어 `PLAYFUL_DEBATE`와 `PLAYFUL`은 서로 관련될 수 있다. 핵심은 **각 필드가 같은 질문에 중복 답하는 것이 아니라, 서로 다른 시스템 결정에 필요한 정보를 표현한다는 점**이다.

---

## 1. `claim_type` — 무슨 종류의 논쟁인가

실제 허용 값:

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

| 값 | 의미 | 예시 |
|---|---|---|
| `FACT` | 사실 여부가 핵심인 주장 | “공룡은 인간과 같은 시대에 살았다.” |
| `DEFINITION` | 개념의 정의나 범위가 핵심인 주장 | “핫도그는 샌드위치인가?” |
| `CAUSE` | 무엇이 원인인지 따지는 주장 | “스마트폰 사용이 수면 부족의 원인인가?” |
| `VALUE` | 무엇이 더 좋거나 중요한지 판단 | “안정보다 도전이 더 중요한가?” |
| `POLICY` | 어떤 규칙이나 제도를 시행해야 하는지 판단 | “대학은 출석을 의무화해야 하는가?” |
| `COMPARISON` | 둘 이상의 대안을 비교 | “재택근무와 출근 중 어느 쪽이 더 효율적인가?” |
| `INTERPRETATION` | 같은 사건·작품·행동의 의미를 다르게 해석 | “이 영화의 결말은 희망적인가 비관적인가?” |
| `PERSONAL_DISPUTE` | 개인 사건에서 책임이나 해석이 충돌 | “철수와 영희 중 누가 더 잘못했는가?” |
| `INFORMATIONAL` | 토론보다 설명이나 정보 제공이 먼저 필요한 입력 | “파이썬 리스트가 뭐야?” |
| `OTHER` | 위 유형에 명확히 들어가지 않는 입력 | 여러 성격이 섞여 한 유형으로 분류하기 어려운 입력 |

`claim_type`은 어느 입장이 맞는지 판정하는 값이 아니다. 입력이 어떤 종류의 논쟁인지 분류하고, 현재 구현에서는 Persona pair 선택에 사용한다.

현재 Persona pair 매핑:

| `claim_type` | Persona pair |
|---|---|
| `FACT`, `CAUSE` | Auditor + Falsifier |
| `DEFINITION`, `INFORMATIONAL` | Socratic + Falsifier |
| `POLICY`, `VALUE` | Principlist + Pragmatist |
| `PERSONAL_DISPUTE` | Socratic + Synthesist |
| `COMPARISON` | Pragmatist + Synthesist |
| `INTERPRETATION` | Socratic + Principlist |
| `OTHER` | Falsifier + Pragmatist |

---

## 2. `epistemic_status` — 현실에서 사실적으로 어떤 상태인가

실제 허용 값:

```text
NON_FACTUAL
OPEN_EMPIRICAL
GENUINELY_CONTESTED
WEIGHT_DOMINANT_TRUE
WEIGHT_DOMINANT_FALSE
FORMALLY_SETTLED
UNKNOWN
```

| 값 | 의미 | 예시 |
|---|---|---|
| `NON_FACTUAL` | 객관적인 참·거짓 판정이 핵심이 아님 | “민트초코가 초코보다 맛있는가?” |
| `OPEN_EMPIRICAL` | 관찰·실험으로 검토할 수 있지만 아직 열려 있는 문제 | “주 4일제가 생산성을 높이는가?” |
| `GENUINELY_CONTESTED` | 관련 근거가 존재하지만 해석이나 결론이 실질적으로 갈리는 문제 | “재택근무가 사무실 근무보다 생산성에 더 유리한가?” |
| `WEIGHT_DOMINANT_TRUE` | 현실의 증거가 참 쪽에 크게 기울어 있음 | “지구는 대체로 구형이다.” |
| `WEIGHT_DOMINANT_FALSE` | 현실의 증거가 거짓 쪽에 크게 기울어 있음 | “지구는 평평하다.” |
| `FORMALLY_SETTLED` | 정의·수학·형식 체계 등에서 사실상 확정된 문제 | “표준 산술에서 1+1=2인가?” |
| `UNKNOWN` | 시스템이 신뢰 있게 사실 상태를 정하기 어려움 | 최신 연구·통계·법률 상태처럼 외부 확인이 필요한 입력 |

핵심 원칙은 **토론 가능성(Debateability)과 현실에서의 사실적 지위(Epistemic Status)를 분리하는 것**이다.

예를 들어 “지구는 평평하다”는 놀이형 토론의 소재가 될 수 있지만, 현실 세계에서 양쪽 주장이 같은 증거 수준을 가진 것처럼 취급하지 않는다.

---

## 3. `treatment_mode` — 이 입력을 어떤 방식으로 토론할 것인가

실제 허용 값:

```text
NATURAL_DEBATE
PLAYFUL_DEBATE
REFRAMED_DEBATE
```

| 값 | 의미 | 예시 |
|---|---|---|
| `NATURAL_DEBATE` | 입력 자체를 그대로 토론 가능 | “대학은 출석을 의무화해야 하는가?” |
| `PLAYFUL_DEBATE` | 놀이·말장난·가정 규칙을 명시하고 토론 | “1+1=3을 최대한 그럴듯하게 방어해봐.” |
| `REFRAMED_DEBATE` | 입력 자체는 토론형이 아니어서 가까운 토론 쟁점으로 재구성 | “파이썬 리스트가 뭐야?” → “초보자는 파이썬에서 리스트부터 배워야 하는가?” |

`REFRAMED_DEBATE`는 단순한 문장 정리가 아니다. 원래 입력에 없던 주장이나 판단 기준이 추가될 수 있으므로 사용자 확인이 필요할 수 있다.

---

## 4. `interaction_state` — 사용자에게 다음에 무엇을 요구할 것인가

실제 허용 값:

```text
READY
CONFIRMATION_REQUIRED
CONTEXT_REQUIRED
INFORMATIONAL_FIRST
```

| 값 | 의미 | 예시 |
|---|---|---|
| `READY` | 추가 입력 없이 다음 단계로 진행 | 바로 Motion 준비 |
| `CONFIRMATION_REQUIRED` | 재구성된 Motion이나 의미 변경을 사용자에게 확인 | “이 쟁점으로 토론할까?” |
| `CONTEXT_REQUIRED` | 판단에 필요한 사건 맥락을 추가 수집 | 개인 분쟁에서 직접 본 일·전해 들은 일 등을 질문 |
| `INFORMATIONAL_FIRST` | 토론보다 정보 설명이 먼저 필요 | “파이썬 리스트가 뭐야?” |

이 값은 Frontend의 다음 단계 분기에 직접 사용한다.

---

## 5. `truth_mode` — 지금 말하는 세계가 현실인가, 가정인가

실제 허용 값:

```text
REAL_WORLD
STIPULATED_COUNTERFACTUAL
RHETORICAL_PLAY
```

| 값 | 의미 | 예시 |
|---|---|---|
| `REAL_WORLD` | 실제 현실을 기준으로 토론 | “대학은 출석을 의무화해야 하는가?” |
| `STIPULATED_COUNTERFACTUAL` | 현실과 다르지만 모두가 명시적으로 받아들인 가정을 전제로 토론 | “만약 인간이 잠을 잘 필요가 없다면 야간 노동은 정당한가?” |
| `RHETORICAL_PLAY` | 말장난·과장·수사적 놀이 자체가 토론의 일부 | “1+1=3이라는 주장을 최대한 그럴듯하게 방어해봐.” |

`epistemic_status`와 역할이 다르다.

- `epistemic_status` — **현실에서 그 주장에 어느 정도의 사실적 근거가 있는가**
- `truth_mode` — **이번 토론이 현실 세계를 말하는가, 명시적 가정이나 놀이 세계를 말하는가**

`truth_mode`의 기본값은 `REAL_WORLD`다.

---

## 6. `tone_hint` — 어떤 표현 스타일로 말할 것인가

실제 허용 값:

```text
SERIOUS
PLAYFUL
None
```

| 값 | 의미 | 예시 |
|---|---|---|
| `SERIOUS` | 사실 명확성, 불확실성 표현, 존중하는 반박을 우선 | 개인 분쟁, 정책, 사실 민감 주제 |
| `PLAYFUL` | 가벼운 비유와 논증에서 나온 유머를 허용 | “부먹 vs 찍먹”, “핫도그는 샌드위치인가?” |
| `None` | 별도 tone hint가 없음 | `treatment_mode`를 기준으로 기본 tone 결정 |

`None`은 `SERIOUS`, `PLAYFUL`과 동등한 의미의 토론 유형이 아니다. `tone_hint`가 선택적 필드라 미지정 상태를 가질 수 있다는 뜻이다.

현재 구현의 fallback:

```text
tone_hint가 있으면 해당 값 사용
없고 treatment_mode == PLAYFUL_DEBATE이면 PLAYFUL
그 외에는 SERIOUS
```

---

## 서로 비슷해 보이는 값의 차이

### `epistemic_status` vs `truth_mode`

“현실에서 얼마나 사실인가”와 “어떤 세계를 전제로 말하는가”의 차이다.

예:

```text
주제: "1+1=3"

epistemic_status = FORMALLY_SETTLED 또는 사실 우세 상태
truth_mode = RHETORICAL_PLAY
```

현실의 산술 사실을 바꾸는 것이 아니라, 현실 사실은 유지하면서 놀이형 논증을 허용하는 구조다.

### `treatment_mode` vs `tone_hint`

“토론을 어떻게 처리할 것인가”와 “그 토론을 어떤 말투로 표현할 것인가”의 차이다.

예:

```text
treatment_mode = NATURAL_DEBATE
tone_hint = PLAYFUL
```

입력 자체는 정상적인 토론 주제지만 표현은 가볍게 만들 수 있다.

### `claim_type` vs `interaction_state`

“무슨 종류의 입력인가”와 “지금 사용자에게 무엇을 받아야 하는가”의 차이다.

예:

```text
claim_type = PERSONAL_DISPUTE
interaction_state = CONTEXT_REQUIRED
```

개인 분쟁이라는 주제 유형을 분류한 뒤, 현재 정보만으로는 바로 토론할 수 없으므로 추가 맥락을 요청한다.

---

## 예시: 하나의 입력이 여러 필드로 나뉘는 이유

사용자 입력:

> “철수와 영희 중 누가 더 잘못했어?”

가능한 분석 구조:

```text
claim_type        = PERSONAL_DISPUTE
epistemic_status  = UNKNOWN
treatment_mode    = NATURAL_DEBATE
interaction_state = CONTEXT_REQUIRED
truth_mode        = REAL_WORLD
tone_hint         = SERIOUS
```

하나의 `topic_type` 값으로는 다음 결정을 동시에 표현하기 어렵다.

- 개인 분쟁이라는 **논쟁 종류**
- 현재 사실관계를 확정하기 어렵다는 **사실 상태**
- 실제 사건으로 다룬다는 **현실성 프레임**
- 추가 맥락이 필요하다는 **사용자 진행 상태**
- 진지한 표현이 적합하다는 **표현 스타일**

Topic Analyzer는 이 책임을 분리해 이후 단계가 필요한 정보만 사용하도록 한다.
