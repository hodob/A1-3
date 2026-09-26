# 사이 — AI Debate Harness

> **두 AI의 찬반 답변을 따로 생성해 나란히 보여주는 서비스가 아니라, 상대의 실제 이전 발언과 구조화된 토론 상태 때문에 다음 발언이 달라지도록 만든 관전형 AI 토론 시스템입니다.**

**사이**는 사용자가 주제를 입력하면 두 AI 토론자가 순차적으로 발언하고, 서로의 주장·질문·반박·양보·수정을 다음 턴의 판단 재료로 사용하는 웹 서비스입니다. 사용자는 토론을 직접 지휘하기보다 공방을 지켜보고, 필요하면 한 번 질문한 뒤 마지막 판단을 직접 내립니다.

### 30초 요약

- **사용자 경험**: 주제 입력 → 필요 시 맥락 확인 → Motion 확인 → AI 토론 관전 → 선택적 질문 → 중립 요약 → 사용자 판단
- **핵심 차이**: 다음 발언은 단순한 대화 이어쓰기가 아니라 `Debate State → 현재 과제 → Action × Target → Persona → 생성 → 검증 → State Update` 순서로 결정
- **AI 역할 분리**: A/B 토론자는 실제 발언을 만들고, 별도의 control/coordinator 경로가 주제 분석·구조화·검증·요약을 담당
- **판정 원칙**: AI가 승자나 점수를 정하지 않으며, 최종 선택은 사용자에게 남김

## 목차

