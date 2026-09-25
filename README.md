# AI Debate Harness — Clash Lab

사용자가 던진 주제를 두 AI 토론자가 **상대의 실제 이전 발언과 구조화된 Debate State를 보며 순차적으로 토론**하는 Vanilla Web + Python Serverless MVP다.

단순 찬반 대본 생성이 아니라 `State → Action → Persona preference → Utterance → Guard → State Update` Harness를 구현하는 것이 핵심이다. 최종 승자는 AI가 정하지 않고 사용자가 직접 선택한다.

## 주요 기능

- Topic Analyzer: FACT / DEFINITION / POLICY / PERSONAL_DISPUTE 등 분류
- 필요 시 Context Intake 및 completeness 표시
- Motion Normalization + 사용자 1회 수정
- Opening → Crossfire → Audience Question → Rebuttal → Final Focus
- Proposition / Relation / Question / Commitment 기반 Debate State
- Rule-assisted Action Selector + Action–Target Pair State
- 6개 사전 정의 Persona의 soft action preference
- Action Fidelity Guard + Semantic Stance Guard
- Neutral Summary + 사용자 선택
- Mock mode / Live mode 분리


## 기술 스택

- Frontend: HTML / CSS / Vanilla JavaScript
- Backend: Python 3.12 / Vercel Serverless Functions
- Validation: Pydantic
- AI: OpenAI-compatible Chat Completions + Tool Calling (`gpt-5.4` 검증)
- Deployment: GitHub + Vercel

## 배포 URL

- Vercel: https://a1-3-green.vercel.app
- GitHub: https://github.com/hodob/A1-3

## 프로젝트 구조

```text
public/                 Vanilla HTML / CSS / JavaScript
api/                    Vercel Python Serverless handlers
src/debate_engine/      검증된 Debate Engine
src/web_app/            Web DTO, Mock/Live service, signed session
tests/                 회귀·웹·배포 계약 테스트
etc/fixtures/           검증 fixture
etc/tools/              진단/개발 도구
docs/                  서비스/아키텍처/배포/검증 문서
```

## 로컬 테스트

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

일반 Python:

```bash
python -m unittest discover -s tests -q
python -m compileall -q api src etc/tools
node --check public/app.js
```

## Mock 웹 실행 — Provider tokens 0

로컬 개발 서버는 배포 설정이 `live`여도 항상 `mock` 서비스를 사용한다.

```bash
python -m etc.tools.web_dev_server
```

Topic → Motion → Debate → Audience Question → Neutral Summary → User Choice 전체 UX를 외부 모델 호출 없이 확인할 수 있다.

## 설정 분리

비밀값과 일반 실행 설정을 분리한다.

`config.json` — Git에 커밋하는 비밀이 아닌 설정:

```json
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
  }
}
```

`.env` / Vercel 환경 변수(Environment Variables) — 서버 전용 secret만 저장:

- `DEBATER_API_KEY`
- `SESSION_SECRET`

로컬 비밀값 형식은 `.env.example`을 참고한다. `.env`에 URL/model/mode를 넣지 않는다.

`provider.model`은 주제 파악, 의미 검사, State 추출, 요약을 담당한다. `debater_models` 중 서로 다른 회사의 모델 두 개를 토론 시작 시 뽑아 A/B 발언 생성에 배정하고 서명된 세션에 고정한다. 현재 배포 설정은 `live`다. 로컬 `web_dev_server`는 이 설정과 무관하게 Provider 호출 없이 Mock 서비스를 사용한다.

모든 live Provider 요청은 streaming으로 전송한다. 토론 발언의 텍스트 청크는 웹에 `작성 중 · 아직 확정되지 않았어요`로 표시한다. Action·Stance·State 검증 뒤에만 확정 발언과 세션을 전달하며, 재생성이나 실패 시 임시 문장은 폐기한다. Tool Calling 청크는 서버에서 조립한 뒤 로컬 검증한다.

배포 화면 하단의 짧은 버전은 Vercel의 `VERCEL_GIT_COMMIT_SHA`가 제공될 때만 표시한다. 이 System Environment Variable이 비활성화된 환경에서는 버전을 숨긴다.


## 배포 전 0-token Preflight

```bash
python -m etc.tools.preflight
```

전체 unittest, Python compile, JavaScript syntax, Vercel 설정, frontend secret scan을 한 번에 검사하며 Provider 호출은 하지 않는다.

## Vercel 배포

- Python runtime: `pyproject.toml`에서 3.12 계열 고정
- Python Functions: `api/*.py`
- Static frontend: `public/`
- Public hyphen API path는 `vercel.json` rewrite로 Python 파일에 연결
- Provider key는 Browser로 전달하지 않음

상세 절차: `docs/DEPLOYMENT_CHECKLIST.md`

배포 직후에는 Provider를 쓰기 전에 `/api/health`를 확인한다. 이 endpoint는 Python Function과 Live 환경 설정만 검증하며 Provider 호출은 0회다.

## 검증 상태

로컬 회귀, Mock browser E2E, 실제 `gpt-5.4` Provider smoke까지 완료했다. Live smoke는 11 calls / 12,653 tokens로 Topic Analysis, 3 Debate Turns, Action/Stance Guard, State Patch, Relation/Question Extraction, signed session, Neutral Summary를 한 번에 검증했다.

상세 근거: `docs/VALIDATION_EVIDENCE.md`

## 시연

시연 전에 장기 benchmark를 다시 실행하지 않는다. 시연용 Provider token reserve를 보호하며, 실제 서비스 흐름 중심으로 보여준다.

시연 순서: `docs/DEMO_RUNBOOK.md`

## 제출 문서

- 서비스 기획: `docs/SERVICE_PLAN.md`
- Web/AI 아키텍처: `docs/WEB_MVP_ARCHITECTURE.md`
- 검증 근거: `docs/VALIDATION_EVIDENCE.md`
- 테스트 감사: `docs/TEST_AUDIT.md`
- 배포 체크리스트: `docs/DEPLOYMENT_CHECKLIST.md`
- 제출 체크리스트: `docs/SUBMISSION_CHECKLIST.md`
