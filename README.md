# 사이 — AI Debate Harness

> 두 AI가 상대의 실제 발언에 반응하며 토론하고, 사용자는 그 공방을 지켜본 뒤 직접 판단하는 관전형 AI 토론 서비스다.

- **배포 URL**: https://a1-3-green.vercel.app
- **GitHub**: https://github.com/hodob/A1-3

**사이**는 사용자가 입력한 주제로 두 AI 토론자가 번갈아 발언하게 한다. 찬성 답변과 반대 답변을 따로 만들어 나란히 놓는 방식과 달리, 각 발언은 상대가 앞서 내놓은 주장·질문·반박·양보·수정을 다음 턴의 판단 재료로 삼는다. 사용자는 토론을 지휘하지 않고 지켜보다가 필요하면 한 번 질문하고, 승패는 마지막에 직접 판단한다.

두 토론자는 **A**와 **B**로 부르며, 논제에 대한 양쪽 입장을 하나씩 맡는다. 화면에 보이는 양측의 이름은 주제를 분석할 때 어느 쪽에도 치우치지 않게 짓는다.

이 설계의 핵심은 **이번 턴에 무엇을 할지는 Harness가 정하고, AI 모델은 그것을 문장으로 옮기기만 한다**는 점이다. AI가 쓴 발언은 Harness의 검증을 통과해야만 토론 기록에 확정된다.

이 문서에서 자주 쓰는 용어는 다음과 같다.

- **Harness**: 사이의 서버 코드. 토론의 진행자이자 심판 역할을 한다. 지금까지의 토론을 정리한 기록(**Debate State**)을 읽고 이번 턴에 할 일을 정한 뒤, AI가 쓴 발언이 규칙을 지켰는지 검사한다.
- **Debater Model**: A와 B의 발언 문장을 실제로 만드는 외부 AI 모델.
- **Control Model**: 토론 발언 대신 주제 분석, 발언 검사, 토론 정리처럼 정해진 형식의 결과를 만드는 외부 AI 모델.
- **Provider**: 위 AI 모델들을 빌려 쓰는 외부 서비스(API).

## 목차

