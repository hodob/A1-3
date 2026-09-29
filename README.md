# 사이 — AI Debate Harness

> 두 AI가 상대의 실제 발언에 반응하며 토론하고, 사용자는 그 공방을 지켜본 뒤 직접 판단하는 관전형 AI 토론 서비스다.

- **배포 URL**: https://a1-3-green.vercel.app
- **GitHub**: https://github.com/hodob/A1-3

**사이**는 사용자가 입력한 주제로 두 AI 토론자가 번갈아 발언하게 한다. 찬성 답변과 반대 답변을 따로 만들어 나란히 놓는 방식과 달리, 각 발언은 상대가 앞서 내놓은 주장·질문·반박·양보·수정을 다음 턴의 판단 재료로 삼는다. 사용자는 토론을 지휘하지 않고 지켜보다가 필요하면 한 번 질문하고, 승패는 마지막에 직접 판단한다.

이 설계의 핵심은 **이번 턴에 무엇을 할지는 Harness가 정하고, 모델은 그것을 문장으로 옮기기만 한다**는 점이다. 이 문서에서는 두 역할을 다음과 같이 구분한다.

- **Harness**: 사이의 서버 코드. 지금까지의 토론을 정리한 **Debate State**를 읽고 이번 턴에 할 일을 정한 뒤, 생성된 발언을 검증한다.
- **Debater Model**: 외부 AI 모델. Harness가 정한 조건에 맞춰 실제 발언 문장을 만든다.

검증을 통과한 발언만 토론 기록과 Debate State에 확정된다.

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

Topic Analyzer는 주제를 "찬반 가능/불가능"으로만 나누지 않는다. 어떤 종류의 논쟁인지, 현실에서 사실관계가 어떤 상태인지, 어떤 방식으로 토론할지, 추가 맥락이 필요한지를 각각 따로 판단한다. 개인적인 사건이라면 필요한 맥락을 한 번에 하나씩 묻고, 사용자가 말하지 않은 사실을 AI가 지어내 채우지 않는다.

Topic Analyzer가 다듬은 논제(Motion)는 토론을 시작하기 전에 사용자가 한 번 수정할 수 있다.

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

사용자는 Opening과 Crossfire를 지켜보다가, 원하면 A와 B에게 같은 질문을 하나 던질 수 있다. 토론이 끝나면 AI가 승자를 판정하지 않는다. 사용자는 Neutral Summary를 읽고 A / 모르겠다 / B 중 하나를 직접 고른다.

