# Test Audit

최종 설정 분리 및 배포 준비 단계에서 테스트 코드를 다시 감사했다.

## 현재 상태

- Python unittest: **276개 통과**
- `src + api` line coverage: **이번 검증에서 미실측**
- Provider 추가 호출: **0**
- `api/*` HTTP adapter: 테스트 후 100% line coverage
- `provider_adapter.py`: 정상/실패 structured output 경계 보강 후 100%
- `runtime_config.py`: config/.env 분리 및 오류 경계 포함 97%

테스트 개수에는 문서/배포 계약 테스트도 포함되므로, 276이라는 숫자 자체를 모델 품질이나 토론 품질의 통계적 정확도로 해석하지 않는다.

## 이번 감사에서 보강한 부분

### 1. `.env` / `config.json` 분리

- `config.json`: `web_mode`, provider URL, model만 허용
- `.env`: `DEBATER_API_KEY`, `SESSION_SECRET`만 허용
- `.env`에 URL/model/mode를 넣으면 CLI config loader가 거부
- 환경 변수의 옛 `DEBATER_URL`, `DEBATE_MODEL`, `DEBATE_WEB_MODE`가 `config.json`을 덮어쓰지 못함
- secret field가 `config.json`에 들어가면 schema validation 실패

### 2. 실제 HTTP adapter

기존에는 Vercel handler의 파일 존재와 rewrite 문자열 위주였다. 다음을 실제 메서드 호출로 추가 검증했다.

- 빈 body → 400
- malformed/non-object JSON → 400
- body size 초과 → 413
- 정상 POST → 정확한 route/body dispatch
- response JSON/Cache-Control
- OPTIONS → 204
- health GET → Provider 호출 없이 dispatch

### 3. Provider adapter

- Tool Calling 정상 parse
- forced tool choice capability
- JSON schema transport fallback
- 잘못된/multiple tool call 거부
- malformed tool arguments
- local Pydantic validation error
- structured output transport가 전혀 없을 때 명시적 실패

### 4. Vercel rewrite

단순 문자열 존재 검사를 줄이고 `vercel.json`을 JSON으로 파싱하여 public route → destination의 정확한 매핑을 비교한다.

## 상대적으로 낮은 coverage의 이유

`debate_harness.py`, `state_harness.py`의 CLI/network orchestration 일부는 전체 line coverage가 낮다. 이 경로는 과거 실험/진단 CLI를 포함하고 있으며 Production Web 요청의 핵심 경로는 `src/web_app/*`, Provider adapter, typed state contracts, Action/Guard 계층에서 별도로 테스트된다.

실제 Provider 연결은 unit test에서 반복 호출하지 않고 기존 단일 Live smoke 결과로 보완한다.

## 여전히 외부에서 확인해야 하는 것

로컬 테스트가 대신할 수 없는 항목:

1. 실제 Vercel 배포 성공
2. Vercel Production Environment Variables 적용
3. 배포 URL의 `/api/health`
4. 실제 배포 환경에서 최소 Live UI 연결 확인
5. 실제 사용자 관전 피로도/재미 평가

이 항목들은 기존 AI 엔진 회귀 테스트를 다시 돌릴 이유가 아니다.


## 반복 토론 Control State 회귀 보강

- SAME_POINT가 새 C ID를 받아도 같은 semantic facet으로 묶임
- 같은 Action이 새 C ID로 repetition guard를 우회하지 못함
- resolved 질문의 paraphrase가 새 OPEN Q로 재생성되지 않음
- NEW_COUNTEREXAMPLE은 실제 progress로 유지
- 두 턴 연속 rephrase-only이면 probing보다 WEIGH task로 전환
- common ground/conceded facet을 다시 공격 대상으로 올리지 않음
- Final Focus는 열린 Q ID를 노출하거나 답변 의무로 재개하지 않음
- Audience Question 원문이 실제 generation prompt에 전달됨
- task_fidelity=REPHRASES_ONLY이면 기존 Action/Stance가 정상이어도 commit되지 않음
