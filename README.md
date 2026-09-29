# 사이 — AI Debate Harness

> **두 AI의 찬반 답변을 따로 만들어 나란히 보여주는 서비스가 아니라, 상대의 실제 이전 발언과 구조화된 토론 상태 때문에 다음 발언이 달라지도록 만든 관전형 AI 토론 시스템이다.**

**사이**는 사용자가 주제를 입력하면 두 AI 토론자가 순차적으로 발언하고, 서로의 주장·질문·반박·양보·수정을 다음 턴의 판단 재료로 사용하는 웹 서비스다. 사용자는 토론을 지휘하기보다 공방을 지켜보고, 필요하면 한 번 질문한 뒤 마지막 판단을 직접 내린다.

핵심은 **Debater Model이 혼자 다음 행동까지 결정하지 않는다는 것**이다. Harness가 현재 토론을 읽고 이번 턴에서 해결할 과제와 대상을 정한 뒤 모델에게 발언을 맡기고, 검증을 통과한 결과만 다음 토론 상태로 확정한다.

## 목차

1. [전체 사용자 흐름](#1-전체-사용자-흐름)
2. [전체 시스템 구조](#2-전체-시스템-구조)
3. [토론이 다음 발언을 만드는 방법](#3-토론이-다음-발언을-만드는-방법)
4. [토론 진행 규칙](#4-토론-진행-규칙)
5. [구현 참고](#5-구현-참고)
6. [References](#6-references)

---

## 1. 전체 사용자 흐름

처음 입력된 문장을 바로 찬반 프롬프트에 넣지 않는다. 먼저 토론 가능한 주제인지, 사용자만 알고 있는 맥락이 필요한지, 사실 설명이 먼저 필요한 입력인지 판단한 뒤 토론을 시작한다.

### 1.1 토론을 시작하기 전

**그림 1. 토론 준비 흐름 — 주제를 토론 가능한 상태로 만드는 과정**

~~~mermaid
flowchart TD
    A[주제 입력] -->|분석| B{"어떻게 진행할까?<br/>Topic Analyzer"}
    B -->|바로 가능| M[Motion 확인]
    B -->|확인 필요| C[확인 이유 표시]
    C --> M

    B -->|개인 맥락 필요| D[Context 질문 1개]
    D -->|사용자 답변| E{맥락이 충분한가?}
    E -->|아니오| D
    E -->|예| F[Context Summary]
    F --> M

    B -->|사실 설명이 먼저 필요| I[주제 수정 안내]
    I --> A
    M -->|최대 1회 수정| Z[토론 시작]
~~~

Topic Analyzer는 단순히 “찬반 가능/불가능”만 분류하지 않는다. 주제의 종류와 사실적 지위, 어떤 방식으로 토론할지, 추가 맥락이 필요한지 등을 나눠 판단한다. 개인 사건이라면 한 번에 하나씩 필요한 맥락을 묻고, 사용자가 제공하지 않은 사건 사실을 AI가 임의로 채우지 않는다.

<details>
<summary><strong>Topic Analyzer의 실제 계약 값 보기</strong></summary>

| 계약 필드 | 실제 허용 값 |
|---|---|
| `claim_type` | `FACT`, `DEFINITION`, `CAUSE`, `VALUE`, `POLICY`, `COMPARISON`, `INTERPRETATION`, `PERSONAL_DISPUTE`, `INFORMATIONAL`, `OTHER` |
| `epistemic_status` | `NON_FACTUAL`, `OPEN_EMPIRICAL`, `GENUINELY_CONTESTED`, `WEIGHT_DOMINANT_TRUE`, `WEIGHT_DOMINANT_FALSE`, `FORMALLY_SETTLED`, `UNKNOWN` |
| `treatment_mode` | `NATURAL_DEBATE`, `PLAYFUL_DEBATE`, `REFRAMED_DEBATE` |
| `interaction_state` | `READY`, `CONFIRMATION_REQUIRED`, `CONTEXT_REQUIRED`, `INFORMATIONAL_FIRST` |
| `truth_mode` | `REAL_WORLD`, `STIPULATED_COUNTERFACTUAL`, `RHETORICAL_PLAY` |
| `tone_hint` | `SERIOUS`, `PLAYFUL`, `None` |

현재 구현에서는 이 값들을 Pydantic DTO의 `Literal` 타입으로 제한한다.

</details>

### 1.2 토론이 시작된 뒤

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

사용자는 토론을 직접 지휘하지 않는다. Opening과 Crossfire를 지켜보다가 원하면 같은 질문을 A와 B 모두에게 던질 수 있고, 마지막에는 승자를 자동 판정하는 대신 Neutral Summary를 본 뒤 A / 모르겠다 / B 중 직접 선택한다.

세부 단계별 역할과 조기 종료 규칙은 [4. 토론 진행 규칙](#4-토론-진행-규칙)에서 설명한다.

---

## 2. 전체 시스템 구조

시스템은 **화면**, **제품 흐름과 세션**, **토론 제어**, **실제 발언 생성**을 분리한다.

**그림 3. 시스템 경계 — 사이와 외부 AI Provider**

~~~mermaid
flowchart TD
    U[사용자]

    subgraph SAI[사이]
        B[Browser<br/>UI]
        API[Vercel Python API]
        W[Web Service<br/>제품 흐름 · 세션 · Provider orchestration]
        H[Debate Harness<br/>State · Planning · Validation]

        B -->|JSON / SSE| API
        API --> W
        W --> H
        H --> W
    end

    subgraph EXT[외부 AI Provider]
        D[Debater Models<br/>A/B 발언 생성]
        C[Control / Coordinator<br/>분석 · 구조화 · 검증 · 요약]
    end

    U --> B
    W <-->|발언 생성| D
    W <-->|구조화된 판단| C
~~~

| 구성 요소 | 역할 |
|---|---|
| **Browser** | 주제 입력, 토론 관전, 사용자 질문, 최종 선택, provisional draft 표시 |
| **Web Service** | 제품 흐름, 세션, Provider 호출을 조정 |
| **Debate Harness** | 현재 토론을 읽고 다음 과제·Action·Target을 정하고 결과를 검증 |
| **Debater Models** | Harness가 정한 조건에 맞는 실제 발언을 생성 |
| **Control / Coordinator** | 주제 분석, State Patch 추출, semantic compliance, Neutral Summary 같은 구조화 작업 |

이 구조에서 중요한 경계는 **“무엇을 할지 결정하는 부분”과 “실제 문장을 생성하는 모델”을 분리했다는 점**이다.

---

## 3. 토론이 다음 발언을 만드는 방법

일반적인 두 AI 답변 비교라면 각 모델이 주제와 이전 대화를 보고 알아서 다음 말을 만들 수 있다. 사이는 그 사이에 Harness를 둔다.

Harness는 확정된 토론 기록에서 **현재 살아 있는 쟁점과 질문을 계산하고 → 이번 턴에 해결할 과제를 정하고 → 어떤 행동을 어떤 대상에 할지 선택한 뒤 → 필요한 Context만 Debater Model에 전달**한다.

### 3.1 State에서 다음 Turn Plan까지

**그림 4. 다음 발언 계획 — 확정된 토론 기록을 실제 생성 조건으로 바꾸는 과정**

~~~mermaid
flowchart TD
    S[Debate State<br/>확정된 주장 · 질문 · 관계 · 입장 변화]
    V[Current Debate View<br/>현재 논점 · 열린 질문 · 진전 상태]
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

`DebateState`에는 다음 턴에도 보존해야 할 사실을 남긴다. 예를 들어 어떤 주장이 나왔는지, 어떤 질문이 열려 있는지, 누가 무엇을 양보·철회·수정했는지가 여기에 들어간다.

반대로 “두 주장이 사실 같은 논점인가?”, “최근 턴이 실제로 진전됐는가?”, “지금 먼저 답해야 할 질문은 무엇인가?”처럼 원본 State에서 계산할 수 있는 정보는 매 턴 다시 계산한다. 이 계산 결과를 바탕으로 `Turn Task`를 만들고, 그 과제를 수행할 수 있는 `Action × Target` 후보 중 하나를 Harness가 선택한다.

Debater Model은 이 전략을 다시 고르는 역할이 아니다. **이미 정해진 Turn Task와 Action × Target을 자연스러운 발언으로 실행하는 역할**이다.

<details>
<summary><strong>Debate State와 파생 계산의 세부 구조 보기</strong></summary>

State의 주요 구조는 다음과 같다.

| 구조 | 기록하는 것 |
|---|---|
| **Proposition** | 실제로 제시된 주장 |
| **Relation** | 주장 사이의 지지·공격·모순·한정 관계 |
| **Question** | 제기된 질문과 `OPEN / RESOLVED` 상태 |
| **Commitment Event** | 주장·양보·철회·수정 같은 입장 변화 |

주장을 수정해도 기존 Proposition을 덮어쓰지 않는다.

~~~text
C12  기존 주장: "모든 경우에 X다"
C19  수정 주장: "조건 Y에서는 X다"
REVISE  C12 → C19
~~~

`build_control_view(state)`는 원본 State를 읽어 `Semantic Facets`, `Question Groups`, `Progress`를 계산한다. `Immediate QUD`는 그 결과와 현재 speaker를 기준으로 지금 먼저 처리할 열린 질문을 고른 결과다.

이 방식은 계산 가능한 값을 별도 state에 중복 저장하지 않고 필요할 때 derive하는 일반적인 state 관리 방식과 같은 방향이다. Redux와 React는 중복·파생 state를 최소화하도록 권장하고, PostgreSQL의 일반 View도 원본 데이터를 별도로 복제하지 않고 조회 시점에 결과를 계산한다.

</details>

### 3.2 Action 선택과 Persona

Harness는 현재 Turn Task에서 가능한 `Action × Target` 후보를 만든 뒤, 이미 해결됐거나 반복 소진됐거나 대상 조건에 맞지 않는 후보를 먼저 제외한다. 남은 후보에서 현재 쟁점과의 관련성, 전략적 우선순위, Persona 선호, 반복 정도 등을 비교해 하나를 고른다.

Persona는 **허용 여부를 결정하는 Hard Constraint가 아니라 선택 가능한 행동 사이의 Soft Preference**다. 따라서 어떤 Persona가 특정 행동을 선호하더라도 이미 해결된 질문이나 소진된 Action × Target을 다시 선택 가능하게 만들지는 못한다.

| Persona | 사용자 표시 | 선호하는 방향 |
|---|---|---|
| Auditor | **근거 검증형** | 근거 요구, 추론 연결 검증, 일관성 확인 |
| Socratic | **전제 탐구형** | 정의·범위 확인, 숨은 전제 탐색, 명시적 입장 요구 |
| Falsifier | **반례 탐색형** | 반례·경계 테스트, 일관성 검사, 직접 반박 |
| Pragmatist | **현실 실용형** | 결과·비용·trade-off 비교, 반박과 방어 |
| Principlist | **원칙 중심형** | 기준·전제·일관성 점검, 원칙 기반 이유 확장 |
| Synthesist | **조정 통합형** | 국소적 양보, 주장 수정, 비교와 핵심 압축 |

<details>
<summary><strong>15개 Strategic Action 전체 보기</strong></summary>

| Action | 역할 |
|---|---|
| `CLARIFY_CLAIM` | 주장 의미·범위·용어를 명확히 하도록 요구 |
| `REQUEST_SUPPORT` | 주장에 대한 근거·이유·정당화를 요구 |
| `CHALLENGE_PREMISE` | 전제의 사실성·필요성·적용 가능성을 문제 삼음 |
| `CHALLENGE_INFERENCE` | 근거에서 결론으로 가는 추론의 충분성을 문제 삼음 |
| `TEST_BOUNDARY` | 반례·경계 사례로 주장 적용 범위를 시험 |
| `CHECK_CONSISTENCY` | 기존 commitment와 현재 주장 사이의 긴장을 확인 |
| `SEEK_COMMITMENT` | 상대가 특정 기준·명제에 명시적으로 입장을 정하도록 요구 |
| `PRESS_UNANSWERED` | 부분 답변/회피 상태의 핵심 질문을 좁혀 다시 요구 |
| `CONCEDE_LOCAL` | 상대의 특정 논점을 인정하되 전체 입장은 유지 |
| `REVISE_CLAIM` | 자신의 기존 주장을 실제로 수정·한정 |
| `REFUTE_CLAIM` | 상대 주장을 이유와 함께 직접 반박 |
| `DEFEND_CLAIM` | 공격받은 자신의 주장을 근거·구분·한정으로 방어 |
| `EXTEND_ARGUMENT` | 현재 입장을 지지하는 새로운 관련 이유를 추가 |
| `WEIGH_COMPARATIVE` | 경쟁하는 두 고려사항을 같은 기준에서 비교 |
| `CRYSTALLIZE` | 새 핵심 근거 없이 이미 나온 핵심 clash를 압축 |

현재 구현의 ranking은 단순 가중합이 아니라 `Target Quality`를 먼저 비교하고, 같은 조건에서는 `Strategic Priority → Persona Preference → Saturation` 순으로 우선순위를 좁히는 tuple ranking이다.

</details>

### 3.3 모델에는 전체 State가 아니라 이번 턴에 필요한 Context를 보낸다

State를 구조화했다고 해서 매 턴 그 전체를 Debater Model에 넣는 것은 아니다. 현재 `Turn Task`, `Action × Target`, QUD가 가리키는 Proposition, 관련 Semantic Facet, 최근에 실제로 참조된 State 항목을 중심으로 이번 턴에서 사용할 Context를 고른다.

즉 흐름은 다음과 같다.

~~~text
전체 Debate State
    ↓ 현재 상황 계산
Turn Task / Action × Target / QUD
    ↓ 관련 항목 선택
이번 턴의 Relevant Context
    ↓
Debater Model
~~~

현재 구현의 `working_reference_ids()`는 이런 기준으로 State reference를 모아 중복을 제거하고 최대 12개를 발언 생성 요청에 포함한다. State Patch 추출도 별도의 graph-aware working set을 사용한다.

따라서 **“전체 Context를 보내지 않는 것”이 State 구조의 유일한 목적은 아니지만, 현재 중요한 정보를 계산할 수 있기 때문에 필요한 Context만 선택해서 보낼 수 있다.**

### 3.4 생성된 발언은 바로 확정되지 않는다

**그림 5. 한 턴 확정 과정 — provisional draft에서 committed turn까지**

~~~mermaid
flowchart TD
    P[Turn Plan<br/>Task · Action · Target · Context]
    G[Debater Model<br/>발언 생성]
    D[Streaming Draft<br/>아직 확정 전]
    V{Compliance}
    R[Repair 또는 Replan]
    S[State Patch<br/>추출 · 검증 · 적용]
    C[Commit<br/>발언 + 새 Debate State 확정]

    P --> G
    G --> D
    D --> V
    V -->|실패| R
    R --> P
    V -->|통과| S
    S -->|성공| C
~~~

화면에 스트리밍되는 Draft는 아직 확정된 발언이 아니다. 먼저 발언이 Assigned Stance, Turn Task, Action × Target, 출력 형식과 reference 규칙을 지키는지 검사한다.

검증에 실패하면 같은 계획을 최소 수정하는 `Targeted Repair`를 시도하고, 필요하면 같은 Turn Task 안에서 Harness가 다른 Action × Target으로 `Replan`한다. Debater Model이 스스로 전략을 다시 고르는 구조는 아니다.

Compliance를 통과한 뒤에는 발언에서 State 변화만 typed Patch로 추출한다. Patch까지 유효하게 적용돼야 발언과 새 State가 함께 확정된다. 끝까지 검증에 실패하면 기존 committed transcript와 Debate State는 그대로 유지된다.

<details>
<summary><strong>State Patch와 검증 세부 항목 보기</strong></summary>

State Patch가 표현할 수 있는 변화:

~~~text
ADD_PROPOSITION
ADD_RELATION
ASK_QUESTION
ANSWER_QUESTION
REVISE_PROPOSITION
CONCEDE_LOCAL
WITHDRAW_PROPOSITION
~~~

Compliance는 단순 pass/fail만 보지 않고 stance reversal, Action 미수행, target 미사용, off-task, 단순 반복, 잘못된 State reference, Final Focus 형식 위반 등을 구분한다.

Browser가 받는 `draft_reset / draft_delta`는 provisional output이며, Patch 적용까지 성공한 뒤 SSE `commit` event로 최종 결과를 보낸다.

</details>

---

## 4. 토론 진행 규칙

토론 단계의 기본 골격은 Public Forum Debate의 Constructive–Crossfire–Rebuttal–Final Focus 요소를 참고하되, 관전형 서비스에 맞게 단순화했다.

| 단계 | 역할 |
|---|---|
| **Opening** | 각 토론자가 입장과 핵심 이유를 제시하고 첫 충돌 지점을 만든다. |
| **Crossfire** | 질문·반례·검증을 통해 상대 주장을 시험하고 실제 쟁점을 좁힌다. |
| **사용자 질문** | 사용자가 원할 때 같은 질문을 A와 B 모두에게 던져 두 입장을 같은 기준에서 비교한다. |
| **Rebuttal** | Crossfire에서 드러난 핵심 충돌을 직접 반박·방어하고 필요하면 국소적으로 양보하거나 주장을 수정한다. |
| **Final Focus** | 새로운 핵심 논점을 늘리지 않고 마지막까지 남길 이유를 짧게 압축한다. |
| **Neutral Summary** | 승자를 정하지 않고 핵심 충돌, 양측의 강한 논점, 합의, 남은 쟁점을 정리한다. |
| **사용자 선택** | Summary를 본 사용자가 A / 모르겠다 / B 중 최종 판단을 직접 선택한다. |

### Crossfire와 Rebuttal은 quota가 아니라 cap이다

정해진 턴 수를 무조건 채우지 않는다. 현재 State에서 더 수행할 가치가 있는 과제가 없으면 Provider를 추가 호출하기 전에 다음 단계로 이동할 수 있다.

Crossfire에서는 새 주장만 계속 추가하기보다, 이미 나온 상대의 핵심 이유를 질문·반례·추론 공격·commitment 요구·국소적 양보·수정으로 실제로 처리하는 것을 우선한다.

### Moderator는 판단하지 않고 서버의 결정을 설명한다

토론을 계속할지, Audience gate를 열지, 다음 Phase로 이동할지는 Server Control Plane이 결정한다. Frontend Moderator는 `moderator_decision`, `turn_task`, phase transition을 바탕으로 이 결정을 사용자에게 보여주는 카드만 만든다.

`public/debate_moderator.js`가 별도 LLM을 호출하거나 독립적으로 토론 전략을 판단하지는 않는다.

---

## 5. 구현 참고

앞 절까지는 프로젝트를 처음 보는 사람이 동작 원리를 이해하기 위한 설명이다. 이 절부터는 코드와 배포 구조를 빠르게 찾기 위한 참고 정보다.

### 5.1 코드 구성

<details>
<summary><strong>주요 디렉터리와 파일 보기</strong></summary>

~~~text
public/
  index.html                 화면 구조와 주요 섹션
  styles.css                 반응형 레이아웃과 상태별 UI
  app.js                     UI state, fetch/SSE, 토론 진행, 오류 처리
  debate_stream.js           Server-Sent Events parser
  debate_moderator.js        서버의 진행 결정을 사회자 카드로 표현
  markdown_renderer.js       Markdown + State reference 렌더링

api/
  _base.py                   공통 HTTP/SSE adapter
  analyze_topic.py           /api/analyze-topic
  context_step.py            /api/context-step
  create_motion.py           /api/create-motion
  debate_step.py             /api/debate-step
  neutral_summary.py         /api/neutral-summary
  health.py                  /api/health

src/web_app/
  contracts.py               Browser ↔ Server Pydantic DTO
  api.py                     API dispatcher와 공통 오류 응답
  live_service.py            실제 AI orchestration
  mock_service.py            Provider 호출 없는 동일 제품 흐름
  session_token.py           signed client-carried session
  service_factory.py         Mock / Live service 선택

src/debate_engine/
  debate_contracts.py        Proposition / Relation / Question / Patch 계약
  debate_control.py          semantic facet, 질문 초점, progress, 이번 턴 과제
  action_policy.py           Action 후보 생성과 선택
  action_pair_state.py       Action × Target 반복/소진 상태
  target_quality.py          target 중요도·행동 가능성 평가
  persona_preferences.py     Persona별 soft preference
  action_execution_contracts.py  15개 Action 의미 계약
  combined_compliance.py     Action / Stance / Task 통합 검증과 retry
  stance_compliance.py       Assigned Stance 유지 검사
  surface_contract.py        출력 형식과 State reference 검사
  state_harness.py           State Patch 추출·검증·적용
~~~

</details>

### 5.2 Frontend와 세션

Debate Arena에서는 provisional draft와 committed transcript를 분리한다. `draft_reset / draft_delta`는 임시 출력이고, 서버의 `commit`을 받은 뒤에만 확정 transcript를 갱신한다. 오래 걸리는 요청은 `AbortController`로 중단할 수 있고 operation sequence로 오래된 응답이 현재 화면을 덮어쓰는 것을 막는다.

Serverless 인스턴스의 메모리를 세션 저장소로 가정하지 않는다. 토론의 연속성은 signed client-carried `engine_token`으로 이어간다.

~~~text
Session + Debate State + Action history + A/B model assignment
    ↓ JSON
    ↓ zlib
    ↓ base64url body
    ↓ HMAC-SHA256 signature
engine_token
~~~

`engine_token`은 **서명된 상태이지 암호화된 상태가 아니다.** 서명은 변조 여부를 확인하지만 내용의 비밀성을 제공하지 않는다.

### 5.3 API

| Endpoint | 주요 역할 |
|---|---|
| `POST /api/analyze-topic` | 주제 성격과 진행 방식 분석 |
| `POST /api/context-step` | 필요한 개인 맥락을 한 질문씩 수집 |
| `POST /api/create-motion` | Motion, side label, Persona pair 결정 |
| `POST /api/debate-step` | planning → generation → validation → State update |
| `POST /api/neutral-summary` | 승자 판정 없는 토론 정리 |
| `/api/health` | live config와 배포 version 확인, Provider 호출 없음 |

Browser-facing DTO는 Pydantic `extra="forbid"` 계약을 사용하며 내부 Patch와 Control View를 일반 Web DTO에 그대로 노출하지 않는다.

### 5.4 기술 스택과 실행

| 영역 | 기술 |
|---|---|
| Frontend | HTML, CSS, Vanilla JavaScript |
| Backend | Python 3.12, Vercel Serverless Functions |
| Schema / Validation | Pydantic |
| Streaming | Server-Sent Events (SSE) |
| AI Integration | OpenAI-compatible Chat Completions / Tool Calling |
| Debater Routing | multi-provider debater pool |
| Session | zlib-compressed + HMAC-SHA256 signed client-carried state |
| Deployment | GitHub + Vercel |

- **배포 URL**: https://a1-3-green.vercel.app
- **GitHub**: https://github.com/hodob/A1-3
- **비밀 환경 변수**: `DEBATER_API_KEY`, `SESSION_SECRET`
- **일반 실행 설정**: `config.json`

로컬에서는 `.env.example`을 참고해 `.env`에 두 secret을 설정한다. Provider 호출 없이 UI 흐름만 확인할 때는 Mock 개발 서버를 사용할 수 있다.

~~~bash
python -m etc.tools.web_dev_server
~~~

Vercel에서는 Project Settings의 Environment Variables에 같은 secret을 등록한다. `public/`은 정적 Frontend로 제공되고 `api/*.py`는 Python Serverless Function으로 실행된다. GitHub 저장소와 연결된 Vercel 프로젝트는 `main` 변경에 따라 배포된다.

---

## 6. References

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