단계별 역할과 조기 전환 규칙은 [4. 토론 진행 규칙](#4-토론-진행-규칙)에서 설명한다.

---

## 2. 전체 시스템 구조

시스템은 **화면**, **제품 흐름과 세션**, **토론 제어**, **발언 생성**을 서로 분리한다.

**그림 3. 시스템 경계 — 사이와 외부 AI Provider**

~~~mermaid
flowchart TD
    U[사용자]

    subgraph SAI[사이]
        B[Browser<br/>UI]
        API[Vercel Python API]
        W[Web Service<br/>제품 흐름 · 세션 · Provider 호출]
        H[Debate Harness<br/>State · 계획 · 검증]

        B -->|JSON / SSE| API
        API --> W
        W --> H
        H --> W
    end

    subgraph EXT[외부 AI Provider]
        D[Debater Models<br/>A/B 발언 생성]
        C[Control Model<br/>분석 · 구조화 · 검증 · 요약]
    end

    U --> B
    W <-->|발언 생성| D
    W <-->|구조화된 판단| C
~~~

| 구성 요소 | 역할 |
|---|---|
| **Browser** | 주제 입력, 토론 관전, 사용자 질문, 최종 선택, 확정 전 초안 표시 |
| **Web Service** | 제품 흐름과 세션을 관리하고 Provider 호출을 조율 |
| **Debate Harness** | 현재 토론을 읽어 이번 턴의 과제·Action·Target을 정하고 결과를 검증 |
| **Debater Models** | Harness가 정한 조건에 맞는 실제 발언을 생성 |
| **Control Model** | 주제 분석, State Patch 추출, 의미 검증, Neutral Summary 같은 구조화 작업 |

가장 중요한 경계는 **무엇을 할지 결정하는 부분**과 **실제 문장을 만드는 모델**을 나눴다는 점이다.

---

## 3. 토론이 다음 발언을 만드는 방법

두 모델에게 번갈아 답변만 받는다면 각 모델이 이전 대화만 보고 다음 말을 알아서 정한다. 사이에서는 그 전에 Harness가 확정된 토론 기록에서 **아직 살아 있는 쟁점과 질문을 계산하고 → 이번 턴에 해결할 과제를 정하고 → 어떤 행동을 어떤 대상에 할지 고른 뒤 → 필요한 Context만 Debater Model에 전달**한다. 3.1~3.3은 이 계획 과정을, 3.4는 생성된 발언을 확정하는 과정을 설명한다.

### 3.1 State에서 다음 턴 계획까지

**그림 4. 다음 발언 계획 — 확정된 토론 기록을 생성 조건으로 바꾸는 과정**

~~~mermaid
flowchart TD
    S[Debate State<br/>확정된 주장 · 질문 · 관계 · 입장 변화]
    V[Control View<br/>현재 논점 · 열린 질문 · 진전 상태]
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

`DebateState`에는 다음 턴에도 유지해야 할 사실만 저장한다. 어떤 주장이 나왔는지, 어떤 질문이 열려 있는지, 누가 무엇을 양보·철회·수정했는지가 여기에 해당한다.

반면 "두 주장이 사실상 같은 논점인가?", "최근 턴에서 토론이 실제로 진전됐는가?", "지금 가장 먼저 답해야 할 질문은 무엇인가?"처럼 저장된 State로 계산할 수 있는 정보는 저장하지 않고 매 턴 다시 계산한다. 이 계산 결과를 **Control View**라고 부른다. Harness는 Control View로 `Turn Task`를 만들고, 그 과제를 수행할 수 있는 `Action × Target` 후보 중 하나를 고른다.

Debater Model은 전략을 다시 고르지 않는다. **이미 정해진 Turn Task와 Action × Target을 자연스러운 발언으로 옮기는 역할**만 맡는다.

<details>
<summary><strong>Debate State와 파생 계산의 세부 구조 보기</strong></summary>

State의 주요 구조는 다음과 같다.

| 구조 | 기록하는 것 |
|---|---|
| **Proposition** | 실제로 제시된 주장 |
| **Relation** | 주장 사이의 지지·공격·모순·한정 관계 |
| **Question** | 제기된 질문과 `OPEN / RESOLVED` 상태 |
| **Commitment Event** | 주장·양보·철회·수정 같은 입장 변화 |

주장을 수정해도 기존 Proposition을 덮어쓰지 않고, 새 Proposition과 수정 관계를 함께 남긴다.

~~~text
C12  기존 주장: "모든 경우에 X다"
C19  수정 주장: "조건 Y에서는 X다"
REVISE  C12 → C19
~~~

Control View는 `build_control_view(state)`가 만든다. 이 함수는 State를 읽어 `Semantic Facets`(같은 논점으로 묶인 주장), `Question Groups`, `Progress`를 계산한다. `Immediate QUD`는 이 결과와 현재 발언자를 기준으로 지금 가장 먼저 다룰 열린 질문을 고른 것이다.

계산할 수 있는 값을 따로 저장하지 않으면 원본과 사본이 어긋날 일이 없다. React와 Redux가 중복·파생 state를 줄이라고 권장하는 것, PostgreSQL의 View가 데이터를 복제하지 않고 조회할 때 계산하는 것과 같은 원리다.

</details>

### 3.2 Action 선택과 Persona

Harness는 현재 Turn Task에서 가능한 `Action × Target` 후보를 만든 뒤, 이미 해결됐거나 반복으로 소진됐거나 대상 조건에 맞지 않는 후보를 먼저 제외한다. 남은 후보 중에서 현재 쟁점과의 관련성, 전략적 우선순위, Persona 선호, 반복 정도를 비교해 하나를 고른다.

Persona는 **어떤 행동을 허용할지 정하는 규칙이 아니라, 허용된 행동 중에서 무엇을 더 선호할지 정하는 성향**이다. 그래서 Persona가 특정 행동을 선호하더라도, 이미 해결된 질문이나 소진된 Action × Target을 다시 고르게 만들 수는 없다.

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

### 3.3 모델에는 이번 턴에 필요한 Context만 보낸다

State를 구조화했다고 해서 매 턴 전체 State를 Debater Model에 넣지는 않는다. 다음 항목을 중심으로 이번 턴의 Context를 고른다.

- 현재 `Turn Task`와 `Action × Target`이 가리키는 항목
- **QUD**(Question Under Discussion, 지금 가장 먼저 다룰 열린 질문)가 겨냥하는 주장
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

### 3.4 생성된 발언은 바로 확정되지 않는다

**그림 5. 한 턴의 확정 과정 — 초안에서 확정 발언까지**

~~~mermaid
flowchart TD
    P[Turn Plan<br/>Task · Action · Target · Context]
    G[Debater Model<br/>발언 생성]
    D[Streaming Draft<br/>확정 전 초안]
    V{Compliance 검사}
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

화면에 스트리밍되는 초안은 아직 확정된 발언이 아니다. 먼저 발언이 배정된 입장(Assigned Stance), Turn Task, Action × Target, 출력 형식, State 참조 규칙을 지켰는지 검사한다.

검사에 실패하면 같은 계획을 유지한 채 문제 부분만 고치는 `Targeted Repair`를 시도하고, 그래도 안 되면 Harness가 같은 Turn Task 안에서 다른 Action × Target을 골라 `Replan`한다.

검사를 통과하면 발언에서 State 변화만 타입이 정해진 Patch로 추출한다. Patch까지 정상적으로 적용되어야 발언과 새 State가 함께 확정된다. 끝까지 실패하면 기존 발언 기록과 Debate State는 바뀌지 않는다.

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

토론 단계는 Public Forum Debate의 Constructive–Crossfire–Rebuttal–Final Focus 구성을 참고해, 관전형 서비스에 맞게 단순화했다.

| 단계 | 역할 |
|---|---|
| **Opening** | 각 토론자가 입장과 핵심 이유를 밝히고 첫 충돌 지점을 만든다. |
| **Crossfire** | 질문·반례·검증으로 상대 주장을 시험하며 실제 쟁점을 좁힌다. |
| **사용자 질문** | 사용자가 원하면 A와 B에게 같은 질문을 던져 두 입장을 같은 기준으로 비교한다. |
| **Rebuttal** | Crossfire에서 드러난 핵심 충돌을 직접 반박·방어하고, 필요하면 부분적으로 양보하거나 주장을 수정한다. |
| **Final Focus** | 새 논점을 더하지 않고, 끝까지 남길 이유를 짧게 압축한다. |
| **Neutral Summary** | 승자를 정하지 않고 핵심 충돌, 양측의 강한 논점, 합의한 부분, 남은 쟁점을 정리한다. |
| **사용자 선택** | 사용자가 Summary를 읽고 A / 모르겠다 / B 중 하나를 직접 고른다. |

### 4.1 Crossfire와 Rebuttal의 턴 수는 목표가 아니라 상한이다

정해진 턴 수를 반드시 채우지 않는다. 현재 State에서 더 다룰 가치가 있는 과제가 없으면, Provider를 더 호출하지 않고 다음 단계로 넘어간다.

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

http://127.0.0.1:8765 에 접속한다(`--port`로 변경 가능). 이 서버는 `config.json`의 `web_mode`와 관계없이 항상 Mock 서비스를 사용하므로 API 키가 필요 없고 토큰도 소모하지 않는다.

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
| `debug_mode` | `true`면 토론 진단 로그를 SSE `debug` 이벤트로 보내고, 토론이 끝난 화면에서 JSON으로 내려받을 수 있다. 기본값은 `false`다. |

**환경 변수** — 서버에서만 쓰는 비밀값. Vercel에서는 Project Settings의 Environment Variables에 등록한다. 로컬에서 실제 Provider를 호출하는 `etc/tools/` 진단 도구를 쓸 때는 [.env.example](.env.example)을 복사해 `.env`를 만든다. Mock 개발 서버만 쓸 때는 필요 없다.

| 변수 | 용도 |
|---|---|
| `DEBATER_API_KEY` | Provider API 키 |
| `SESSION_SECRET` | `engine_token` 서명 키 |

`.env`에는 이 두 키만 둘 수 있다. URL·모델·모드 같은 일반 설정을 넣으면 실행 시 오류가 나며 `config.json`으로 옮기라는 안내가 표시된다.

### 5.5 Vercel 배포

- `public/`은 정적 Frontend로 제공되고, `api/*.py`는 Python Serverless Function으로 실행된다.
- 하이픈이 들어간 공개 API 경로(`/api/debate-step` 등)는 `vercel.json`의 rewrite로 해당 Python 파일에 연결된다.
- GitHub 저장소와 연결된 Vercel 프로젝트는 `main` 브랜치가 바뀔 때마다 배포된다.
- 배포 직후에는 `GET /api/health`로 Function과 Live 설정이 정상인지 확인한다. 이 요청은 Provider를 호출하지 않는다.
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
tests/                           Python 회귀 테스트와 tests/js/ JavaScript 테스트
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
