# 사이 — AI Debate Harness

> 두 AI가 상대의 실제 발언에 반응하며 토론하고, 사용자는 그 공방을 지켜본 뒤 직접 판단하는 관전형 AI 토론 서비스다.

- **배포 URL**: https://a1-3-green.vercel.app
- **GitHub**: https://github.com/hodob/A1-3

**사이**는 사용자가 입력한 주제로 두 AI 토론자가 번갈아 발언하게 한다. 찬성 답변과 반대 답변을 따로 만들어 나란히 놓는 방식과 달리, 각 발언은 상대가 앞서 내놓은 주장·질문·반박·양보·수정을 다음 턴의 판단 재료로 삼는다. 사용자는 토론을 지휘하지 않고 지켜보다가 필요하면 한 번 질문하고, 승패는 마지막에 직접 판단한다.

두 토론자는 **A**와 **B**로 부르며, 논제에 대한 양쪽 입장을 하나씩 맡는다. 화면에 보이는 양측의 이름은 주제를 분석할 때 어느 쪽에도 치우치지 않게 짓는다.

이 설계의 핵심은 **이번 턴에 무엇을 할지는 Harness가 정하고, 모델은 그것을 문장으로 옮기기만 한다**는 점이다. 모델이 쓴 발언은 Harness의 검증을 통과해야만 토론 기록에 확정된다.

이 문서에서 자주 쓰는 용어는 다음과 같다.

- **Harness**: 사이의 서버 코드. 지금까지의 토론을 정리한 **Debate State**를 읽고 이번 턴에 할 일을 정한 뒤, 생성된 발언을 검증한다.
- **Debater Model**: A와 B의 발언 문장을 실제로 만드는 외부 AI 모델.
- **Control Model**: 주제 분석, 발언 검증, 토론 정리처럼 문장이 아닌 구조화된 결과를 만드는 외부 AI 모델.
- **Provider**: 위 모델들을 호출하는 외부 AI API.

