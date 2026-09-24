# Single Live Smoke Plan

실제 Provider 실측은 여러 번 나누지 않고 **한 번의 짧은 세션**에서 최대한 많은 계층을 확인한다.

## Reserve policy

- Demo reserve: **1,500,000 tokens — 개발 실측에서 사용하지 않음**
- 이 smoke의 계획 상한: **20,000 tokens**
- 기본 실행: 핫도그 정의 논제, **3 turns** (Opening A → Opening B → Crossfire A)
- 전체 토론, Persona 장기 실험, 4-topic 재실행은 하지 않는다.

## 한 번에 확인하는 항목

1. `topic_analysis` structured tool calling
2. Motion/persona pairing
3. A/B 양측 실제 발언 생성
4. Crossfire 첫 반응
5. combined Action Fidelity + Stance Compliance
6. State Patch local validation
7. Proposition / Relation extraction
8. Crossfire가 질문을 만들면 Question extraction guard
9. signed `engine_token` round-trip과 State 참조 무결성
10. Neutral Summary structured contract
11. 호출 목적별 provider call 수와 input/output/total token usage

Question이나 Relation이 실제 발언 특성상 생성되지 않을 수 있으므로 관찰 여부는 coverage로 별도 기록한다. 구조 무결성 실패, compliance 실패, signed-session 복원 실패는 smoke 실패로 본다.

## 실행 전

```bash
python -m unittest discover -s tests -q
python -m etc.tools.live_smoke_once
```

두 명령은 Provider를 호출하지 않는다.

## 실제 1회 실행

`config.json`에 Provider URL/model을 두고 `.env` 또는 운영 환경 변수에는 `DEBATER_API_KEY`, `SESSION_SECRET`만 넣은 뒤 명시적으로 `--execute`를 붙인다.

```bash
python -m etc.tools.live_smoke_once --execute
```

기본 결과 파일:

`etc/runs/live-smoke-once.json`

API key와 session secret은 결과에 기록하지 않는다.
