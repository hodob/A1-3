# Web MVP Architecture

## 1. 폴더를 나눈 이유

```text
public/            Browser에서 실행되는 HTML / CSS / JavaScript
api/               Vercel Python Serverless Function 진입점
src/debate_engine/ Debate State, Action, Persona, Guard 등 검증된 Core
src/web_app/       Web DTO, Mock/Live orchestration, signed session
tests/             TDD 회귀 테스트
etc/               fixture, 진단 도구, 개발 증빙
docs/              서비스/설계/배포 문서
```

Frontend와 Backend를 분리한 이유는 Browser에 API Key와 내부 Debate State 로직을 노출하지 않으면서, UI와 AI Harness를 독립적으로 테스트하기 위해서다.

## 2. HTML / CSS / JavaScript 역할

### HTML

`public/index.html`은 Home / Debate / How It Works의 의미 구조, 입력 폼, 버튼, 결과 영역을 정의한다.

### CSS

`public/styles.css`은 레이아웃, 두 토론자의 시각적 구분, 모바일 breakpoint, Loading/Error 상태의 표현을 담당한다.

### JavaScript

`public/app.js`은 사용자 입력을 읽고 `fetch('/api/...')` 요청으로 바꾸며, Loading / Success / Failure 상태와 Debate phase 전환을 처리한다.

## 3. fetch → Python → AI → Response

대표적인 Debate Step 흐름:

```text
사용자가 '다음 발언' 클릭
        ↓
public/app.js
fetch('/api/debate-step', JSON)
        ↓
vercel.json rewrite
        ↓
api/debate_step.py
        ↓
src/web_app/api.py
Pydantic request validation
        ↓
LiveDebateWebService
        ↓
Debate State
→ Semantic Facet / Question Group
→ Progress / Common Ground
→ Turn Task (이번 턴의 해결 과제)
→ eligible Action × Target
→ Pair State / Target Quality
→ Persona soft preference
        ↓
AI Provider 발언 생성
        ↓
Action Fidelity + Stance Compliance + Turn Task Fidelity
        ↓
State Patch / Relation / Question / semantic progress extraction
        ↓
Moderator: continue / weigh / phase change
        ↓
Pydantic response DTO
        ↓
JSON Response
        ↓
public/app.js가 DOM에 발언 추가
```

## 4. API 구성

Public endpoint:

- `/api/analyze-topic`
- `/api/context-step`
- `/api/create-motion`
- `/api/debate-step`
- `/api/neutral-summary`

`vercel.json`에서 hyphenated public URL을 `api/*.py` Python 파일로 rewrite한다.

## 5. 입력 검증과 응답 포맷

Web Request/Response는 `src/web_app/contracts.py`의 Pydantic model로 검증한다. `extra='forbid'`를 사용해 예상하지 않은 field가 조용히 들어오는 것을 막는다.

성공 응답:

```json
{"ok": true, "data": {}}
```

실패 응답:

```json
{"ok": false, "error": {"code": "INVALID_INPUT", "message": "..."}}
```

주요 error code:

- `INVALID_INPUT`
- `PAYLOAD_TOO_LARGE`
- `SAFE_FAILURE`
- `CONFIG_ERROR`
- `TIMEOUT`
- `API_ERROR`

## 6. Debate State 경계

Browser에는 public `DebateSession`과 `engine_token`이 전달된다.

`engine_token`은 서버의 `SESSION_SECRET`으로 HMAC 서명된 압축 payload다. 다음 요청에서 서버가 서명을 검증하고 내부 authoritative Debate State와 Action history를 복원한다.

Browser가 public `next_index` 같은 값을 임의로 바꾸더라도 이미 signed token이 있는 세션에서는 그것이 authoritative engine state를 덮어쓰지 않는다.

