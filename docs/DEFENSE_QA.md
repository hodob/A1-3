# 평가 질문 대비 설명 노트

## 1. 왜 html / css / js / api 구조를 나눴나?

`HTML`은 서비스의 의미 구조와 입력/결과 영역, `CSS`는 반응형 레이아웃과 시각 표현, `JavaScript`는 상태와 이벤트 및 `fetch` 통신을 담당한다. `api/`의 Python은 Browser에 노출하면 안 되는 Provider Key를 사용하고 AI Harness를 실행한다.

역할을 나누면 UI 수정이 Debate Engine을 깨뜨리지 않고, Backend도 Browser 없이 fixture로 테스트할 수 있다.

## 2. Loading / 성공 / 실패는 어떻게 처리했나?

`public/app.js`의 공통 API 함수가 요청마다 AbortController를 만들고 JSON 응답을 확인한다. 요청 전에는 `주제를 분석하고 있습니다...`, `토론자가 생각하고 있습니다...` 같은 Loading 상태를 보여주며 중복 버튼을 막는다. 성공하면 `payload.data`를 화면에 반영하고, 실패하면 stable error message만 보여준다.

## 3. Serverless Function 입력 검증과 응답 포맷은?

HTTP adapter가 body 크기와 JSON 형식을 먼저 검사한다. 그 다음 `src/web_app/contracts.py`의 Pydantic model이 field, enum, 길이 등을 검사한다.

성공은 `{ok: true, data: ...}`, 실패는 `{ok: false, error: {code, message}}` 형태로 통일했다.

## 4. fetch 요청은 어떻게 왕복하나?

사용자 입력 → JavaScript `fetch('/api/...')` → Vercel rewrite → Python handler → Web DTO validation → Debate Engine / AI Provider → validated response → JSON → JavaScript DOM update 순서다.

## 5. 환경 변수를 왜 쓰나?

API Key를 JavaScript에 넣으면 배포 파일과 Browser DevTools에서 노출된다. 그래서 `DEBATER_API_KEY`는 Vercel Environment Variable로만 저장하고 Python에서 읽는다. 환경마다 Provider URL이나 model을 코드 수정 없이 바꿀 수도 있다.

## 6. AI 기능을 왜 이 서비스에 넣었나? Prompt는 어떻게 구성했나?

이 서비스의 핵심은 정답 생성이 아니라 **상대 발언에 따라 다음 행동이 달라지는 토론**이다. 그래서 Topic Analyzer, Turn generation, compliance, State extraction을 각각 목적이 다른 Prompt/structured contract로 분리했다.

발언 Prompt에는 Global quality rule, Persona, Assigned Stance, 현재 phase, 관련 Debate State, 상대 발언과 선택 Action을 넣는다. Persona는 사실성이나 Protocol보다 우선하지 않는다.

## 7. 배포 후 문제가 생기면 어떤 순서로 본다?

Browser Console → Network response → Vercel Function log → Environment Variable → Provider 상태 순서로 확인한다. 재현 가능한 경우 전체 토론을 다시 돌리지 않고 실패 Turn fixture를 만들어 regression test부터 추가한다. 실제 개발에서도 State ID 타입 오류, Stance reversal, Action Fidelity 문제를 이런 순서로 fixture화해 수정했다.

## 8. 응답 지연이 잦다면?

`응답 지연` 원인을 먼저 계층별로 측정한다. 현재 한 Turn은 generation / semantic compliance / state extraction 호출이 주요 비용이다.

개선 옵션:

- 관련 State subset만 Prompt에 전달
- 서로 결합 가능한 validator 호출 유지
- 이미 해결된 Action×Target pair를 Rule Engine에서 미리 제거
- 짧은 발언 길이 유지
- Provider latency 로그 확인
- 필요한 경우 streaming UX 검토
- 품질 저하 없이 가능한 호출 통합 검토

단순히 timeout만 계속 늘리는 방식은 비용과 UX를 동시에 악화시킬 수 있다.

## 9. AI 기능을 2개로 늘린다면?

Frontend에서 각각의 UI 상태를 분리하고 `/api/...` endpoint 또는 service method를 추가한다. 공통 request/response DTO, Provider Adapter, Error Contract는 재사용한다. AI 로직을 handler에 직접 복사하지 않고 `src/`에 domain service로 추가한다.

## 10. API 키 유출 시 즉시 무엇을 하나?

`API 키 유출`이 확인되면 먼저 Provider에서 기존 key를 revoke/rotate한다. Vercel Environment Variable을 새 key로 변경하고 재배포한다. Git history나 screenshot에 노출됐다면 파일만 지우는 것으로 끝내지 않고 이미 유출된 key는 반드시 폐기한다.

재발 방지:

- `.env` Git 제외
- Frontend secret scan
- Environment Variable만 사용
- 로그에 Authorization/provider payload 저장 금지

## 11. 프론트 프레임워크가 허용된다면?

React/Vue 같은 `프레임워크`를 쓰면 Debate Turn, Context Intake, Summary 같은 복잡한 UI 상태를 component/state 단위로 관리하기 쉬워진다. 반면 build chain과 dependency가 늘고 과제의 HTML/CSS/JavaScript 동작 원리를 직접 보여주기는 어려워진다.

현재 구조에서는 Backend API contract가 이미 분리되어 있으므로 Frontend만 교체할 수 있고 Python Debate Engine은 대부분 유지할 수 있다.

## 12. 로컬과 배포 환경의 차이는?

로컬에서는 기본 Mock mode로 토큰 없이 개발한다. Production은 Vercel Environment Variable로 Live mode를 켜고 Serverless Function이 Provider를 호출한다. 배포 환경에는 function duration, CDN routing, secret 설정 같은 추가 운영 조건이 있으므로 `vercel.json`과 배포 로그를 함께 확인해야 한다.
