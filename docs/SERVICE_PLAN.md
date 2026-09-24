# AI Debate Harness — 서비스 기획서

## 1. 서비스 개요

**Clash Lab**은 사용자가 입력한 주제를 두 AI 토론자가 순차적으로 토론하는 과정을 관전하는 웹 서비스다. 전체 찬반 대본을 한 번에 생성하지 않고, 각 Turn마다 상대의 직전 발언과 구조화된 Debate State를 바탕으로 다음 행동을 선택한다.

서비스 가치의 우선순위는 다음과 같다.

1. AI끼리 실제로 주고받는 토론을 보는 재미
2. 한 주제를 여러 관점에서 탐색
3. 최종 판단은 AI가 아니라 사용자가 직접 수행

## 2. 목적

일반적인 AI 답변은 한 모델이 결론을 정리해 주는 형태가 많다. 이 서비스는 서로 다른 추론 성향을 가진 두 AI가 같은 주제를 놓고 반박·질문·양보·수정을 반복하도록 만들어, 사용자가 **논쟁이 전개되는 과정 자체**를 볼 수 있게 한다.

AI가 승자를 결정하지 않고 마지막에는 사용자가 `A / 아직 모르겠다 / B` 중 직접 선택한다.

## 3. 타겟 사용자

- AI Agent / Multi-agent 서비스의 동작을 직접 보고 싶은 사용자
- 한 주제의 상반된 관점을 짧게 비교하고 싶은 사용자
- 진지한 정책·가치 주제뿐 아니라 부먹/찍먹 같은 가벼운 논쟁을 재미있게 보고 싶은 사용자
- AI Harness, State, Persona, Serverless 구조를 학습하거나 시연하려는 사용자

## 4. 페이지 / 섹션 구성

MVP는 메뉴로 이동 가능한 세 개의 section을 사용한다.

### Home

- 토론 주제 입력
- 빈값/길이 검증
- Topic Analyzer 실행
- Motion Preview 및 1회 수정

### Debate

- 필요한 경우 Context Intake
- Context completeness 표시
- Opening → Crossfire → **Audience Question** → Rebuttal → Final Focus
- **Neutral Summary**
- 사용자 최종 선택

### How It Works

- Debate State
- Action Selector
- Persona preference
- Guard
- Browser → Python API → AI Provider → Response 흐름 설명

## 5. 핵심 AI 기능

### 입력

기본 입력은 사용자가 작성한 텍스트 주제다.

예:

- `탕수육 부먹 vs 찍먹`
- `핫도그는 샌드위치인가?`
- `대학 수업은 출석을 의무화해야 하는가?`

개인 사건처럼 추가 맥락이 필요한 경우에는 AI가 한 번에 하나씩 Context 질문을 제공하며 사용자가 객관식, `잘 모르겠다`, 직접 입력으로 답한다.

### 처리

1. Topic Analyzer가 claim type / epistemic status / treatment mode / interaction state를 구조화한다.
2. Motion을 토론 가능한 명제로 정규화한다.
3. Topic에 맞는 Persona pair를 정한다.
4. 각 Turn에서 현재 Debate State로 가능한 Action × Target을 계산한다.
5. Persona는 적법한 후보들 사이의 soft preference로만 작동한다.
6. LLM이 발언을 생성한다.
7. Action Fidelity / Stance Guard를 통과한 발언만 State에 반영한다.
8. Proposition / Relation / Question / Commitment Event를 다음 Turn에 사용한다.

### 출력

사용자에게는 내부 JSON이나 Action ID가 아니라 다음을 보여준다.

- 정규화된 Motion과 양측 label
- 양측의 순차 발언
- 현재 Debate phase
- Audience Question 양측 답변
- 핵심 clash / 양측 강점 / 합의 / 미해결 쟁점으로 구성된 Neutral Summary
- 사용자 선택 UI

## 6. 사용자에게 제공하는 가치

단순히 `찬성 이유 3개 / 반대 이유 3개`를 나열하는 것이 아니라, **상대가 실제로 한 말 때문에 다음 Turn이 달라지는 토론**을 제공한다.

Persona도 말투 캐릭터가 아니라 `근거를 요구하는가`, `정의를 묻는가`, `반례를 찾는가`, `비용을 비교하는가` 같은 행동 선호 차이로 구현한다.

## 7. 실패 처리 기준

### 빈 입력

`토론할 주제를 입력해주세요.` 안내를 표시하고 API를 호출하지 않는다.

### 긴 입력

Frontend와 Pydantic request contract에서 길이를 제한한다.

### Loading

`주제를 분석하고 있습니다...`, `토론자가 생각하고 있습니다...`처럼 현재 상태를 표시하고 중복 요청 버튼을 막는다.

### API / Provider 오류

Raw stack trace나 Provider payload를 화면에 노출하지 않고 `응답을 생성하지 못했습니다. 다시 시도해주세요.`와 같은 안정적인 메시지를 표시한다.

### 지연 / Timeout

Browser에서 AbortController timeout 경로를 두고 지연 안내를 표시한다.

### Guard 실패

Action Fidelity 또는 Stance 검사 후 발언을 안전하게 확정하지 못하면 State를 변경하지 않고 `SAFE_FAILURE`로 반환한다.

## 8. 기술 스택

- Frontend: HTML / CSS / Vanilla JavaScript
- Backend: Python Vercel Serverless Functions
- Validation: Pydantic
- AI Provider: OpenAI-compatible Chat Completions / Tool Calling
- Deployment: GitHub + Vercel
- State: signed client-carried session token, 별도 DB 없음

## 9. MVP 범위

포함:

- Text Topic
- Context Intake
- Motion
- Two-agent Debate
- Audience Question
- Neutral Summary
- User Choice
- Responsive UI
- Error / Loading UX

제외:

- 계정
- DB / History
- PDF / 이미지 / 음성
- 웹 검색
- 3명 이상 Agent
- AI Winner Judge

## 10. 개인정보·사실성 원칙

- 사용자가 주지 않은 개인 사건의 사실을 만들어내지 않는다.
- 외부 웹 검색이 없으므로 최신 통계·정책·사건을 강하게 단정하지 않는다.
- 가짜 연구·통계·인용을 생성해 한쪽 입장을 강화하지 않는다.
- 개인 사건 입력은 관찰/전달된 주장/사용자 해석/미확인 정보로 구분할 수 있게 한다.

## 11. 시연 시나리오

추천 주제는 `핫도그는 샌드위치인가?`다. 최신 사실 의존도가 낮고 Socratic과 Falsifier의 추론 차이, Crossfire 질문, State 업데이트를 설명하기 쉽다.