Raw `DebateState`는 발화 사실의 source of truth이고, `src/debate_engine/debate_control.py`가 semantic facet, question group, progress event, common ground를 Derived Control State로 계산한다. 새 C/Q ID가 생겼다는 사실만으로 토론 진전으로 보지 않는다. 고정 schedule은 최대 cap이며, 고가치 Turn Task가 없으면 추가 Provider 호출 전에 phase를 넘길 수 있다.

## 7. 설정과 Secret을 분리하는 이유

Browser 코드에는 Provider 설정이나 비밀값을 하드코딩하지 않는다.

### `config.json` — 비밀이 아닌 서버 실행 설정

- `provider.url`
- `provider.model`
- `provider.debater_models` (회사와 모델 ID의 배열)
- `web_mode`

이 값들은 Git에 커밋할 수 있지만 Frontend가 직접 Provider를 호출하는 데 사용하지 않는다. Python Serverless Function이 읽는다.

### `.env` / Vercel Environment Variables — 서버 전용 secret

- `DEBATER_API_KEY`
- `SESSION_SECRET`

특히 API Key를 JavaScript에 넣으면 Browser DevTools와 배포된 파일에서 누구나 읽을 수 있다. 따라서 비밀값은 환경 변수로 두고 Python Serverless Function에서만 사용한다.

## 8. Mock / Live 분리

### Mock

`config.json`의 `web_mode=mock`

- Provider 호출 0
- UI / phase / error flow 개발
- 브라우저 E2E에 사용

### Live

`config.json`의 `web_mode=live`

- 실제 Provider 사용
- `config.json`의 URL, coordinator model, debater model array + 환경 변수의 API key/session secret이 필요
- A/B 발언 생성은 서로 다른 회사의 모델을 한 번 뽑아 서명된 세션에 고정한다. 주제 파악, 의미 검사, State 추출, 중립 요약은 `provider.model`을 쓴다.
- 모든 Provider 요청은 SSE streaming으로 받고, 서버에서 텍스트·Tool Calling arguments·usage를 조립한다. 토론 발언은 `draft_reset`/`draft_delta`로 화면에 임시 표시하고, Action·Stance·State 검증이 끝난 뒤 `commit`으로 확정한다. 재생성 시 임시 발언을 교체하고 실패 시 `error`로 폐기한다. 기존 JSON API 응답 계약도 유지한다.
- Mock 및 fixture 테스트를 먼저 통과한 뒤 최소 smoke만 수행

## 9. Loading / Success / Failure

### Loading

요청 시작 시 status 문구를 갱신하고 요청 중 버튼을 disable한다.

### Success

API response DTO를 받은 뒤 Motion, Context 질문, Debate Turn, Summary를 해당 DOM 영역에 반영한다.

### Failure

Frontend는 raw Python stack trace나 Provider JSON을 표시하지 않는다. 안정적인 사용자 메시지만 노출한다.

Browser AbortController timeout은 긴 Debate Step을 고려해 설정되며 Serverless Function 쪽에도 최대 실행 시간이 설정돼 있다.

## 10. 배포 구조

```text
Browser
   ↓ same-origin HTTPS
Vercel CDN / Static public/
   ↓ /api/*
Vercel Python Function
   ↓ Authorization: Bearer ... (server only)
AI Provider
```

Vercel은 `pyproject.toml`의 Python 3.12 runtime 조건과 `requirements.txt`/dependency metadata를 사용한다.

## 11. 배포 후 문제 진단 순서

1. Browser DevTools Console에서 JavaScript/CSP 오류 확인
2. Network에서 `/api/...` HTTP status와 JSON error code 확인
3. Vercel Function log 확인
4. Environment Variable 누락/오타 확인
5. Provider endpoint / timeout 확인
6. 로컬 fixture로 동일 실패를 재현
7. 수정 후 regression test
8. 재배포

Provider 오류가 의심된다고 바로 전체 Debate를 반복 실행하지 않는다. 토큰 비용을 줄이기 위해 실패 Turn이나 fixture를 먼저 사용한다.