1. [사용자 흐름](#1-사용자-흐름)
2. [시스템 경계와 배포 구조](#2-시스템-경계와-배포-구조)
3. [코드 구조](#3-코드-구조)
4. [한 턴이 결정되는 과정](#4-한-턴이-결정되는-과정)
5. [Debate State와 반복 제어](#5-debate-state와-반복-제어)
6. [Action과 Persona](#6-action과-persona)
7. [실제 `/api/debate-step` 실행 흐름](#7-실제-apidebate-step-실행-흐름)
8. [Prompt Architecture와 검증](#8-prompt-architecture와-검증)
9. [Debate Protocol과 Moderator](#9-debate-protocol과-moderator)
10. [Frontend Runtime](#10-frontend-runtime)
11. [API 계약](#11-api-계약)
12. [기술 스택과 실행·배포](#12-기술-스택과-실행배포)
13. [References](#references)

---

## 1. 사용자 흐름

### 1.1 토론을 시작하기 전

처음 입력된 문장을 바로 찬반 프롬프트에 넣지 않습니다. 먼저 Topic Analyzer가 **이 주제가 어떤 종류인지, 사실 확인이 먼저 필요한지, 개인 맥락이 필요한지, 어떤 강도로 다뤄야 하는지**를 구조화합니다.

**그림 1. 주제를 토론 가능한 상태로 준비하는 흐름**

```mermaid
flowchart TD
    A[사용자 주제 입력] -->|분석 요청| B[Topic Analyzer]
    B --> C{Interaction State}

    C -->|READY| M[Motion 준비]
    C -->|CONFIRMATION_REQUIRED| N[확인 이유를 함께 표시]
    N --> M

    C -->|CONTEXT_REQUIRED| D[Context 질문 1개]
    D -->|사용자 답변| E[Context Step]
    E --> F{debate_ready?}
    F -->|아니오| D
    F -->|예| G[Context Summary]
    G --> M

    C -->|INFORMATIONAL_FIRST| I[사실·설명이 먼저 필요한 입력 안내]
    I -->|주제 수정| A

    M --> H[Motion 확인 / 최대 1회 수정]
```

Topic Analyzer는 현재 구현에서 다음 축을 구분합니다.

| 축 | 무엇을 판단하는가 |
|---|---|
| Claim Type | FACT, DEFINITION, CAUSE, VALUE, POLICY, COMPARISON, INTERPRETATION, PERSONAL_DISPUTE 등 |
| Epistemic Status | 사실 우세인지, 실제로 논쟁 가능한지, 아직 불명확한지 |
| Treatment Mode | 자연스러운 토론 / 가벼운 토론 / 재구성된 토론 |
| Interaction State | 바로 진행 / 확인 필요 / 추가 맥락 필요 / 먼저 정보 설명 필요 |
| Truth Mode | 현실 세계 사실 / 가정된 반사실 / 수사적·놀이형 논쟁 |
| Tone | SERIOUS / PLAYFUL 표현 강도 |

개인 사건처럼 사용자만 알고 있는 정보가 필요한 경우에는 한 번에 하나씩 질문합니다. 답변은 Context Summary에서 `직접 본 일`, `전해 들은 이야기`, `내 해석`, `모르는 부분`처럼 provenance 성격별로 정리됩니다. 사용자가 주지 않은 사건 사실을 AI가 임의로 채우지 않는 것이 기본 규칙입니다.

### 1.2 토론이 시작된 뒤

**그림 2. 토론 프로토콜 — 탐색에서 요약까지**

```mermaid
flowchart TD
    A[Opening A / B] -->|첫 주장과 이유 형성| B[Crossfire]
    B -->|쟁점 탐색·검증| C{Audience Question}
    C -->|질문함| D[A와 B가 같은 질문에 답변]
    C -->|건너뜀| E[Rebuttal A / B]
    D --> E
    E -->|남은 충돌 직접 처리| F[Final Focus A / B]
    F -->|새 핵심 근거 없이 압축| G[Neutral Summary]
    G -->|판정 재료 제공| H[사용자 선택<br/>A / 아직 모르겠다 / B]
```

Crossfire와 Rebuttal의 턴 수는 반드시 채워야 하는 quota가 아니라 **최대 cap**입니다. 현재 상태에서 더 수행할 가치가 있는 과제가 없으면 Provider를 한 번 더 부르기 전에 다음 단계로 넘어갈 수 있습니다.

---

## 2. 시스템 경계와 배포 구조

**그림 3. 브라우저·Serverless·Debate Harness·AI Provider의 책임 경계**

```mermaid
flowchart TD
    U[사용자] -->|주제·답변·질문·선택| B[Browser<br/>HTML / CSS / Vanilla JS]

    B -->|JSON fetch / SSE| API[Vercel Python<br/>Serverless Functions]
    API -->|Pydantic DTO| W[Web Service Layer<br/>세션·제품 흐름·오류 처리]

    W -->|턴 계획 요청| H[Debate Harness<br/>State / Control / Action / Guard]
    H -->|A/B 발언 생성| D[Debater Models<br/>multi-provider pool]

    W -->|주제 분석·구조화·검증·요약| C[Control / Coordinator Model]

    W -->|서명·복원| T[(engine_token)]
    W -->|commit 결과 / SSE event| API
    API -->|화면 갱신| B
```

브라우저에는 사용자 입력, UI 상태, transcript와 **서명된 `engine_token`**이 있습니다. `engine_token` 안에는 internal Debate State와 Action history 같은 서버 제어 데이터도 압축되어 들어가지만, 서버의 HMAC 검증을 통과해야만 authoritative state로 인정됩니다.

즉 이 토큰은 **암호화가 아니라 무결성 보호**입니다. 브라우저가 토큰을 보관하더라도 내부 상태를 임의로 바꾸어 다음 턴의 authoritative state로 사용할 수는 없습니다. API Key와 Action 선택 로직은 서버에만 존재합니다.

토론 시작 시 `multi-provider debater pool`에서 서로 다른 두 토론자 모델을 A/B에 배정하고, 그 배정은 한 토론 동안 signed session에 고정됩니다. 주제 분석·구조화 출력·State Patch 추출·Compliance 검사·Neutral Summary는 control/coordinator 경로가 담당합니다.

---

## 3. 코드 구조

```text
public/                 Browser UI
api/                    Vercel Python Serverless 진입점
src/web_app/            Web DTO, 세션, Mock/Live orchestration
src/debate_engine/      토론 상태·행동 선택·검증 Core
config.json             비밀이 아닌 실행 설정
.env / Vercel Env       서버 전용 secret
docs/                   설계·계약·검증 문서
```

### 주요 책임

| 영역 | 역할 |
|---|---|
| `public/` | 화면 state, `fetch`, SSE draft 표시, 오류 UX, Markdown·reference 렌더링 |
| `api/` | HTTP/SSE adapter와 공개 API endpoint |
| `src/web_app/` | Browser-facing DTO, 제품 흐름, signed session, Provider orchestration |
| `src/debate_engine/` | Debate State, Control State, Action 선택, Persona preference, Guard, State Patch |
| `config.json` | provider URL, coordinator model, debater model pool, debug mode 등 비밀이 아닌 설정 |
| 환경 변수 | `DEBATER_API_KEY`, `SESSION_SECRET` 같은 server-only secret |

<details>
<summary><strong>주요 파일별 역할 보기</strong></summary>

```text
public/
  index.html                 화면 구조와 3개 주요 섹션
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
  session_token.py           zlib + HMAC signed session
  service_factory.py         Mock / Live service 선택

src/debate_engine/
  debate_contracts.py        Proposition / Relation / Question / Patch 계약
  debate_control.py          semantic facet, 질문 초점, progress, 이번 턴 과제
  action_policy.py           Action 후보 생성과 선택
  action_pair_state.py       Action × Target 반복/소진 상태
  target_quality.py          target 중요도·행동 가능성 평가
  persona_preferences.py     Persona별 soft preference
  action_execution_contracts.py  15개 Action의 의미 계약
  combined_compliance.py     Action / Stance / Task 통합 검증과 retry
  stance_compliance.py       Assigned Stance 유지 검사
  surface_contract.py        출력 형식과 State reference 검사
  state_harness.py           State Patch 추출·검증·적용
```

</details>

이 분리의 핵심은 **LLM이 문장을 생성하는 책임과 Harness가 토론을 제어하는 책임을 분리하는 것**입니다.

---

## 4. 한 턴이 결정되는 과정

다음 발언은 단순히 transcript 뒤에 이어 쓰는 방식으로 정하지 않습니다.

**그림 4. 한 턴의 제어 파이프라인 — 위에서 아래로 후보가 좁아짐**

```mermaid
flowchart TD
    P[Protocol / Phase<br/>지금 할 수 있는 범위] --> Q[현재 가장 먼저 해결할 질문·과제]
    S[Debate State] --> Q

    Q --> E[가능한 Action × Target 생성]
    S --> E

    E --> F[반복·해결·소진된 후보 제거]
    F --> T[중요한 Target 우선]
    T --> U[Strategic Utility]
    U --> R[Persona soft preference]
    R --> A[Action × Target 확정]

    A --> G[발언 생성]
    G --> V[Surface / Action / Stance / Task 검증]

    V -->|통과| C[State Patch 적용 후 commit]
    V -->|실패| X[Targeted Repair 또는 Replan]
    X --> G
```

각 층은 서로 다른 질문에 답합니다.

| 층 | 판단 |
|---|---|
| Protocol / Phase | 지금 단계에서 무엇을 할 수 있는가? |
| Debate State | 지금까지 무엇이 실제로 주장·질문·양보·수정되었는가? |
| 현재 질문·과제 | 이번 발언이 가장 먼저 해결해야 할 것은 무엇인가? |
| Action × Target | 어떤 논점에 어떤 방식으로 대응할 것인가? |
| Persona | 적법한 후보 중 어떤 행동을 상대적으로 선호하는가? |
| Guard | 생성된 문장이 실제로 계획한 행동·입장·과제를 수행했는가? |
| State Patch | 확정된 발언에서 다음 턴에 필요한 변화를 무엇으로 남길 것인가? |

이 구조에서 **Persona는 후보를 만드는 권한이 없습니다.** 이미 해결됐거나 막힌 행동을 되살릴 수도 없습니다. 먼저 적법한 후보를 만든 뒤 마지막 선택에만 soft preference로 영향을 줍니다.

---

## 5. Debate State와 반복 제어

Debate State는 전체 대화를 다시 저장하기 위한 요약문이 아니라 **다음 행동을 결정하기 위한 구조화 상태**입니다.

**그림 5. 실제 기록과 그 위에서 계산되는 제어 상태**

```mermaid
flowchart TD
    subgraph RAW[Authoritative Debate State]
        P[Propositions]
        R[Relations]
        Q[Questions]
        C[Commitment Events]
        E[Event / Response History]
    end

    RAW -->|매 턴 계산| D[Derived Control State]

    D --> F[같은 논점을 묶는<br/>Semantic Facets]
    D --> G[현재 질문 초점<br/>Question Groups / Immediate QUD]
    D --> H[의미 있는 진전 여부<br/>Progress]
    D --> I[Action × Target 상태]
    D --> J[Target Quality]
```

### 실제로 저장하는 핵심 Entity

- **Proposition**: 주장·근거·반례 등의 기본 명제
- **Relation**: `SUPPORTS`, `ATTACKS`, `CONTRADICTS`, `QUALIFIES`
- **Question**: 별도 Entity로 저장하고 `OPEN / RESOLVED`를 관리
- **Commitment Event**: `ASSERT`, `CONCEDE`, `WITHDRAW`, `REVISE`

기존 Proposition text를 수정해서 과거를 지우지 않습니다. 주장을 바꾸면 새 Proposition과 `REVISE` event를 추가합니다.

### 같은 말을 새 ID로 반복하는 문제

새 Proposition이 생길 때 단순히 “새 C ID가 생겼다”를 진전으로 보지 않습니다. 기존 논점과의 의미 관계를 함께 판정해 같은 논지는 하나의 **semantic facet**으로 묶습니다. 따라서 표현만 바꾼 새 Proposition으로 반복 제한을 우회하기 어렵게 합니다.

### 현재 가장 먼저 해결할 질문

질문을 오래된 순서대로 전부 다시 꺼내지 않습니다. 현재 쟁점에서 **가장 먼저 해결해야 하는 질문 초점**을 정하고, 같은 의미의 연속 질문은 하나의 Question Group으로 묶을 수 있습니다. 최신 핵심 질문이 해결된 뒤 과거의 unrelated OPEN 질문을 자동으로 되살리지 않습니다.

이 구조는 담화를 현재의 Question Under Discussion 중심으로 보는 연구와, 하나의 복합 질문 턴을 의미 단위로 묶는 접근을 참고했습니다 (Roberts, 2012; Prakken, 2005; D’Agostino et al., 2024).

<details>
<summary><strong>의미 관계와 이번 턴 과제의 전체 목록 보기</strong></summary>

새 Proposition의 의미 관계:

```text
NEW_REASON
SAME_POINT
REFINEMENT
NEW_COUNTEREXAMPLE
QUALIFICATION
RELATED_DISTINCT
```

이번 발언이 해야 할 일 (`Turn Task`):

| 내부 이름 | 의미 |
|---|---|
| `INTRODUCE_UNCOVERED_FACET` | 아직 다뤄지지 않은 핵심 측면 제시 |
| `ANSWER_OPEN_QUESTION` | 현재 열린 핵심 질문에 직접 답변 |
| `ADDRESS_AUDIENCE` | 관객 질문에 직접 답변 |
| `ADDRESS_COUNTEREXAMPLE` | 최근 반례를 처리 |
| `TEST_UNRESOLVED_REASON` | 아직 해결되지 않은 이유를 검증 |
| `WEIGH_COMPETING_REASONS` | 경쟁하는 이유를 같은 기준에서 비교 |
| `NARROW_DISAGREEMENT` | 동의/불일치 범위를 좁힘 |
| `CRYSTALLIZE` | 이미 나온 핵심 충돌을 압축 |
| `NO_VALUABLE_MOVE` | 현재 단계에서 추가 발언 가치가 낮음 |

</details>

> README에서는 구조 이해에 필요한 State만 설명합니다. 실제 코드의 provenance, source turn, working-set metadata, debug bookkeeping 등 순수 구현 세부 필드는 길이와 가독성을 위해 생략했습니다.

---

## 6. Action과 Persona

### 6.1 Action은 “다음에 할 말”이 아니라 의미 계약

현재 Runtime에는 15개의 Strategic Action이 있습니다. 각 Action은 단순 이름이 아니라 **어떤 종류의 target을 받아야 하는지, 발언에서 어떤 의미 효과가 실제로 나타나야 하는지, 무엇을 실패로 볼지**가 정의된 실행 계약입니다.

선택 순서는 개념적으로 다음과 같습니다.

```text
Hard Eligibility
→ Action × Target Pair Filter
→ Target Quality
→ Strategic Utility
→ Persona Preference
→ Repetition / Saturation
```

Action×Target pair는 `AVAILABLE / OPEN / PARTIALLY_RESOLVED / RESOLVED / EXHAUSTED / BLOCKED` 상태를 가질 수 있습니다. 이미 충분히 답한 질문, 철회·수정된 주장, 반복 소진된 pair는 다음 후보에서 제외됩니다.

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

</details>

### 6.2 Persona는 캐릭터가 아니라 행동 선호 정책

Persona는 고정된 세계관이나 역할극 캐릭터가 아닙니다. 현재 구현에서는 **적법한 Action 후보들 사이의 안정적인 soft preference**입니다. Stance는 별도의 session assignment이므로 같은 Persona도 다른 토론에서는 반대 입장을 맡을 수 있습니다.

Persona 연구에서 role-playing persona, personality prompting, role과 expressive style의 효과를 구분해서 볼 필요가 있다는 점을 참고했습니다. 이를 바탕으로 현재 구현에서는 Big Five나 MBTI 자체를 runtime 제어 변수로 쓰지 않고, 토론 행동과 직접 연결되는 Persona → Action preference만 사용합니다 (Tseng et al., 2024; Jiang et al., 2024; Nagao et al., 2026).

| Persona | 사용자 표시 | 무엇을 더 자주 시도하는가 |
|---|---|---|
| Auditor | **근거 검증형** | 근거 요구, 추론 연결 검증, 일관성 확인 |
| Socratic | **전제 탐구형** | 정의·범위 확인, 숨은 전제 탐색, 명시적 입장 요구 |
| Falsifier | **반례 탐색형** | 반례·경계 테스트, 일관성 검사, 직접 반박 |
| Pragmatist | **현실 실용형** | 결과·비용·trade-off 비교, 반박과 방어 |
| Principlist | **원칙 중심형** | 기준·전제·일관성 점검, 원칙 기반 이유 확장 |
| Synthesist | **조정 통합형** | 국소적 양보, 주장 수정, 비교와 핵심 압축 |

Topic Analyzer의 claim type에 따라 기능적으로 다른 Persona pair를 고릅니다. 예를 들어 정의형 주제에서는 정의·전제를 파고드는 성향과 반례를 찾는 성향을, 정책·가치형 주제에서는 원칙과 실제 결과를 보는 성향을 조합합니다.

---

## 7. 실제 `/api/debate-step` 실행 흐름

개념적인 Action 선택과 실제 HTTP/SSE 실행을 분리해서 보면 한 턴이 어떻게 확정되는지 더 명확합니다.

**그림 6. 브라우저 요청부터 확정 발언까지의 실제 call sequence**

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as /api/debate-step
    participant W as Web Service
    participant H as Debate Harness
    participant D as Debater Model
    participant G as Compliance Guard
    participant S as State Patch

    B->>A: signed session + NEXT
    A->>W: DebateStepRequest
    W->>W: engine_token 검증 / State 복원

    W->>H: 현재 State와 phase 전달
    H-->>W: 이번 과제 + Action × Target

    W->>D: stance + persona + task + target + context
    D-->>W: streaming text delta
    W-->>A: draft_reset / draft_delta
    A-->>B: SSE로 임시 문장 표시

    W->>G: Surface + Action + Stance + Task 검사

    alt 검증 실패
        G-->>W: typed failure
        W->>D: targeted repair 또는 replan
    else 검증 통과
        G-->>W: committed utterance
        W->>S: 확정 발언 + 관련 State working set
        S-->>W: typed Patch
        W->>W: Patch 검증 / 적용 / 새 token 서명
        W-->>A: committed response
        A-->>B: commit event
    end
```

화면에 streaming되는 문장은 **확정 전 draft**입니다. `draft_reset`과 `draft_delta`는 사용자가 기다리는 동안 생성 과정을 보여주기 위한 provisional UI이고, Guard와 State Patch까지 통과해야 transcript에 commit됩니다.

### State Patch

확정된 발언 뒤에는 LLM이 전체 State를 다시 작성하지 않고 필요한 변화만 typed Patch로 추출합니다.

```text
ADD_PROPOSITION
ADD_RELATION
ASK_QUESTION
ANSWER_QUESTION
REVISE_PROPOSITION
CONCEDE_LOCAL
WITHDRAW_PROPOSITION
```

Patch는 Pydantic schema, entity reference, ownership 규칙을 통과해야 합니다. 기존 Proposition text는 덮어쓰지 않으며 revision은 새 Proposition과 event로 표현합니다.

### 관련 State만 전달

State가 계속 커져도 전체 graph를 매번 프롬프트에 넣지 않습니다. 현재 Action target, 질문 초점, semantic facet의 대표/현재 node, 명시적으로 참조한 State, 최근 양측 Proposition을 중심으로 working set을 구성합니다. Patch용 Proposition working set은 현재 구현에서 최대 10개입니다.

긴 context에서는 필요한 정보의 위치와 양이 모델의 활용 성능에 영향을 줄 수 있다는 결과를 참고해, 전체 누적 State보다 현재 과제와 연결된 node를 우선하는 방식을 사용합니다 (Liu et al., 2024).

---

## 8. Prompt Architecture와 검증

프롬프트는 하나의 긴 “역할 설정”으로 만들지 않고, **변하지 않는 규칙과 이번 턴에만 필요한 데이터를 분리**합니다.

**그림 7. 발언 생성 프롬프트의 정보 우선순위**

```mermaid
flowchart TD
    A[Global Hard Rules<br/>사실성·입장 경계·사용자 입력은 data] --> B[Grounding<br/>fact anchor / context]
    B --> C[Assignment<br/>stance / persona / phase]
    C --> D[Phase Instruction<br/>Opening / Crossfire / Rebuttal / Final Focus]
    D --> E[이번 턴 계약<br/>과제 + Action + Target]
    E --> F[허용된 State References]
    F --> G[Recent Transcript]
    G --> H[Surface Style / Format]
    H --> I[Draft]
    I --> J{Validation}
    J -->|통과| K[Commit]
    J -->|실패 코드| L[Targeted Repair / Replan]
    L --> I
```

Speech prompt는 실제 코드에서 `identity`, `hard_rules`, `grounding`, `assignment`, `phase_instruction`, `surface_style`, `surface_format`처럼 구획을 나눕니다. Motion, Context, transcript, Audience Question은 instruction과 섞이지 않도록 data 영역으로 전달합니다.

전역 품질 규칙은 Persona보다 우선합니다.

- 사용자가 제공하지 않은 개인 사건의 사실을 만들지 않음
- 존재하지 않는 통계·연구·인용을 만들어 한쪽을 강화하지 않음
- 상대가 실제로 하지 않은 주장을 공격하지 않음
- 실제 질문에는 먼저 답함
- 유효한 반론은 국소적으로 인정할 수 있음
- 세부 주장은 수정할 수 있지만 Assigned Stance 전체를 반대로 뒤집지 않음

### 실패 유형에 맞춘 Repair

검증은 단순한 `pass / fail`이 아니라 실패 종류를 구분합니다. 예를 들어 stance reversal, Action 미수행, target 미사용, off-task, 단순 재진술, 허용되지 않은 State reference, Final Focus 형식 위반 등이 서로 다른 failure code가 됩니다.

첫 retry는 이전 draft에서 **무엇을 유지하고 무엇만 바꿔야 하는지**를 알려주는 targeted repair입니다. 같은 전략으로 고치기 어려운 실패가 반복되면 Action/Target 자체를 다시 계획할 수 있습니다. 최대 시도 안에 검증을 통과하지 못하면 발언과 State를 확정하지 않습니다.

이 구조는 실패 위치와 허용 가능한 수정 방향을 명시한 structured feedback이 agent repair에 도움을 줄 수 있다는 연구를 참고했습니다 (Ray & Goyal, 2026).

---

## 9. Debate Protocol과 Moderator

### Crossfire

Crossfire는 질문을 정해진 순서대로 번갈아 읽는 단계가 아닙니다. 현재 Debate State에서 살아 있는 논점을 골라 **질문, 반례, 추론 공격, commitment 요구, 국소적 양보, 주장 수정** 등으로 상태를 실제로 변화시키는 구간입니다.

관전 재미도 별도의 농담 생성 모듈을 붙이는 방식보다 **상대의 방금 한 발언을 이용한 callback, 반례, 양보, 수정, 새로운 충돌**에서 나오도록 설계했습니다. PLAYFUL 주제에서는 가벼운 비유나 논증에서 나온 유머를 허용하지만 상대 인격에 대한 공격은 허용하지 않습니다.

### Moderator는 별도 AI가 아님

현재 구현에서는 진행 결정과 화면 표현을 분리합니다.

```text
Server Control Plane
  └─ 지금 더 말할 가치가 있는가?
  └─ Audience gate를 열 것인가?
  └─ Crossfire / Rebuttal을 다음 phase로 넘길 것인가?

Frontend Moderator
  └─ 위 결정을 사용자가 이해할 수 있는 사회자 카드로 표현
```

즉 `public/debate_moderator.js`가 새로운 LLM 판단을 추가하는 것이 아닙니다. 서버가 전달한 `MOVE_PHASE`, `AUDIENCE_QUD_OPENED`, `WEIGH_COMPETING_REASONS` 같은 상태를 결정적인 문구로 바꿔 보여줍니다.

### Audience Question과 Final Focus

Audience Question은 일반 agenda보다 우선하는 임시 질문 초점으로 취급하고 A와 B가 같은 질문에 차례로 답합니다. Final Focus에서는 새 핵심 근거를 추가하지 않고 이미 나온 이유 중 가장 중요한 것을 짧게 압축합니다.

### Neutral Summary

토론이 끝나면 별도의 중립 요약이 다음 항목만 정리합니다.

- 핵심 충돌
- A의 강한 논점
- B의 강한 논점
- 함께 인정한 부분
- 남은 질문

승자, 점수, 정답은 정하지 않습니다.

---

## 10. Frontend Runtime

Frontend는 API 결과를 단순 출력하는 역할 외에도 **긴 AI 작업 중 사용자가 무엇을 보고 있는지**를 관리합니다.

**그림 8. 사용자가 보는 화면 상태의 lifecycle**

```mermaid
stateDiagram-v2
    [*] --> Topic
    Topic --> Context: 추가 맥락 필요
    Topic --> Motion: 바로 토론 가능
    Context --> Context: 다음 질문 필요
    Context --> Motion: debate_ready
    Motion --> Debate: 토론 시작
    Debate --> Debate: draft → validation → commit
    Debate --> Audience: Crossfire 종료
    Audience --> Debate: 질문 또는 건너뛰기
    Debate --> Summary: COMPLETE
    Summary --> Choice
    Choice --> Done
    Done --> Topic: 다른 주제로 시작
```

주요 Frontend 책임:

- 화면 state와 session 관리
- 중복 요청 차단과 operation sequence 기반 stale response 방지
- `AbortController`를 이용한 지연/timeout 처리
- SSE의 `draft_reset → draft_delta → commit/error` lifecycle 처리
- provisional draft와 committed transcript 분리
- Markdown sanitize/render
- State reference를 사람이 읽을 수 있는 발언 링크로 변환
- 서버의 진행 결정을 deterministic moderator card로 표현
- 모바일/데스크톱 반응형 UI
- raw stack trace나 Provider payload 대신 안정적인 오류 메시지 표시

토론자가 기존 State 항목을 가리킬 때는 `[[C24]]`, `[[Q3]]` 같은 내부 marker를 사용할 수 있습니다. 서버는 확정 후 이를 `StateReference` metadata로 바꾸고, Frontend는 사용자에게 **A/B · 발언 번호** 형태의 링크로 보여줍니다. 허용된 working set 밖의 ID는 local validation에서 거부됩니다.

---

## 11. API 계약

| Endpoint | 주요 입력 | 역할 | 주요 출력 |
|---|---|---|---|
| `POST /api/analyze-topic` | 사용자 topic | 주제 성격과 진행 방식 분석 | `TopicAnalysis` |
| `POST /api/context-step` | topic + 이전 답변 | 필요한 개인 맥락을 한 질문씩 수집 | 다음 질문 또는 `context_summary` |
| `POST /api/create-motion` | analysis + context + optional edit | Motion, side label, Persona pair 결정 | `MotionResponse` |
| `POST /api/debate-step` | signed session + command | planning → generation → validation → State update | SSE draft + committed response |
| `POST /api/neutral-summary` | motion + committed transcript | 승자 판정 없는 정리 | clash / 양측 논점 / 합의 / 남은 질문 |
| `/api/health` | 없음 | Serverless와 live config 확인, Provider 호출 없음 | ready / mode / version |

Browser-facing DTO는 Pydantic `extra="forbid"` 계약을 사용합니다. 내부 Patch, Action 후보, Control State는 일반 Web DTO에 그대로 노출하지 않습니다.

> API 표와 State 설명은 시스템 구조를 이해하는 데 필요한 항목만 보여줍니다. 전체 Pydantic field와 validation bookkeeping은 문서 길이와 가독성을 위해 생략했습니다.

---

## 12. 기술 스택과 실행·배포

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

### 실행·배포 정보

- **배포 URL**: https://a1-3-green.vercel.app
- **GitHub**: https://github.com/hodob/A1-3
- **비밀 환경 변수**: `DEBATER_API_KEY`, `SESSION_SECRET`
- **일반 실행 설정**: `config.json`

로컬에서는 `.env.example`을 참고해 `.env`에 두 secret을 설정합니다. Provider 호출 없이 UI 흐름만 확인할 때는 Mock 개발 서버를 사용할 수 있습니다.

```bash
python -m etc.tools.web_dev_server
```

Vercel에서는 Project Settings의 Environment Variables에 같은 secret을 등록합니다. `public/`은 정적 Frontend로 제공되고 `api/*.py`는 Python Serverless Function으로 실행됩니다. GitHub 저장소와 연결된 Vercel 프로젝트는 `main` 변경에 따라 배포됩니다.

---

## References

- Tseng, Yu-Min et al. (2024). *Two Tales of Persona in LLMs: A Survey of Role-Playing and Personalization*. Findings of EMNLP 2024. https://aclanthology.org/2024.findings-emnlp.969/
- Jiang, Hang et al. (2024). *PersonaLLM: Investigating the Ability of Large Language Models to Express Personality Traits*. Findings of NAACL 2024. https://aclanthology.org/2024.findings-naacl.229/
- Nagao, Moe et al. (2026). *Personality, Role, and Expressive Style in Large Language Models: An Interactionist Analysis*. arXiv preprint. https://arxiv.org/abs/2605.28037
- Roberts, Craige (2012). *Information Structure in Discourse: Towards an Integrated Formal Theory of Pragmatics*. Semantics & Pragmatics, 5. https://doi.org/10.3765/sp.5.6
- Prakken, Henry (2005). *Coherence and Flexibility in Dialogue Games for Argumentation*. Journal of Logic and Computation. https://doi.org/10.1093/logcom/exi046
- D’Agostino, Giulia, Chris Reed, and Daniele Puccinelli (2024). *Segmentation of Complex Question Turns for Argument Mining: A Corpus-based Study in the Financial Domain*. LREC-COLING 2024. https://aclanthology.org/2024.lrec-main.1265/
- Liu, Nelson F. et al. (2024). *Lost in the Middle: How Language Models Use Long Contexts*. Transactions of the Association for Computational Linguistics, 12, 157–173. https://aclanthology.org/2024.tacl-1.9/
- Ray, Jaideep & Ankit Goyal (2026). *Structured Feedback Improves Repair in an LLM Agent Loop*. arXiv preprint. https://arxiv.org/abs/2607.14167
