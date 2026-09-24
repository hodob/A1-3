# Vercel Deployment Checklist

이 문서는 실제 Provider 토큰을 낭비하지 않고 배포 오류를 최소화하기 위한 최종 체크리스트다.

## 1. 배포 전 로컬 확인

- `python -m etc.tools.preflight`
- `config.json`과 `.env`의 역할이 분리되어 있는지 확인
- `public/`에 API Key, Bearer token이 하드코딩되지 않았는지 확인

## 2. `config.json` — 비밀이 아닌 실행 설정

Git에 커밋하는 `config.json`에는 다음만 둔다.

- `web_mode`: 로컬 안전 기본값은 `mock`, Production 배포 전 `live`로 변경
- `provider.url`: Provider의 `/v1` 또는 `/chat/completions` 주소
- `provider.model`: `gpt-5.4`

API Key나 `SESSION_SECRET`은 `config.json`에 넣지 않는다.

## 3. Vercel Environment Variables — secret만

Production 환경에는 다음 두 값만 등록한다.

- `DEBATER_API_KEY` — 서버 전용 secret
- `SESSION_SECRET` — 충분히 긴 임의 문자열. Provider key와 다른 값을 사용

`.env`는 로컬 secret 파일이며 Git에 커밋하지 않는다. `.env.example`에는 placeholder만 둔다.

## 4. Runtime

`pyproject.toml`에서 Python 3.12 계열을 고정한다. Python Serverless Function은 `api/*.py`이며 `vercel.json`에서 최대 실행 시간을 설정한다.

## 5. 최초 배포 확인 — Provider 호출 전

1. Production에 올릴 커밋의 `config.json`에서 `web_mode=live`인지 확인
2. `/`가 열리는지 확인
3. `/styles.css`, `/app.js`, `/robots.txt`가 200인지 확인
4. `/api/health`에서 `status=ready`, `mode=live`, `provider_call=false`인지 확인한다. 이 endpoint는 Provider를 호출하지 않는다.
5. 브라우저 콘솔에 JS/CSP 오류가 없는지 확인
6. `DEBATER_API_KEY`, `SESSION_SECRET` 두 환경 변수가 등록되었는지 Vercel Dashboard에서 확인
7. 그 다음에만 UI의 정상 POST 흐름으로 최소 Live 검증을 진행한다.

## 6. Live 확인

로컬 Provider 통합 smoke는 이미 완료되어 있다. 배포 환경에서는 전체 품질 실험을 반복하지 않는다.

최초 Production 검증은 한 개 논제로 시작하고 Topic 분석 → Motion 생성 → 첫 발언까지 확인한 뒤 문제가 없으면 필요한 만큼만 계속한다. 오류가 나면 반복 실행하기 전에 Vercel Function 로그를 먼저 확인한다.

## 7. Secret / 비용 보호

- `.env`는 Git/Vercel 업로드 대상에서 제외
- `DEBATER_API_KEY`와 `SESSION_SECRET`은 `public/`, `config.json`에 넣지 않음
- 배포 URL은 검색 엔진 색인을 막기 위해 `X-Robots-Tag`와 `robots.txt`를 사용
- 시연 전 불필요한 Live 재실험 금지
- 오류가 재현되면 전체 토론보다 해당 Turn/fixture를 우선 사용

## 8. 제출 전

- Vercel URL
- GitHub 저장소 URL
- README
- 서비스 기획서 `docs/SERVICE_PLAN.md`
- 구조 설명 `docs/WEB_MVP_ARCHITECTURE.md`
- 화면 캡처
- AI 코딩 도구 사용 근거

을 한 번에 확인한다.