> 동작 원리가 궁금하면 1~4장을, 직접 실행해 보려면 [5장](#5-실행과-배포)을 먼저 보면 된다. 한 턴이 실제로 어떻게 정해지는지는 [3.1의 예시](#31-예시-핫도그-토론의-6번째-턴)에서 볼 수 있다.

## 목차

1. [전체 사용자 흐름](#1-전체-사용자-흐름)
2. [전체 시스템 구조](#2-전체-시스템-구조)
3. [토론이 다음 발언을 만드는 방법](#3-토론이-다음-발언을-만드는-방법)
4. [토론 진행 규칙](#4-토론-진행-규칙)
5. [실행과 배포](#5-실행과-배포)
6. [구현 참고](#6-구현-참고)
7. [참고 문헌](#7-참고-문헌)

---

## 1. 전체 사용자 흐름

입력된 문장을 곧바로 찬반 프롬프트에 넣지 않는다. 토론할 수 있는 주제인지, 사용자만 아는 맥락이 필요한지, 사실 설명이 먼저 필요한 질문인지를 먼저 판단한 뒤 토론을 시작한다.

### 1.1 토론을 시작하기 전

입력을 분석하는 단계를 **Topic Analyzer**, 분석을 거쳐 확정한 토론 문장을 **Motion**(논제)이라고 부른다.

**그림 1. 토론 준비 흐름 — 주제를 토론 가능한 상태로 만드는 과정**

~~~mermaid
flowchart TD
    A[주제 입력] -->|분석| B{"어떻게 진행할까?<br/>Topic Analyzer"}
    B -->|바로 가능| M[Motion 확인]
    B -->|확인 필요| C[확인 이유 표시]
    C --> M

    B -->|개인 맥락 필요| D[맥락 질문 1개]
    D -->|사용자 답변| E{맥락이 충분한가?}
    E -->|아니오| D
    E -->|예| F[맥락 요약]
    F --> M

    B -->|사실 설명이 먼저 필요| I[주제 수정 안내]
    I --> A
    M -->|최대 1회 수정| Z[토론 시작]
~~~

| 분기 | 입력 예 | 진행 |
|---|---|---|
| 바로 가능 | "핫도그는 샌드위치인가?" | 바로 Motion을 보여 준다. |
| 확인 필요 | 토론형이 아닌 입력을 가까운 쟁점으로 바꾼 경우 | 원래 입력에 없던 판단 기준이 들어갈 수 있으므로, 왜 바꿨는지 보여 주고 확인받는다. |
| 개인 맥락 필요 | "철수와 영희 중 누가 더 잘못했어?" | 직접 본 일, 전해 들은 일 등 판단에 필요한 사실을 한 번에 하나씩 묻는다. |
| 사실 설명이 먼저 필요 | "파이썬 리스트가 뭐야?" | 토론보다 설명이 먼저인 입력이므로 주제를 바꾸도록 안내한다. |

Topic Analyzer는 주제를 "찬반 가능/불가능"으로만 나누지 않는다. 어떤 종류의 논쟁인지, 현실에서 사실관계가 어떤 상태인지, 어떤 방식으로 토론할지, 추가 맥락이 필요한지를 각각 따로 판단한다. 개인적인 사건이라면 사용자가 말하지 않은 사실을 AI가 지어내 채우지 않는다.

Motion은 토론을 시작하기 전에 사용자가 한 번 수정할 수 있다.

<details>
<summary><strong>Topic Analyzer가 반환하는 값 보기</strong></summary>

| 계약 필드 | 허용 값 |
|---|---|
| `claim_type` | `FACT`, `DEFINITION`, `CAUSE`, `VALUE`, `POLICY`, `COMPARISON`, `INTERPRETATION`, `PERSONAL_DISPUTE`, `INFORMATIONAL`, `OTHER` |
| `epistemic_status` | `NON_FACTUAL`, `OPEN_EMPIRICAL`, `GENUINELY_CONTESTED`, `WEIGHT_DOMINANT_TRUE`, `WEIGHT_DOMINANT_FALSE`, `FORMALLY_SETTLED`, `UNKNOWN` |
| `treatment_mode` | `NATURAL_DEBATE`, `PLAYFUL_DEBATE`, `REFRAMED_DEBATE` |
| `interaction_state` | `READY`, `CONFIRMATION_REQUIRED`, `CONTEXT_REQUIRED`, `INFORMATIONAL_FIRST` |
| `truth_mode` | `REAL_WORLD`, `STIPULATED_COUNTERFACTUAL`, `RHETORICAL_PLAY` |
| `tone_hint` | `SERIOUS`, `PLAYFUL`, `None` |

이 값들은 Pydantic DTO의 `Literal` 타입으로 제한한다. 필드별 판단 기준과 책임은 [docs/TOPIC_ANALYZER.md](docs/TOPIC_ANALYZER.md)에 정리했다.

</details>

### 1.2 토론이 시작된 뒤

단계 이름은 미국 고교 토론 대회 형식인 Public Forum에서 가져왔다. **Opening**은 입론, **Crossfire**는 서로 묻고 답하는 교차 질의, **Rebuttal**은 반박, **Final Focus**는 마무리 발언이다. 화면에는 각각 "첫 입장", "주고받기", "쟁점 되짚기", "마지막 한마디"로 표시된다. A와 B는 번갈아 발언하며, 토론 전체는 최대 12턴이다(사용자 질문에 대한 답변 2턴은 별도).

**그림 2. 토론 진행 흐름 — 탐색에서 최종 판단까지**

~~~mermaid
flowchart TD
    O[Opening] --> C[Crossfire]
    C --> Q{사용자 질문?}
    Q -->|질문| A[A와 B가 같은 질문에 답변]
    Q -->|건너뜀| R[Rebuttal]
    A --> R
    R --> F[Final Focus]
    F --> S[Neutral Summary]
    S --> U[사용자 선택]
~~~

사용자는 Opening과 Crossfire를 지켜보다가, 원하면 A와 B에게 같은 질문을 하나 던질 수 있다. 토론이 끝나면 AI가 승자를 판정하지 않는다. 사용자는 Neutral Summary를 읽고 A / 아직 모르겠다 / B 중 하나를 직접 고른다. 정리 화면과 마지막 화면에는 각 토론자의 Persona와 실제로 발언을 만든 모델 이름이 함께 표시된다. 토론 내용과 선택은 서버에 저장하지 않는다.

실제 토론 화면에서는 발언이 다음처럼 이어진다. "대학은 출석을 의무화해야 하는가?"를 배포 환경에서 돌린 기록 중 2·3번째 발언의 앞부분이다.

> **B · 의무화 반대** — 발언 2 · 첫 입장
>
> 출석 의무화는 학생의 자율성 제약이 실제 학습 성과로 이어지지 않는다는 점에서 정당성이 약합니다. …
>
> **A · 의무화 찬성** — 발언 3 · 주고받기
>
> ↖ B · 발언 2의 결론은 "자율성 제약이 성과로 이어지지 않는다"는 점을 사실상 의무화 전반의 정당성 약화로 바로 연결하고 있는데, 그 추론은 너무 강합니다. …

`↖ B · 발언 2`는 A가 겨냥한 앞 발언을 가리키는 참조 표시다. A는 새 주장을 늘어놓는 대신 B의 추론 한 곳을 골라 공격했다. 이 선택은 모델이 아니라 Harness가 내렸다. Harness가 정한 이번 턴의 과제는 "상대의 핵심 이유 하나를 검증하기"였고, 행동은 "근거에서 결론으로 가는 추론이 충분한지 문제 삼기"(`CHALLENGE_INFERENCE`)였다. 이런 결정이 어떻게 나오는지는 [3장](#3-토론이-다음-발언을-만드는-방법)에서 설명한다.

단계별 역할과 조기 전환 규칙은 [4. 토론 진행 규칙](#4-토론-진행-규칙)에서 설명한다.

---

## 2. 전체 시스템 구조

시스템은 **화면**, **제품 흐름과 세션**, **토론 제어**, **발언 생성**을 서로 분리한다.

**그림 3. 시스템 경계 — 사이와 외부 AI Provider**

~~~mermaid
flowchart TD
    U[사용자] --> B

    subgraph SAI[사이]
        B[Browser<br/>UI]
        API[Vercel Python API]
        H[Debate Harness<br/>State · 계획 · 검증]
        W[Web Service<br/>제품 흐름 · 세션 · Provider 호출]

        B -->|JSON / SSE| API
        API --> W
        H <--> W
    end

    subgraph EXT[외부 AI Provider]
        D[Debater Models<br/>A/B 발언 생성]
        C[Control Model<br/>분석 · 구조화 · 검증 · 요약]
    end

    W <-->|발언 생성| D
    W <-->|구조화된 판단| C
~~~

| 구성 요소 | 역할 |
|---|---|
| **Browser** | 주제 입력, 토론 관전, 사용자 질문, 최종 선택, 확정 전 초안 표시 |
| **Web Service** | 제품 흐름과 세션을 관리하고 Provider 호출을 조율 |
| **Debate Harness** (이하 Harness) | 현재 토론을 읽어 이번 턴의 과제·Action·Target을 정하고 결과를 검증 |
| **Debater Models** | Harness가 정한 조건에 맞는 실제 발언을 생성 |
| **Control Model** | 주제 분석, State Patch 추출, 의미 검증, Neutral Summary 같은 구조화 작업 |

가장 중요한 경계는 **무엇을 할지 결정하는 부분**과 **실제 문장을 만드는 모델**을 나눴다는 점이다.

---

## 3. 토론이 다음 발언을 만드는 방법

두 모델에게 번갈아 답변만 받는다면 각 모델이 이전 대화만 보고 다음 말을 알아서 정한다. 사이에서는 모델이 말하기 전에 Harness가 다음 네 단계를 거친다.

1. 확정된 토론 기록에서 아직 남아 있는 쟁점과 열린 질문을 계산한다.
2. 이번 턴에 해결할 과제(**Turn Task**)를 정한다.
3. 어떤 행동(**Action**)을 어떤 대상(**Target**)에 할지 고른다. Target은 State에 기록된 특정 주장(`C15`)이나 질문(`Q3`)이다. 행동과 대상의 짝을 이 문서에서는 `Action × Target`으로 표기한다.
4. 이번 턴에 필요한 Context만 골라 Debater Model에 넘긴다.

3.1은 실제 토론 한 턴의 예시, 3.2~3.4는 이 계획 과정, 3.5는 생성된 발언을 확정하는 과정이다.

### 3.1 예시: 핫도그 토론의 6번째 턴

"핫도그는 샌드위치인가?"라는 주제로 5턴까지 진행된 실제 기록([etc/fixtures/action_pair_hotdog_turn6.json](etc/fixtures/action_pair_hotdog_turn6.json))에 현재 계획 로직을 그대로 실행한 결과다. A는 "샌드위치에 들어간다", B는 "별도 범주다" 쪽이다.

5턴까지 쌓인 State의 일부다. `C`로 시작하는 항목은 주장, `Q`로 시작하는 항목은 질문이다.

~~~text
C1   A · 1턴  핫도그는 샌드위치에 들어간다.
C2   A · 1턴  샌드위치의 분류 기준은 빵이 속재료를 감싸거나 끼운 구조인가이다.   (C1을 지지)
C15  B · 4턴  핫도그를 샌드위치에서 빼는 결정적 조건은 번이 이어진 형식이다.
Q3   A → B · 5턴 · OPEN
     "번이 이어졌다는 형식 하나가 왜 샌드위치 바깥으로 내보내는 결정선이 되는지,
      그 점을 더 분명히 설명해 주시겠습니까?"
~~~

6번째 턴은 B의 Crossfire 차례다. Harness는 다음 순서로 판단한다.

| 단계 | 결과 |
|---|---|
| 현재 상황 계산 | B가 아직 답하지 않은 질문 `Q3`이 열려 있다. |
| Turn Task | `ANSWER_OPEN_QUESTION` — 다른 공격보다 `Q3`에 먼저 직접 답해야 한다. |
| 후보 | `DEFEND_CLAIM × C15`(자기 기준을 방어), `REVISE_CLAIM × C15`(기준을 수정) |
| 제외된 예 | `CHALLENGE_PREMISE × C1`: B가 4턴에 이미 사용해 **소진**됨. `REQUEST_SUPPORT × C1`: C1에는 이미 충분한 근거(C2 등)가 있어 **해결**됨. |
| 선택 | 이 주제는 정의 논쟁이라 B에게 Falsifier(반례 탐색형) Persona가 배정되어 있고, 그 결과 `DEFEND_CLAIM × C15`를 고른다. 같은 상황에서 Persona만 Synthesist(조정 통합형)로 바꾸면 `REVISE_CLAIM`을 고른다. |

Debater Model은 `Q3`, `C15`와 관련 주장을 Context로 받아, "왜 번이 이어진 형식이 결정선인지"를 방어하는 발언을 쓴다. Persona와 소진·해결의 기준은 [3.3](#33-action-선택과-persona)에서 설명한다.

### 3.2 State에서 다음 턴 계획까지

**그림 4. 다음 발언 계획 — 확정된 토론 기록을 생성 조건으로 바꾸는 과정**

~~~mermaid
flowchart TD
    S[Debate State<br/>확정된 주장 · 질문<br/>관계 · 입장 변화]
    V[Control View<br/>현재 논점 · 열린 질문<br/>진전 상태]
    T[Turn Task<br/>이번 턴에 해결할 일]
    A[Action × Target<br/>어떤 행동을 어떤 대상에 할지]
    C[Relevant Context<br/>이번 턴에 필요한 State 정보]
    M[Debater Model]

    S --> V
    V --> T
    T --> A
    A --> C
    C --> M
~~~

Debate State에는 다음 턴에도 유지해야 할 사실만 저장한다. 어떤 주장이 나왔는지, 어떤 질문이 열려 있는지, 누가 무엇을 양보·철회·수정했는지가 여기에 해당한다.

반면 "두 주장이 사실상 같은 논점인가?", "최근 턴에서 토론이 실제로 진전됐는가?", "지금 가장 먼저 답해야 할 질문은 무엇인가?"처럼 저장된 State로 계산할 수 있는 정보는 저장하지 않고 매 턴 다시 계산한다. 이 계산 결과를 **Control View**라고 부른다. Harness는 Control View로 `Turn Task`를 만들고, 그 과제를 수행할 수 있는 `Action × Target` 후보 중 하나를 고른다.

<details>
<summary><strong>Turn Task 종류 보기</strong></summary>

| Turn Task | 이번 턴의 과제 | 주로 쓰이는 때 |
|---|---|---|
| `INTRODUCE_UNCOVERED_FACET` | 입장을 지지하는 핵심 이유 1~2개를 처음 제시한다. | Opening |
| `ANSWER_OPEN_QUESTION` | 자기에게 온 열린 질문에 먼저 직접 답한다. | 답하지 않은 질문이 있을 때 |
| `TEST_UNRESOLVED_REASON` | 아직 해결되지 않은 상대의 핵심 이유 하나를 검증하거나 범위를 좁힌다. | Crossfire |
| `ADDRESS_COUNTEREXAMPLE` | 상대가 새로 제시한 반례를 받아들이거나, 한정하거나, 반박한다. | 반례가 나왔을 때 |
| `ADDRESS_AUDIENCE` | 사용자 질문에 직접 답한다. | 사용자 질문 단계 |
| `WEIGH_COMPETING_REASONS` | 양측 핵심 이유를 같은 기준에서 비교해 남은 충돌을 좁힌다. | Rebuttal |
| `CRYSTALLIZE` | 이미 다룬 핵심 쟁점과 이유만 압축한다. | Final Focus |
| `NO_VALUABLE_MOVE` | 더 다룰 가치가 있는 과제가 없다. 발언을 만들지 않고 다음 단계로 넘어간다. | Crossfire·Rebuttal 조기 전환 |

</details>

<details>
<summary><strong>Debate State와 파생 계산의 세부 구조 보기</strong></summary>

State의 주요 구조는 다음과 같다.

| 구조 | 기록하는 것 |
|---|---|
| **Proposition** | 실제로 제시된 주장 |
| **Relation** | 주장 사이의 지지·공격·모순·한정 관계 |
| **Question** | 제기된 질문과 `OPEN / RESOLVED` 상태. 한 발언에 여러 질문이 섞여 있어도 문장 단위로 나눠 빠뜨리지 않게 확인한다(D'Agostino et al., 2024) |
| **Commitment Event** | 주장·양보·철회·수정 같은 입장 변화. 대화 게임 이론의 commitment 개념을 따랐다(Prakken, 2005) |

주장을 수정해도 기존 Proposition을 덮어쓰지 않고, 새 Proposition과 수정 관계를 함께 남긴다.

~~~text
C12  기존 주장: "모든 경우에 X다"
C19  수정 주장: "조건 Y에서는 X다"
REVISE  C12 → C19
~~~

Control View는 `build_control_view(state)`가 만든다. 이 함수는 State를 읽어 `Semantic Facets`(같은 논점으로 묶인 주장), `Question Groups`, `Progress`를 계산한다. `Immediate QUD`(QUD는 Question Under Discussion의 약자)는 이 결과와 현재 발언자를 기준으로 지금 가장 먼저 다룰 열린 질문을 고른 것이다.

계산할 수 있는 값을 따로 저장하지 않으면 원본과 사본이 어긋날 일이 없다. React와 Redux가 중복·파생 state를 줄이라고 권장하는 것, PostgreSQL의 View가 데이터를 복제하지 않고 조회할 때 계산하는 것과 같은 원리다.

</details>

### 3.3 Action 선택과 Persona

Harness는 현재 Turn Task에서 가능한 `Action × Target` 후보를 만든 뒤, 이미 해결됐거나 반복으로 소진됐거나 대상 조건에 맞지 않는 후보를 먼저 제외한다. 남은 후보 중에서 현재 쟁점과의 관련성, 전략적 우선순위, Persona 선호, 반복 정도를 비교해 하나를 고른다.

- **소진**: 같은 발언자가 같은 `Action × Target`을 이미 한 번 사용한 상태. 같은 공격을 되풀이하지 않도록 기본적으로 다시 고르지 않는다. 단, 근거가 아직 약한 주장에 대한 근거 요구나, 상대가 부분적으로만 답했거나 피한 질문을 다시 묻는 것은 계속 열어 둔다.
- **해결**: 그 행동의 목적이 이미 이뤄진 상태. 예를 들어 근거가 충분히 제시된 주장에 대한 근거 요구나, 이미 직접 답이 나온 질문에 대한 재질문은 해결된 것으로 보고 고르지 않는다.

**Persona**는 토론자의 논증 성향이다. 논제를 확정할 때 주제 유형에 따라 A와 B에게 서로 다른 Persona가 하나씩 배정된다(예: 정의 논쟁은 Socratic과 Falsifier, 정책·가치 논쟁은 Principlist와 Pragmatist). Persona는 **어떤 행동을 허용할지 정하는 규칙이 아니라, 허용된 행동 중에서 무엇을 더 선호할지 정하는 성향**이다. 그래서 Persona가 특정 행동을 선호하더라도, 이미 해결된 질문이나 소진된 Action × Target을 다시 고르게 만들 수는 없다. 말투나 캐릭터를 연기시키는 대신 논증 행동의 선호로 Persona를 다룬 것은 LLM Persona 연구(Tseng et al., 2024; Jiang et al., 2024; Nagao et al., 2026)를 참고했다.

| Persona | 화면 표시 | 선호하는 방향 |
|---|---|---|
| Auditor | **근거 검증형** | 근거 요구, 추론 연결 검증, 일관성 확인 |
| Socratic | **전제 탐구형** | 정의·범위 확인, 숨은 전제 탐색, 명시적 입장 요구 |
| Falsifier | **반례 탐색형** | 반례·경계 사례 제시, 일관성 검사, 직접 반박 |
| Pragmatist | **현실 실용형** | 결과·비용·득실 비교, 반박과 방어 |
| Principlist | **원칙 중심형** | 기준·전제·일관성 점검, 원칙에 근거한 이유 확장 |
| Synthesist | **조정 통합형** | 부분적 양보, 주장 수정, 비교와 핵심 정리 |

<details>
<summary><strong>15개 Strategic Action 전체 보기</strong></summary>

| Action | 역할 |
|---|---|
| `CLARIFY_CLAIM` | 주장의 의미·범위·용어를 분명히 하도록 요구 |
| `REQUEST_SUPPORT` | 주장에 대한 근거·이유·정당화를 요구 |
| `CHALLENGE_PREMISE` | 전제의 사실성·필요성·적용 가능성을 문제 삼음 |
| `CHALLENGE_INFERENCE` | 근거에서 결론으로 가는 추론이 충분한지 문제 삼음 |
| `TEST_BOUNDARY` | 반례·경계 사례로 주장의 적용 범위를 시험 |
| `CHECK_CONSISTENCY` | 앞서 한 입장과 현재 주장 사이의 긴장을 확인 |
| `SEEK_COMMITMENT` | 상대가 특정 기준·명제에 대해 입장을 분명히 하도록 요구 |
| `PRESS_UNANSWERED` | 부분적으로만 답했거나 피한 핵심 질문을 좁혀 다시 요구 |
| `CONCEDE_LOCAL` | 상대의 특정 논점은 인정하되 전체 입장은 유지 |
| `REVISE_CLAIM` | 자신의 기존 주장을 실제로 수정하거나 범위를 좁힘 |
| `REFUTE_CLAIM` | 상대 주장을 이유와 함께 직접 반박 |
| `DEFEND_CLAIM` | 공격받은 자신의 주장을 근거·구분·한정으로 방어 |
| `EXTEND_ARGUMENT` | 현재 입장을 지지하는 새로운 관련 이유를 추가 |
| `WEIGH_COMPARATIVE` | 경쟁하는 두 고려사항을 같은 기준으로 비교 |
| `CRYSTALLIZE` | 새 근거 없이 이미 나온 핵심 충돌을 압축 |

후보의 순위는 점수를 더하는 방식이 아니다. 먼저 `Target Quality`를 비교하고, 같으면 `Strategic Priority → Persona Preference → Saturation`(반복 정도) 순서로 차례로 비교한다.

</details>

### 3.4 모델에는 이번 턴에 필요한 Context만 보낸다

State를 구조화했다고 해서 매 턴 전체 State를 Debater Model에 넣지는 않는다. 이번 턴에 꼭 필요한 정보(이 문서에서는 **Relevant Context**라고 부른다)만 골라 넘긴다. 고르는 기준은 다음과 같다.

- 현재 `Turn Task`와 `Action × Target`이 가리키는 항목
- **QUD**(Question Under Discussion, 지금 가장 먼저 다룰 열린 질문. Roberts, 2012)가 겨냥하는 주장
- 그 주장과 같은 논점으로 묶인 주장(**Semantic Facet**)의 대표형과 최신형
- 최근 발언에서 실제로 참조된 State 항목

~~~text
전체 Debate State
    ↓ 현재 상황 계산
Turn Task / Action × Target / QUD
    ↓ 관련 항목 선택
이번 턴의 Relevant Context
    ↓
Debater Model
~~~

구현에서는 `working_reference_ids()`가 이 기준으로 State 항목을 모아 중복을 없앤 뒤 최대 12개를 발언 생성 요청에 넣는다. State Patch를 추출할 때는 주장 사이의 관계를 따라가며 필요한 항목을 따로 고른다.

State가 구조화되어 있기 때문에 지금 중요한 항목을 계산해 골라낼 수 있다. 긴 입력의 중간에 놓인 정보는 모델이 놓치기 쉬우므로(Liu et al., 2024), 입력을 짧고 초점 있게 유지하는 것 자체가 발언 품질에 도움이 된다.

### 3.5 생성된 발언은 바로 확정되지 않는다

**그림 5. 한 턴의 확정 과정 — 초안에서 확정 발언까지**

~~~mermaid
flowchart TD
    P[Turn Plan<br/>Task · Action · Target<br/>Context]
    G[Debater Model<br/>발언 생성]
    D[Streaming Draft<br/>확정 전 초안]
    V{규칙 준수 검사}
    R[Repair 또는 Replan]
    S[State Patch<br/>추출 · 검증 · 적용]
    C[Commit<br/>발언 + 새 Debate State 확정]

    P --> G
    G --> D
    D --> V
    V -->|실패| R
    R --> P
    V -->|3번 모두 실패| X[확정하지 않음<br/>기존 기록 유지]
    V -->|통과| S
    S -->|성공| C
    S -->|2번 모두 실패| X
~~~

화면에 스트리밍되는 초안은 아직 확정된 발언이 아니다. Harness는 먼저 초안이 규칙을 지켰는지 검사한다(코드에서는 Compliance 검사라고 부른다). 검사 항목은 다음과 같다.

- 배정된 입장(Assigned Stance)을 유지했는가
- 이번 턴의 과제(Turn Task)를 수행했는가
- 고른 행동을 고른 대상에 실제로 했는가(Action × Target)
- 출력 형식과 State 참조 규칙을 지켰는가 (예: Final Focus는 최대 2문장)

형식 검사는 모델 호출 없이 코드로 먼저 하고, 통과하면 Control Model이 나머지 의미를 판단한다.

검사에 실패하면 두 가지 방법으로 다시 시도한다. 발언 생성은 둘을 합쳐 한 턴에 최대 3번까지 한다.

- **Targeted Repair(부분 수정)**: 계획은 그대로 두고, 무엇이 왜 틀렸는지 구조화된 피드백과 함께 모델에게 그 부분만 고쳐 쓰게 한다(Ray & Goyal, 2026).
- **Replan(재계획)**: 수정으로도 안 되면 Harness가 같은 Turn Task 안에서 다른 Action × Target을 골라 새로 쓰게 한다.

검사를 통과하면 발언에서 State 변화만 타입이 정해진 Patch로 추출한다. 추출된 Patch가 형식 검사를 통과하지 못하면 한 번 더 추출한다(최대 2번). Patch까지 정상적으로 적용되어야 발언과 새 State가 함께 확정된다.

끝까지 실패하면 그 턴은 확정되지 않고, 기존 발언 기록과 Debate State도 바뀌지 않는다. 화면에는 "다음 발언을 이어가지 못했어요"라는 안내와 **이 발언 다시 준비하기** 버튼이 나타나며, 사용자는 여기까지의 토론을 잃지 않고 같은 턴을 다시 시도할 수 있다.

> **실제 실행에서 본 예** — 배포 환경에서 "대학은 출석을 의무화해야 하는가?"로 14턴을 돌렸을 때, 2개 턴이 첫 초안에서 거부되고 `Targeted Repair` 한 번으로 통과했다.
>
> - 10번째 턴(B, 의무화 반대): 사용자 질문에 답하면서 "출석 의무화를 유지하되…"라고 써서 자기 입장을 뒤집었다. `STANCE_REVERSAL`로 거부됐고, 재작성본은 반대 입장을 유지했다. 거부된 초안도 스트리밍 중에는 화면에 잠시 보였는데, 초안을 확정 전으로 표시하는 이유가 바로 이것이다.
> - 14번째 턴(B, Final Focus): 세 문장을 써서 `FINAL_FOCUS_LENGTH`(최대 2문장)로 거부됐다.
>
> 5번째 턴에서는 첫 State Patch가 형식 검사에 걸려 한 번 더 추출했다.

<details>
<summary><strong>State Patch와 검증 세부 항목 보기</strong></summary>

State Patch로 표현할 수 있는 변화:

~~~text
ADD_PROPOSITION
ADD_RELATION
ASK_QUESTION
ANSWER_QUESTION
REVISE_PROPOSITION
CONCEDE_LOCAL
WITHDRAW_PROPOSITION
~~~

Compliance 검사는 통과/실패만 판정하지 않고 실패 원인을 구분한다. 입장 뒤집기, Action 미수행, Target 미사용, 과제 이탈, 단순 반복, 잘못된 State 참조, Final Focus 형식 위반 등이 각각 다른 원인으로 기록된다.

Browser가 받는 `draft_reset / draft_delta` 이벤트는 확정 전 초안이다. Patch 적용까지 성공하면 서버가 SSE `commit` 이벤트로 최종 결과를 보낸다.

</details>

---

## 4. 토론 진행 규칙

토론 단계는 Public Forum Debate의 Constructive–Crossfire–Rebuttal–Final Focus 구성(ACTAA)을 참고해, 관전형 서비스에 맞게 단순화했다.

| 단계 | 화면 표시 | 턴 수 | 역할 |
|---|---|---|---|
| **Opening** | 첫 입장 | 2 (A → B) | 각 토론자가 입장과 핵심 이유를 밝히고 첫 충돌 지점을 만든다. |
| **Crossfire** | 주고받기 | 최대 6 | 질문·반례·검증으로 상대 주장을 시험하며 실제 쟁점을 좁힌다. |
| **사용자 질문** | 함께 답하기 | 0 또는 2 | 사용자가 원하면 A와 B에게 같은 질문을 던지고, 둘 다 답한다. 건너뛸 수 있다. |
| **Rebuttal** | 쟁점 되짚기 | 최대 2 | Crossfire에서 드러난 핵심 충돌을 직접 반박·방어하고, 필요하면 부분적으로 양보하거나 주장을 수정한다. |
| **Final Focus** | 마지막 한마디 | 2 | 새 논점을 더하지 않고, 끝까지 남길 이유를 최대 2문장으로 압축한다. |
| **Neutral Summary** | 토론 정리 | — | 승자를 정하지 않고 핵심 충돌, 양측의 강한 논점, 합의한 부분, 남은 쟁점을 정리한다. |
| **사용자 선택** | 내 생각 고르기 | — | 사용자가 Summary를 읽고 A / 아직 모르겠다 / B 중 하나를 직접 고른다. |

### 4.1 Crossfire와 Rebuttal의 턴 수는 목표가 아니라 상한이다

정해진 턴 수를 반드시 채우지 않는다. 현재 State에서 더 다룰 가치가 있는 과제가 없으면, Provider를 더 호출하지 않고 다음 단계로 넘어간다. Crossfire가 일찍 끝나면 곧바로 사용자 질문 단계로, Rebuttal이 일찍 끝나면 Final Focus로 넘어간다.

Crossfire에서는 새 주장을 계속 늘리기보다, 이미 나온 상대의 핵심 이유를 질문·반례·추론 공격·입장 확인 요구·부분 양보·수정으로 실제로 처리하는 것을 우선한다.

### 4.2 사회자는 판단하지 않고 서버의 결정을 전달한다

토론을 계속할지, 사용자 질문 단계를 열지, 다음 단계로 넘어갈지는 서버가 결정한다. 화면의 사회자 카드는 서버가 보낸 `moderator_decision`, `turn_task`, 단계 전환 정보를 사용자에게 보여줄 뿐이다.

`public/debate_moderator.js`는 LLM을 호출하지 않으며, 토론 전략을 독자적으로 판단하지도 않는다.

---

## 5. 실행과 배포

### 5.1 기술 스택

| 영역 | 기술 |
|---|---|
| Frontend | HTML, CSS, Vanilla JavaScript |
| Backend | Python 3.12, Vercel Serverless Functions |
| Schema / Validation | Pydantic |
| Streaming | Server-Sent Events (SSE) |
| AI Integration | OpenAI 호환 Chat Completions / Tool Calling |
| Debater Routing | 여러 회사 모델로 구성한 Debater Model 풀 |
| Session | zlib 압축 + HMAC-SHA256 서명, 클라이언트 보관 |
| Deployment | GitHub + Vercel |

### 5.2 로컬 실행

Python 3.12가 필요하다. JavaScript 테스트까지 돌리려면 Node.js도 필요하다.

~~~bash
python -m venv .venv
source .venv/bin/activate      # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
~~~

외부 AI를 호출하지 않고 전체 화면 흐름을 확인하려면 Mock 개발 서버를 실행한다.

~~~bash
python -m etc.tools.web_dev_server
~~~

http://127.0.0.1:8765 에 접속한다(`--port`로 변경 가능). 이 서버는 `config.json`의 `web_mode`와 관계없이 항상 Mock 서비스를 사용하므로 API 키가 필요 없고 토큰도 소모하지 않는다. Mock 서비스는 미리 정해 둔 문장으로 응답하므로 화면 흐름을 확인하는 용도다. 로컬 개발 서버는 Live 모드를 지원하지 않으므로, 실제 모델로 토론하려면 [5.7](#57-vercel-배포)처럼 Vercel에 배포한다.

### 5.3 테스트

~~~bash
python -m unittest discover -s tests -q
node --test tests/js/test_debate_stream.cjs tests/js/test_markdown_renderer.cjs tests/js/test_debate_moderator.cjs
~~~

배포 전에는 preflight로 필요한 검사를 한 번에 실행한다. 전체 unittest, Python 컴파일, JavaScript 문법, Vercel 설정, 비밀값과 일반 설정의 분리, 프론트엔드 비밀값 노출 여부를 확인하며, Provider는 호출하지 않는다.

~~~bash
python -m etc.tools.preflight
~~~

GitHub Actions도 push와 pull request마다 Python 3.12에서 unittest와 JavaScript 검사를 실행한다.

### 5.4 설정

일반 설정과 비밀값을 분리한다.

**`config.json`** — 비밀이 아닌 실행 설정. Git에 커밋한다.

~~~json
{
  "web_mode": "live",
  "provider": {
    "url": "https://copa.codyssey.kr/v1",
    "model": "gpt-5.4",
    "debater_models": [
      {"company": "GOOGLE", "id": "gemini-3-flash"},
      {"company": "ANTHROPIC", "id": "claude-haiku-4"},
      {"company": "OPENAI", "id": "gpt-5.4-mini"}
    ]
  },
  "debug_mode": false
}
~~~

| 키 | 설명 |
|---|---|
| `web_mode` | `live`면 실제 Provider를 호출하고, `mock`이면 Provider 없이 같은 흐름을 흉내 낸다. |
| `provider.url` | OpenAI 호환 Provider 주소. `/v1` 또는 `/chat/completions`로 끝나야 한다. |
| `provider.model` | Control Model. 주제 분석, 의미 검증, State Patch 추출, Neutral Summary를 맡는다. |
| `provider.debater_models` | Debater Model 풀. 회사와 모델 ID가 서로 달라야 하며 2개 이상이어야 한다. 토론을 시작할 때 이 중 두 개를 무작위로 뽑아 A/B에 배정하고, 서명된 세션에 고정한다. |
| `debug_mode` | 진단 로그를 켠다. 기본값은 `false`다. 아래 설명 참고. |

`config.json`은 배포 파일에 포함되므로, 값을 바꾸면 커밋하고 다시 배포해야 반영된다.

**디버그 모드** — `debug_mode`를 `true`로 두면 서버가 턴마다 진단 정보를 SSE `debug` 이벤트로 보낸다. 사용자가 선택을 마친 화면에 **디버그 로그 JSON 받기** 버튼이 생기고, 다음 내용을 내려받을 수 있다.

- 턴별 계획: Turn Task, Action, Target
- 초안과 재시도 이유
- 규칙 준수 검사 결과
- State Patch
- 호출별 토큰 사용량

로그는 브라우저 메모리에만 있다. API 키, 서명 키, `engine_token`은 포함하지 않는다. 배포 환경에서 켜면 모든 방문자에게 버튼이 보이므로, 점검이 끝나면 다시 끈다.

**환경 변수** — 서버에서만 쓰는 비밀값. Vercel에서는 Project Settings의 Environment Variables에 등록한다. 로컬에서 실제 Provider를 호출하는 `etc/tools/` 진단 도구를 쓸 때는 [.env.example](.env.example)을 복사해 `.env`를 만든다. Mock 개발 서버만 쓸 때는 필요 없다.

| 변수 | 용도 |
|---|---|
| `DEBATER_API_KEY` | Provider API 키 |
| `SESSION_SECRET` | `engine_token` 서명 키 |

`.env`에는 이 두 키만 둘 수 있다. URL·모델·모드 같은 일반 설정을 넣으면 실행 시 오류가 나며 `config.json`으로 옮기라는 안내가 표시된다.

### 5.5 다른 Provider로 실행하기

기본 설정의 `copa.codyssey.kr`은 Codyssey 과정용 게이트웨이다. 다른 환경에서는 `provider.url`, 모델 ID, `DEBATER_API_KEY`를 아래 조건을 만족하는 Provider로 바꾸면 된다. 다만 다른 Provider로는 아직 검증하지 않았다.

- 모든 호출이 **하나의 URL과 하나의 API 키**로 나간다. 그래서 여러 회사의 모델을 한 주소에서 제공하는 OpenAI 호환 게이트웨이가 필요하다.
- Chat Completions의 `stream: true`와 `stream_options.include_usage`를 지원해야 한다.
- Tool Calling(`tools`)을 지원해야 한다. 구조화된 결과는 모두 Tool Call로 받는다.
- `company`는 `GOOGLE`, `ANTHROPIC`, `OPENAI` 중 하나이며, A와 B가 서로 다른 회사 모델을 쓰도록 구분하는 라벨로만 쓰인다.

### 5.6 호출량과 시간

한 턴은 Debater Model 발언 생성, Control Model 검사, State Patch 추출 호출로 이뤄지며, 실패하면 각 단계를 다시 시도한다. Provider 호출 하나의 제한 시간은 90초, Vercel Function 하나의 최대 실행 시간은 300초다.

2026-09-29 배포본에서 디버그 모드를 켜고 한 번 실측한 값이다(주제 "대학은 출석을 의무화해야 하는가?", 사용자 질문 1개 포함 14턴, A `gpt-5.4-mini` · B `claude-haiku-4` · Control `gpt-5.4`).

| 항목 | 값 |
|---|---|
| 한 턴 소요 시간 | 약 10~31초 |
| 토론 전체 | 약 5분 30초 (화면 조작 시간 포함) |
| 발언 생성 | 16번 (재시도 2번 포함), 67,031 토큰 |
| 발언 검사 | 16번 (1번은 형식 위반으로 모델 호출 없이 거부), 20,502 토큰 |
| State Patch 추출 | 15번 (재시도 1번 포함), 55,974 토큰 |
| 합계 | 약 14.4만 토큰 (턴당 약 1만) |

이 값에는 주제 분석, 논제 확정, Neutral Summary 호출이 빠져 있다. 디버그 로그가 토론 턴의 호출만 기록하기 때문이다. 주제와 모델 조합에 따라 달라지므로 대략적인 규모로만 참고한다.

### 5.7 Vercel 배포

처음 배포할 때는 다음 순서를 따른다.

1. Vercel에서 이 GitHub 저장소를 Import한다. `vercel.json`이 설정을 담고 있으므로 Framework Preset은 따로 고르지 않는다.
2. Project Settings → Environment Variables에 `DEBATER_API_KEY`와 `SESSION_SECRET`을 등록한다.
3. 배포가 끝나면 `GET /api/health`가 `"status": "ready"`를 돌려주는지 확인한다.

배포 구조는 다음과 같다.

- `public/`은 정적 Frontend로 제공되고, `api/*.py`는 Python Serverless Function으로 실행된다.
- 하이픈이 들어간 공개 API 경로(`/api/debate-step` 등)는 `vercel.json`의 rewrite로 해당 Python 파일에 연결된다.
- GitHub 저장소와 연결된 Vercel 프로젝트는 `main` 브랜치가 바뀔 때마다 배포된다.
- `GET /api/health`는 Function과 Live 설정만 확인하며 Provider를 호출하지 않는다. 응답의 `version`으로 어떤 커밋이 배포됐는지 알 수 있다.
- 화면 하단의 짧은 버전 표시는 Vercel이 `VERCEL_GIT_COMMIT_SHA`를 제공할 때만 나타난다.

---

## 6. 구현 참고

코드와 내부 구조를 빠르게 찾기 위한 참고 정보다.

### 6.1 코드 구성

<details>
<summary><strong>주요 디렉터리와 파일 보기</strong></summary>

~~~text
public/
  index.html                     화면 구조와 주요 섹션
  styles.css                     반응형 레이아웃과 상태별 UI
  app.js                         UI 상태, fetch/SSE, 토론 진행, 오류 처리
  debate_stream.js               Server-Sent Events 파서
  debate_moderator.js            서버의 진행 결정을 사회자 카드로 표시
  markdown_renderer.js           Markdown과 State 참조 렌더링

api/
  _base.py                       공통 HTTP/SSE 어댑터
  analyze_topic.py               /api/analyze-topic
  context_step.py                /api/context-step
  create_motion.py               /api/create-motion
  debate_step.py                 /api/debate-step
  neutral_summary.py             /api/neutral-summary
  health.py                      /api/health

src/runtime_config.py            config.json과 비밀 환경 변수 로딩·검증

src/web_app/
  contracts.py                   Browser ↔ Server Pydantic DTO
  api.py                         API 디스패처와 공통 오류 응답
  errors.py                      API로 노출되는 도메인 오류
  live_service.py                실제 AI 호출 흐름
  mock_service.py                Provider 없이 같은 흐름을 재현
  service_factory.py             Mock / Live 서비스 선택
  session_token.py               서명된 클라이언트 보관 세션
  live_smoke.py                  토큰 한도를 둔 1회 Live 점검

src/debate_engine/
  debate_contracts.py            Proposition / Relation / Question / Patch 계약
  debate_control.py              Semantic Facet, 질문 초점, 진전도, 이번 턴 과제
  action_policy.py               Action 후보 생성과 선택
  action_pair_state.py           Action × Target 반복·소진 상태
  target_quality.py              Target의 중요도와 실행 가능성 평가
  persona_preferences.py         Persona별 선호
  action_execution_contracts.py  15개 Action의 의미 계약
  combined_compliance.py         Action / Stance / Task 통합 검증과 재시도
  stance_compliance.py           배정된 입장 유지 검사
  surface_contract.py            출력 형식과 State 참조 검사
  state_harness.py               State Patch 추출·검증·적용
  provider_transport.py          Provider 스트리밍 호출과 응답 조립

etc/tools/                       개발 서버, preflight, 진단 도구
etc/fixtures/                    회귀 검증에 쓰는 실제 토론 기록
tests/                           Python 회귀 테스트와 tests/js/ JavaScript 테스트
docs/                            현재 설계 문서 (Topic Analyzer)
docs-legacy/                     이전 기획·검증·배포 문서 보관
~~~

</details>

### 6.2 API

| Endpoint | 역할 |
|---|---|
| `POST /api/analyze-topic` | 주제 성격과 진행 방식 분석 |
| `POST /api/context-step` | 필요한 개인 맥락을 한 번에 하나씩 수집 |
| `POST /api/create-motion` | Motion, 양측 라벨, Persona 조합 결정 |
| `POST /api/debate-step` | 계획 → 생성 → 검증 → State 갱신 |
| `POST /api/neutral-summary` | 승패 판정 없는 토론 정리 |
| `GET /api/health` | Live 설정과 배포 버전 확인. Provider 호출 없음 |

Browser와 주고받는 DTO는 Pydantic `extra="forbid"`로 정의되어 있어 정의되지 않은 필드를 받지 않는다. 내부 Patch와 Control View는 일반 응답 DTO에 그대로 노출하지 않는다.

### 6.3 Frontend와 세션

토론 화면은 확정 전 초안과 확정된 발언 기록을 따로 관리한다. `draft_reset / draft_delta`는 임시 출력이고, 서버의 `commit` 이벤트를 받은 뒤에만 발언 기록을 갱신한다. 오래 걸리는 요청은 `AbortController`로 중단할 수 있으며, 요청마다 순번을 매겨 늦게 도착한 이전 응답이 현재 화면을 덮어쓰지 않게 한다.

Serverless 인스턴스의 메모리는 세션 저장소로 쓰지 않는다. 대신 토론 상태 전체를 서명된 `engine_token`에 담아 클라이언트가 보관하고, 요청마다 서버로 다시 보낸다.

~~~text
Session + Debate State + Action history + A/B model assignment
    ↓ JSON
    ↓ zlib
    ↓ base64url body
    ↓ HMAC-SHA256 signature
engine_token
~~~

`engine_token`은 **서명되어 있을 뿐 암호화되어 있지는 않다.** 서명으로 변조 여부는 확인할 수 있지만, 내용을 숨기지는 못한다.

---

## 7. 참고 문헌

- Arkansas Communication & Theatre Arts Association (ACTAA). *Public Forum Debate (PF)*. https://www.actaa.org/Public-Forum-Debate-%28PF%29
- Tseng, Yu-Min et al. (2024). *Two Tales of Persona in LLMs: A Survey of Role-Playing and Personalization*. Findings of EMNLP 2024. https://aclanthology.org/2024.findings-emnlp.969/
- Jiang, Hang et al. (2024). *PersonaLLM: Investigating the Ability of Large Language Models to Express Personality Traits*. Findings of NAACL 2024. https://aclanthology.org/2024.findings-naacl.229/
- Nagao, Moe et al. (2026). *Personality, Role, and Expressive Style in Large Language Models: An Interactionist Analysis*. arXiv preprint. https://arxiv.org/abs/2605.28037
- Roberts, Craige (2012). *Information Structure in Discourse: Towards an Integrated Formal Theory of Pragmatics*. Semantics & Pragmatics, 5. https://doi.org/10.3765/sp.5.6
- Prakken, Henry (2005). *Coherence and Flexibility in Dialogue Games for Argumentation*. Journal of Logic and Computation. https://doi.org/10.1093/logcom/exi046
- D’Agostino, Giulia, Chris Reed, and Daniele Puccinelli (2024). *Segmentation of Complex Question Turns for Argument Mining: A Corpus-based Study in the Financial Domain*. LREC-COLING 2024. https://aclanthology.org/2024.lrec-main.1265/
- Liu, Nelson F. et al. (2024). *Lost in the Middle: How Language Models Use Long Contexts*. Transactions of the Association for Computational Linguistics, 12, 157–173. https://aclanthology.org/2024.tacl-1.9/
- Ray, Jaideep & Ankit Goyal (2026). *Structured Feedback Improves Repair in an LLM Agent Loop*. arXiv preprint. https://arxiv.org/abs/2607.14167
- PostgreSQL. *CREATE VIEW*. https://www.postgresql.org/docs/current/sql-createview.html
- React. *Choosing the State Structure*. https://react.dev/learn/choosing-the-state-structure
- Redux. *Deriving Data with Selectors*. https://redux.js.org/usage/deriving-data-selectors