1. [전체 사용자 흐름](#1-전체-사용자-흐름)
2. [전체 시스템 구조](#2-전체-시스템-구조)
3. [토론이 다음 발언을 만드는 방법](#3-토론이-다음-발언을-만드는-방법)
4. [토론 진행 규칙](#4-토론-진행-규칙)
5. [설계 포인트](#5-설계-포인트)
6. [실행과 배포](#6-실행과-배포)
7. [구현 참고](#7-구현-참고)
8. [참고 문헌](#8-참고-문헌)

---

## 1. 전체 사용자 흐름

입력된 문장으로 AI에게 곧바로 찬반 토론을 시키지 않는다. 토론할 수 있는 주제인지, 사용자만 아는 맥락이 필요한지, 사실 설명이 먼저 필요한 질문인지를 먼저 판단한 뒤 토론을 시작한다.

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
| 확인 필요 | "재택근무 어때?" | 막연한 질문을 토론 문장으로 바꾸다 보면 원래 없던 내용이 들어갈 수 있다. 예를 들어 "회사는 재택근무를 허용해야 한다"로 바꾸면 '회사'라는 대상이 새로 생긴다. 이렇게 뜻이 바뀔 수 있을 때는 바꾼 이유를 보여 주고 사용자에게 확인받는다. |
| 개인 맥락 필요 | "철수와 영희 중 누가 더 잘못했어?" | 직접 본 일, 전해 들은 일 등 판단에 필요한 사실을 한 번에 하나씩 묻는다. |
| 사실 설명이 먼저 필요 | "파이썬 리스트가 뭐야?" | 토론보다 설명이 먼저인 입력이므로 주제를 바꾸도록 안내한다. |

Topic Analyzer는 주제를 "찬반 가능/불가능"으로만 나누지 않는다. 어떤 종류의 논쟁인지(정의·정책·가치 등), 이미 사실로 결론 난 문제인지 아직 논쟁 중인지, 진지하게 다룰지 가볍게 다룰지, 추가 정보가 필요한지를 각각 따로 판단한다. 개인적인 사건이라면 사용자가 말하지 않은 사실을 AI가 지어내 채우지 않는다.

Motion은 토론을 시작하기 전에 사용자가 한 번 수정할 수 있다.

### 1.2 토론이 시작된 뒤

단계 이름은 미국 고교 토론 대회 형식인 Public Forum에서 가져왔다. **Opening**은 첫 주장 발표, **Crossfire**는 서로 묻고 답하는 교차 질의, **Rebuttal**은 반박, **Final Focus**는 마무리 발언이다. 화면에는 각각 "첫 입장", "주고받기", "쟁점 되짚기", "마지막 한마디"로 표시된다. A와 B는 번갈아 발언하며, 토론 전체는 최대 12턴이다(사용자 질문에 대한 답변 2턴은 별도).

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

사용자는 Opening과 Crossfire를 지켜보다가, 원하면 A와 B에게 같은 질문을 하나 던질 수 있다. 토론이 끝나면 AI가 승자를 판정하지 않는다. 사용자는 토론 정리(Neutral Summary)를 읽고 A / 아직 모르겠다 / B 중 하나를 직접 고른다. 정리 화면과 마지막 화면에는 각 토론자의 논증 성향(Persona, 3.3 참고)과 실제로 발언을 만든 AI 모델 이름이 함께 표시된다. 토론 내용과 선택은 서버에 저장하지 않는다.

실제 토론의 한 장면이다(주제: "대학은 출석을 의무화해야 하는가?").

> **B · 의무화 반대** — 발언 2 · 첫 입장
>
> 출석 의무화는 학생의 자율성 제약이 실제 학습 성과로 이어지지 않는다는 점에서 정당성이 약합니다. …
>
> **A · 의무화 찬성** — 발언 3 · 주고받기
>
> ↖ B · 발언 2의 결론은 "자율성 제약이 성과로 이어지지 않는다"는 점을 사실상 의무화 전반의 정당성 약화로 바로 연결하고 있는데, 그 추론은 너무 강합니다. …

`↖ B · 발언 2`는 A가 겨냥한 앞 발언을 가리키는 참조 표시다. A는 새 주장을 늘어놓는 대신 B의 추론 한 곳을 골라 공격했다. 이 선택은 모델이 아니라 Harness가 내렸다. Harness가 정한 이번 턴의 과제는 "상대의 핵심 이유 하나를 검증하기"였고, 행동은 "근거에서 결론으로 가는 추론이 충분한지 문제 삼기"(`CHALLENGE_INFERENCE`)였다.

---

## 2. 전체 시스템 구조

시스템은 **화면**, **진행 관리**, **토론 제어**, **발언 생성**을 서로 분리한다.

**그림 3. 시스템 경계 — 사이와 외부 AI Provider**

~~~mermaid
flowchart TD
    U[사용자] --> B

    subgraph SAI[사이]
        B[Browser<br/>UI]
        API[Vercel Python API]
        H[Debate Harness<br/>State · 계획 · 검증]
        W[Web Service<br/>진행 관리 · AI 호출]

        B -->|JSON / SSE| API
        API --> W
        H <--> W
    end

    subgraph EXT[외부 AI Provider]
        D[Debater Models<br/>A/B 발언 생성]
        C[Control Model<br/>분석 · 검사 · 기록 정리 · 요약]
    end

    W <-->|발언 생성| D
    W <-->|분석 · 검사 요청| C
~~~

| 구성 요소 | 역할 |
|---|---|
| **Browser** | 주제 입력, 토론 관전, 사용자 질문, 최종 선택, 확정 전 초안 표시 |
| **Web Service** | 화면의 요청을 받아 토론 순서를 진행하고, 필요한 AI 호출을 맡는다 |
| **Debate Harness** (이하 Harness) | 현재 토론을 읽어 이번 턴의 과제·Action·Target을 정하고 결과를 검증 |
| **Debater Models** | Harness가 정한 조건에 맞는 실제 발언을 생성 |
| **Control Model** | 주제 분석, 발언 검사, 토론 기록 정리, 최종 요약 |

가장 중요한 경계는 **무엇을 할지 결정하는 부분**과 **실제 문장을 만드는 모델**을 나눴다는 점이다.

---

## 3. 토론이 다음 발언을 만드는 방법

두 모델에게 번갈아 답변만 받는다면 각 모델이 이전 대화만 보고 다음 말을 알아서 정한다. 사이에서는 모델이 말하기 전에 Harness가 다음 네 단계를 거친다.

1. 확정된 토론 기록에서 아직 남아 있는 쟁점과 열린 질문(아직 답이 나오지 않은 질문)을 찾는다.
2. 이번 턴에 해결할 과제(**Turn Task**)를 정한다.
3. 어떤 행동(**Action**, 예: 반박·질문·방어)을 어떤 대상(**Target**)에 할지 고른다. Target은 토론 기록에 번호로 남은 특정 주장(`C15`)이나 질문(`Q3`)이다. 행동과 대상의 짝을 이 문서에서는 `Action × Target`으로 표기한다.
4. 이번 턴에 필요한 참고 자료(**Context**)만 골라 Debater Model에 넘긴다.

### 3.1 예시: 핫도그 토론의 6번째 턴

"핫도그는 샌드위치인가?" 토론에서 A는 "샌드위치에 들어간다", B는 "별도 범주다" 쪽이다.

5턴까지 쌓인 Debate State의 일부다. `C`로 시작하는 항목은 주장, `Q`로 시작하는 항목은 질문이다.

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
| 제외된 예 | `CHALLENGE_PREMISE × C1`(C1의 전제 공격): B가 4턴에 이미 했으므로 반복하지 않는다(**소진**). `REQUEST_SUPPORT × C1`(C1의 근거 요구): C1에는 이미 근거(C2 등)가 있으므로 의미가 없다(**해결**). |
| 선택 | 이 주제는 정의 논쟁이라 B에게 Falsifier(반례 탐색형) Persona가 배정되어 있고, 그 결과 `DEFEND_CLAIM × C15`를 고른다. 같은 상황에서 Persona만 Synthesist(조정 통합형)로 바꾸면 `REVISE_CLAIM`을 고른다. |

Debater Model은 `Q3`, `C15`와 관련 주장을 참고 자료로 받아, "왜 번이 이어진 형식이 결정선인지"를 방어하는 발언을 쓴다.

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

반면 "두 주장이 사실상 같은 말인가?", "최근 턴에서 토론이 실제로 진전됐는가?", "지금 가장 먼저 답해야 할 질문은 무엇인가?"처럼 저장된 State로 계산할 수 있는 정보는 저장하지 않고 매 턴 다시 계산한다. 이 계산 결과를 **Control View**라고 부른다. 매 턴 새로 그리는 '토론 현황판'이라고 생각하면 된다. Harness는 Control View로 `Turn Task`를 만들고, 그 과제를 수행할 수 있는 `Action × Target` 후보 중 하나를 고른다.

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
<summary><strong>Debate State와 Control View 자세히 보기</strong></summary>

State의 주요 구조는 다음과 같다.

| 구조 | 기록하는 것 |
|---|---|
| **Proposition** (주장) | 실제로 제시된 주장 |
| **Relation** (관계) | 주장 사이의 지지·공격·모순·한정 관계 |
| **Question** (질문) | 제기된 질문과 답변 여부(열림 / 해결됨) |
| **Commitment Event** (입장 변화) | 주장·양보·철회·수정 같은 입장 변화 |

주장을 수정해도 기존 Proposition을 덮어쓰지 않고, 새 Proposition과 수정 관계를 함께 남긴다.

~~~text
C12  기존 주장: "모든 경우에 X다"
C19  수정 주장: "조건 Y에서는 X다"
REVISE  C12 → C19
~~~

Control View는 같은 주장의 여러 버전 묶음(Semantic Facet, 3.4 참고), 비슷한 질문 묶음, 토론이 실제로 진전됐는지를 계산한다. 그 결과와 현재 발언자를 기준으로 지금 가장 먼저 답해야 할 질문(QUD)을 고른다.

이렇게 매번 계산하는 이유는 기록과 현황이 서로 어긋나지 않게 하기 위해서다. 예를 들어 "Q3에 답이 나왔다"를 따로 적어 두면, 나중에 답변이 수정됐을 때 그 메모를 고치는 것을 잊을 수 있다. 매 턴 기록에서 다시 확인하면 그런 일이 생기지 않는다.

</details>

### 3.3 Action 선택과 Persona

Harness는 이번 과제에 쓸 수 있는 `Action × Target` 후보를 모두 만든 뒤, 의미 없는 후보를 먼저 뺀다. 이미 목적을 이룬 것(해결), 이미 한 번 한 것(소진), 대상이 맞지 않는 것(예: 자기 주장에 반박하기)이다. 남은 후보는 다음 순서로 비교해 하나를 고른다.

1. 지금 쟁점에서 얼마나 중요한 대상인가
2. 지금 상황에서 더 효과적인 행동인가 (예: 상대가 답을 피한 질문 다시 묻기 → 근거가 있는 주장의 추론 공격 → 근거가 없는 주장에 근거 요구 순)
3. 토론자의 Persona가 선호하는 행동인가
4. 아직 덜 다뤄진 대상인가

- **소진**: 같은 발언자가 같은 `Action × Target`을 이미 한 번 사용한 상태. 같은 공격을 되풀이하지 않도록 기본적으로 다시 고르지 않는다. 단, 근거가 아직 약한 주장에 대한 근거 요구나, 상대가 부분적으로만 답했거나 피한 질문을 다시 묻는 것은 계속 열어 둔다.
- **해결**: 그 행동의 목적이 이미 이뤄진 상태. 예를 들어 근거가 충분히 제시된 주장에 대한 근거 요구나, 이미 직접 답이 나온 질문에 대한 재질문은 해결된 것으로 보고 고르지 않는다.

**Persona**는 토론자의 논증 성향이다. 논제를 확정할 때 주제 유형에 따라 A와 B에게 서로 다른 Persona가 하나씩 배정된다(예: 정의 논쟁은 Socratic과 Falsifier, 정책·가치 논쟁은 Principlist와 Pragmatist). Persona는 **어떤 행동을 허용할지 정하는 규칙이 아니라, 허용된 행동 중에서 무엇을 더 선호할지 정하는 성향**이다. 그래서 Persona가 특정 행동을 선호하더라도, 이미 해결된 질문이나 소진된 Action × Target을 다시 고르게 만들 수는 없다.

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

</details>

### 3.4 모델에는 이번 턴에 필요한 Context만 보낸다

토론 기록(Debate State)이 쌓였다고 해서 매 턴 기록 전체를 Debater Model에 넣지는 않는다. 이번 턴에 꼭 필요한 정보(이 문서에서는 **Relevant Context**라고 부른다)만 골라 넘긴다. 고르는 기준은 다음과 같다.

- 이번 턴의 과제와 공격·방어 대상이 되는 주장이나 질문
- 지금 가장 먼저 답해야 할 질문(**QUD**, Question Under Discussion)과 그 질문이 가리키는 주장
- 그 주장의 **처음 버전과 최신 버전** (아래 설명)
- 최근 발언에서 실제로 언급된 주장과 질문

토론을 하다 보면 같은 주장이 표현만 바뀌거나 범위가 좁혀져 여러 번 나온다. Harness는 이런 주장들을 한 묶음으로 본다(**Semantic Facet**). 예를 들면 다음과 같다.

~~~text
1턴  "출석은 학습에 도움이 된다."                        ← 처음 버전
3턴  "수업에 나와야 더 잘 배운다."                       ← 같은 말을 다시 함
5턴  "토론·실습 수업에서는 출석이 학습에 도움이 된다."    ← 범위를 좁혀 고침 (최신 버전)
~~~

모델에게는 세 개를 모두 넘기지 않고 처음 버전과 최신 버전만 넘긴다. 그래서 모델은 원래 무슨 주장이었는지와 지금은 어디까지 물러섰는지를 함께 안다. 같은 주장을 여러 개의 다른 주장으로 착각해 반복 공격하는 일도 줄어든다.

~~~text
전체 Debate State
    ↓ 현재 상황 계산
Turn Task / Action × Target / QUD
    ↓ 관련 항목 선택
이번 턴의 Relevant Context
    ↓
Debater Model
~~~

토론 기록이 주장·질문 단위로 정리되어 있기 때문에 지금 중요한 항목만 골라낼 수 있다. 입력이 길면 모델이 중간 정보를 놓치기 쉬우므로, 짧고 초점 있는 입력이 발언 품질에도 도움이 된다.

### 3.5 생성된 발언은 바로 확정되지 않는다

**그림 5. 한 턴의 확정 과정 — 초안에서 확정 발언까지**

~~~mermaid
flowchart TD
    P[Turn Plan<br/>Task · Action · Target<br/>Context]
    G[Debater Model<br/>발언 생성]
    D[Streaming Draft<br/>확정 전 초안]

    subgraph S1["① 발언 검사 · 다시 쓰기 최대 3번"]
        V{규칙 준수 검사}
        R[다시 쓰기<br/>Repair · Replan]
    end

    subgraph S2["② 기록 정리 · 다시 정리 최대 2번"]
        S[State Patch<br/>토론 기록으로 정리]
        SR[다시 정리]
    end

    C[Commit<br/>발언 + 새 Debate State 확정]
    X[이번 턴은 확정하지 않음<br/>기존 기록 유지]

    P --> G
    G --> D
    D --> V
    V -->|불합격| R
    R --> P
    V -->|통과| S
    S -->|형식 오류| SR
    SR --> S
    S -->|성공| C
    R -.->|3번 다 씀| X
    SR -.->|2번 다 씀| X
~~~

한 턴은 두 단계를 거치고, 단계마다 다시 시도하는 횟수를 따로 센다.

- **① 발언 검사**: 발언이 규칙을 어기면 발언을 다시 쓴다. 최대 3번까지 쓴다.
- **② 기록 정리**: ①을 통과한 발언을 토론 기록으로 정리한다. 정리 결과의 형식이 틀리면 정리만 다시 한다. 최대 2번까지 한다.

②에서 실패해도 ①로 돌아가지 않는다. 발언은 이미 규칙을 통과했으므로 다시 쓸 필요가 없기 때문이다. 어느 단계든 기회를 다 쓰면 그 턴은 확정되지 않는다.

화면에 스트리밍되는 초안은 아직 확정된 발언이 아니다. Harness는 먼저 초안이 규칙을 지켰는지 검사한다. 검사 항목은 다음과 같다.

- 배정된 입장(Assigned Stance)을 유지했는가
- 이번 턴의 과제(Turn Task)를 수행했는가
- 고른 행동을 고른 대상에 실제로 했는가(Action × Target)
- 길이·형식 규칙을 지켰는가 (예: Final Focus는 최대 2문장)
- 이전 발언을 가리키는 표시(`↖`)를 실제로 있는 발언에만 달았는가

검사에 실패하면 두 가지 방법으로 다시 시도한다. 발언 생성은 둘을 합쳐 한 턴에 최대 3번까지 한다.

- **Targeted Repair(부분 수정)**: 계획은 그대로 두고, 앞의 초안과 함께 무엇이 왜 틀렸는지(예: "입장을 뒤집었다")를 알려 주며 그 부분만 고쳐 쓰게 한다.
- **Replan(재계획)**: 수정으로도 안 되면 Harness가 같은 Turn Task 안에서 다른 Action × Target을 골라 새로 쓰게 한다.

검사를 통과하면 이 발언으로 토론 기록에 무엇이 바뀌었는지(새 주장, 새 질문, 답변, 양보 등)를 정해진 형식으로 뽑아낸다. 이것을 **State Patch**라고 부른다. 뽑아낸 결과가 형식에 맞지 않으면 한 번 더 뽑는다(최대 2번). State Patch까지 토론 기록에 반영되어야 발언이 확정된다.

끝까지 실패하면 그 턴은 확정되지 않고, 기존 발언 기록과 Debate State도 바뀌지 않는다. 화면에는 "다음 발언을 이어가지 못했어요"라는 안내와 **이 발언 다시 준비하기** 버튼이 나타나며, 사용자는 여기까지의 토론을 잃지 않고 같은 턴을 다시 시도할 수 있다.

> **실제 토론에서 본 예** — "대학은 출석을 의무화해야 하는가?" 토론(14턴)에서 2개 턴이 첫 초안에서 거부되고 `Targeted Repair` 한 번으로 통과했다.
>
> - 10번째 턴(B, 의무화 반대): 사용자 질문에 답하면서 "출석 의무화를 유지하되…"라고 써서 자기 입장을 뒤집었다. `STANCE_REVERSAL`로 거부됐고, 재작성본은 반대 입장을 유지했다. 거부된 초안도 스트리밍 중에는 화면에 잠시 보였는데, 초안을 확정 전으로 표시하는 이유가 바로 이것이다.
> - 14번째 턴(B, Final Focus): 세 문장을 써서 `FINAL_FOCUS_LENGTH`(최대 2문장)로 거부됐다.

---

## 4. 토론 진행 규칙

토론 단계는 Public Forum Debate의 Constructive–Crossfire–Rebuttal–Final Focus 구성을 참고해, 관전형 서비스에 맞게 단순화했다.

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

정해진 턴 수를 반드시 채우지 않는다. 지금까지의 토론 기록에서 더 다룰 가치가 있는 과제가 없으면, AI를 더 호출하지 않고 다음 단계로 넘어간다. Crossfire가 일찍 끝나면 곧바로 사용자 질문 단계로, Rebuttal이 일찍 끝나면 Final Focus로 넘어간다.

Crossfire에서는 새 주장을 계속 늘리기보다, 이미 나온 상대의 핵심 이유를 질문·반례·추론 공격·입장 확인 요구·부분 양보·수정으로 실제로 처리하는 것을 우선한다.

---

## 5. 설계 포인트

### 5.1 AI 기능을 넣은 이유

보통의 AI 답변은 모델 하나가 결론까지 정리해 준다. 그러면 사용자는 결론만 받고, 그 결론이 어떤 반론을 거쳐 나왔는지는 보지 못한다.

사이는 AI를 **답을 주는 도구가 아니라 논쟁을 보여 주는 도구**로 쓴다. 서로 다른 회사의 두 모델이 서로 다른 입장과 논증 성향을 맡아 반박·질문·양보·수정을 주고받는다. 사용자는 한 주제가 여러 관점에서 어떻게 부딪히는지 보고, 판단은 스스로 내린다. 그래서 AI가 승자를 정하지 않는다.

### 5.2 프롬프트 구성

모델에게 "토론해 줘"라고 한 번에 맡기지 않는다. 매 턴 Harness가 그 턴에 필요한 지시를 조립해서 보낸다.

| 구성 | 내용 |
|---|---|
| 고정 규칙 | 통계·연구·인용을 지어내지 않는다. 상대가 실제로 한 말에 반응한다. 질문에는 직접 답한다. 자기 입장을 상대편으로 뒤집지 않는다. |
| 역할 | 맡은 입장(예: 의무화 반대), Persona(예: 현실 실용형), 현재 단계 |
| 단계별 지시와 분량 | 예: Opening은 핵심 이유 1~2개를 2~3문장으로, Final Focus는 2문장 이내로 |
| 말투 | 진지한 주제는 사실과 불확실성 표현 우선, 가벼운 주제는 가벼운 비유 허용 |
| 이번 턴의 과제 | Turn Task, 고른 Action과 그 Action이 만들어야 할 효과, 대상(Target) |
| 참고 자료 | 이번 턴에 필요한 이전 주장·질문 목록(최대 12개)과 지금까지의 발언 |
| 사용자 질문 | 사용자 질문 단계라면 그 질문 |

사용자가 입력한 주제와 질문은 **지시가 아니라 토론 자료**로 표시해서 넘긴다. 입력 안에 "이전 규칙을 무시해" 같은 문장이 있어도 모델이 명령으로 따르지 않게 하기 위해서다.

검사에 실패해 다시 쓰게 할 때는 앞의 초안과 무엇이 왜 틀렸는지를 함께 보낸다(3.5의 부분 수정).

주제 분석과 토론 정리 프롬프트는 모델이 자유 문장 대신 **정해진 칸에 맞춘 데이터(JSON)**를 돌려주게 한다. 서버는 그 결과가 형식에 맞는지 다시 검사한 뒤 사용한다. 예를 들어 토론 정리에서는 승자나 점수를 매기지 말고 핵심 충돌, 양측의 강한 논점, 합의, 남은 쟁점만 목록으로 돌려달라고 요청한다.

### 5.3 화면의 로딩·성공·실패 처리

AI 응답은 몇 초에서 수십 초가 걸리고 실패할 수도 있다. 그래서 요청 전후의 상태를 나눠서 처리한다.

| 상태 | 화면 처리 |
|---|---|
| **요청 전 (입력 검사)** | 빈 입력이면 "토론할 이야기를 한 줄 적어주세요."를 보여 주고 요청을 보내지 않는다. 2000자를 넘어도 안내한다. 서버에서도 같은 규칙으로 한 번 더 검사한다. |
| **로딩** | 진행 문구를 보여 주고, 같은 요청이 두 번 가지 않게 버튼을 잠근다. 15초가 지나면 "평소보다 오래 걸리고 있어요.", 60초가 지나면 **기다리기 중단** 버튼을 보여 준다. 180초가 지나면 자동으로 중단한다. |
| **성공** | 주제 분석과 정리는 결과를 바로 보여 준다. 토론 발언은 만들어지는 대로 "작성 중 · 아직 확정되지 않았어요" 표시와 함께 흘려 보여 주고, 검사를 통과하면 확정된 발언으로 바꾼다. |
| **실패** | 오류 종류에 맞는 안내와 **다시 시도** 버튼을 보여 준다. 입력한 내용과 여기까지의 토론은 그대로 남는다. |

| 실패 상황 | 안내 문구 |
|---|---|
| 발언이 검사를 끝내 통과하지 못함 | 다음 발언을 이어가지 못했어요. (이 발언 다시 준비하기) |
| 응답 지연·시간 초과 | 응답을 기다리는 시간이 길어져 멈췄어요. |
| 서버 설정 오류 | 지금은 토론을 준비할 수 없어요. |
| 토론 정리 실패 | 토론 정리를 불러오지 못했어요. |

사용자가 중단하고 다시 시도했을 때 늦게 도착한 이전 응답이 새 화면을 덮어쓰지 않도록, 요청마다 번호를 붙여 최신 요청의 응답만 반영한다.

### 5.4 배포 후 문제 진단과 수정

배포 후 문제가 생기면 다음 순서로 확인한다.

1. **배포 상태 확인**: `/api/health`에서 서버가 떠 있는지, 설정이 맞는지, 어떤 커밋이 배포됐는지(`version`) 본다. AI를 호출하지 않으므로 비용이 들지 않는다.
2. **브라우저 확인**: 개발자 도구의 콘솔과 네트워크 탭에서 어떤 요청이 어떤 오류 코드로 실패했는지 본다.
3. **서버 로그 확인**: Vercel 관리 화면의 Function 로그에서 서버 쪽 오류 기록을 본다.
4. **로컬에서 재현**: AI를 호출하지 않는 테스트와 Mock 서버로 같은 상황을 재현한다.
5. **수정과 재배포**: 코드를 고쳐 GitHub에 push하면 Vercel이 자동으로 다시 배포한다. `/api/health`의 `version`이 새 커밋으로 바뀐 것을 확인하고, 배포 URL에서 다시 동작을 확인한다.

실제로 겪은 사례는 다음과 같다.

| 문제 | 진단 | 수정 |
|---|---|---|
| `api/` 아래 여러 Python 함수가 함께 배포되지 않음 | Vercel이 프로젝트 종류를 자동으로 판단하면서 여러 함수 구성과 맞지 않았다. | `vercel.json`에 프로젝트 종류를 "Other"(`framework: null`)로 지정하고, 같은 문제가 다시 생기지 않도록 테스트를 추가했다. |
| 문서 폴더를 옮긴 뒤 GitHub Actions(push할 때마다 자동으로 도는 테스트) 실패 | Actions 결과에서 테스트가 옛 문서 경로를 읽고 있음을 확인했다. | 테스트 경로를 고쳐 push하고, Actions가 다시 통과하는 것을 확인했다. |
| 배포 환경의 실제 동작을 자세히 점검 | 디버그 모드를 켜서 턴별 계획, 검사 결과, 토큰 사용량을 기록했다. | 점검 결과를 문서에 반영한 뒤 디버그 모드를 끄고 다시 배포했다. |

---

## 6. 실행과 배포

### 6.1 기술 스택

| 영역 | 기술 |
|---|---|
| Frontend | HTML, CSS, Vanilla JavaScript |
| Backend | Python 3.12, Vercel Serverless Functions |
| AI | OpenAI 호환 API — OpenAI와 같은 방식으로 여러 회사의 모델을 부를 수 있는 방식 (발언 생성 모델 3종 중 2개 + 검증·정리 모델 1개) |
| 실시간 표시 | Server-Sent Events (SSE) — 서버가 만든 글을 조금씩 바로바로 브라우저로 보내는 방식 |
| 배포 | GitHub + Vercel |

### 6.2 환경 변수 설정

API 키 같은 비밀값은 코드와 저장소에 넣지 않고 **서버 환경 변수**로만 관리한다. 브라우저에는 전달되지 않는다.

| 환경 변수 | 용도 |
|---|---|
| `DEBATER_API_KEY` | AI Provider API 키 |
| `SESSION_SECRET` | 브라우저가 보관하는 토론 기록이 조작되지 않았는지 확인하는 서명 키 (7.2 참고) |

- **Vercel**: Project Settings → Environment Variables에 등록한다.
- **로컬**: [.env.example](.env.example)을 복사해 `.env`를 만든다.

비밀이 아닌 설정(동작 모드, 모델 이름, Provider 주소)은 [config.json](config.json)에 둔다. 발언 모델은 gemini-3-flash, claude-haiku-4, gpt-5.4-mini 중 서로 다른 회사의 두 개가 토론마다 무작위로 A와 B에 배정되고, 검증과 정리는 gpt-5.4가 맡는다. `config.json`을 바꾸면 커밋하고 다시 배포해야 반영된다.

### 6.3 로컬 실행

~~~bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m etc.tools.web_dev_server
~~~

http://127.0.0.1:8765 에 접속한다. 로컬 서버는 AI를 호출하지 않는 **Mock 모드**로만 동작해 API 키 없이 화면 흐름을 확인할 수 있다. 실제 AI 토론은 배포 환경에서 동작한다.

테스트는 `python -m unittest discover -s tests -q`로 실행한다.

### 6.4 Vercel 배포

1. Vercel에서 이 GitHub 저장소를 Import한다.
2. 6.2의 환경 변수 두 개를 등록한다.
3. 배포가 끝나면 `/api/health`에서 `"status": "ready"`를 확인한다.

이후에는 `main` 브랜치에 push할 때마다 자동으로 다시 배포된다.

### 6.5 응답 시간과 비용

배포 환경에서 토론 한 판(사용자 질문 포함 14턴)을 실측한 값이다.

| 항목 | 값 |
|---|---|
| 한 턴 소요 시간 | 약 10~31초 |
| 토론 전체 | 약 5분 30초 |
| 사용 토큰 (AI가 읽고 쓴 글의 양) | 약 14.4만 (턴당 약 1만) |
| 재작성된 턴 | 14턴 중 2턴 |

토큰은 발언 생성(약 47%), 토론 기록 정리(State Patch, 약 39%), 규칙 검사(약 14%) 순으로 쓰였다.

---

## 7. 구현 참고

### 7.1 API

브라우저는 `fetch`로 아래 Serverless Function을 호출한다.

| Endpoint | 역할 |
|---|---|
| `POST /api/analyze-topic` | 주제 성격과 진행 방식 분석 |
| `POST /api/context-step` | 필요한 개인 맥락을 한 번에 하나씩 수집 |
| `POST /api/create-motion` | 논제, 양측 이름, Persona 결정 |
| `POST /api/debate-step` | 한 턴 계획 → 생성 → 검증 → 기록 |
| `POST /api/neutral-summary` | 승패 판정 없는 토론 정리 |
| `GET /api/health` | 배포 상태 확인 (AI 호출 없음) |

### 7.2 토론 상태 보관 방식

Vercel 같은 Serverless 환경은 요청이 끝나면 서버의 메모리가 사라질 수 있다. 그래서 진행 중인 토론을 서버에 저장하지 않고, 토론 상태 전체를 서명이 붙은 데이터 조각(**토큰**, 6.5의 AI 사용량 토큰과는 다른 뜻)에 담아 브라우저가 보관하고, 요청마다 서버로 다시 보낸다. 서명 덕분에 서버는 누군가 토론 기록을 몰래 바꾸지 않았는지 확인할 수 있다. 다만 암호화는 하지 않으므로 내용을 숨기지는 못한다.

---

## 8. 참고 문헌

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
