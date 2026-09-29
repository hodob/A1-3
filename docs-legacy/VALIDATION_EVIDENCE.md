# Validation Evidence

## 현재 상태

`READY_FOR_DEPLOYMENT`

Core Engine 연구/검증 이후 Web MVP를 TDD로 연결했고, 실제 Provider는 마지막 단일 smoke에서만 사용했다.

## Local regression

최종 배포 준비 단계에서 **220개 Python 회귀 테스트가 통과**했다. 아래 명령으로 재현할 수 있다.

```bash
python -m unittest discover -s tests -q
```

추가로 다음 정적 검사를 사용한다.

```bash
python -m compileall -q api src etc/tools
node --check public/app.js
```

## Browser Mock E2E — Provider tokens 0

Playwright 기반 브라우저 확인에서 실제 DOM으로 다음 흐름을 검증했다.

- Topic → Motion
- Opening / Crossfire
- Audience Question
- Rebuttal / Final Focus
- Neutral Summary
- User Choice
- 총 14개 발언 표시
- Browser console error 0
- 모바일 390px 가로 overflow 0

증거 이미지:

- `etc/browser-smoke-desktop.png`
- `etc/browser-smoke-mobile.png`

## Live Provider smoke

2026-09-24, `gpt-5.4` Provider 단일 smoke 결과:

- status: `PASS`
- topic: `핫도그는 샌드위치인가?`
- claim type: `DEFINITION`
- Persona pair: `Socratic × Falsifier`
- Debate turns: 3 (`OPENING A → OPENING B → CROSSFIRE A`)
- Provider calls: 11
- total tokens: 12,653
- propositions: 9
- relations: 7
- questions: 2
- commitment events: 10
- state integrity issues: 0
- compliance failures: 0
- summary contract: PASS

Sanitized 원본 결과: `docs/evidence/live-smoke-once.json`

한 세션에서 다음 Live 경로가 모두 확인됐다.

- Topic Analysis
- Utterance Generation
- Action Fidelity + Stance Compliance
- State Patch
- Relation Extraction
- Question Extraction
- Signed Session Roundtrip
- Neutral Summary

Relation extraction은 Turn 1에서 `4 Proposition + 3 Relation`, Turn 2에서 `4 Proposition + 4 Relation`을 생성했고 bounded repair는 발생하지 않았다.

## 해석 범위

이 smoke는 실제 Provider와 전체 Harness의 연결 여부를 확인하는 integration diagnostic이다. 3 Turn 결과를 Persona 품질이나 토론 재미의 통계적 성능 수치로 해석하지 않는다.

장기 Persona/quality 실험은 별도 기존 로그와 fixture로 수행했으며, MVP 배포 전에는 시연용 토큰을 보호하기 위해 반복하지 않는다.
