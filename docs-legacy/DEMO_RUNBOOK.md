# Demo Runbook

## 목적

시연용 **150만 tokens reserve**를 보호하면서 AI Debate Harness의 핵심을 짧게 보여준다. 시연 직전에는 전체 benchmark나 Persona 장기 실험을 다시 실행하지 않는다.

## 시연 전

- Vercel Production URL 접속
- `config.json`의 `web_mode=live` 확인
- Vercel 환경 변수에 `DEBATER_API_KEY`, `SESSION_SECRET`이 등록되어 있는지 확인
- Provider 장애 여부만 확인
- 같은 논제로 사전 토론을 여러 번 생성하지 않음

## 추천 시연 주제

`핫도그는 샌드위치인가?`

이 주제는 최신 사실 검색 의존도가 낮고, Socratic × Falsifier 차이와 Crossfire를 보여주기 쉽다.

대안: `탕수육은 소스를 찍어 먹는 것보다 부어 먹는 편이 낫다.`

## 시연 순서

1. Home에서 주제 입력
2. Topic Analyzer가 만든 Motion과 양측 label 확인
3. Opening A / Opening B 진행
4. Crossfire에서 상대 발언을 직접 받아치는 장면 확인
5. 가능하면 **Audience Question** 한 번 사용 — 같은 질문이 양측에 전달되는 것을 설명
6. Rebuttal / Final Focus 진행
7. **Neutral Summary**에서 AI가 승자를 정하지 않는다는 점 설명
8. 마지막 선택은 사용자가 직접 A / 모르겠다 / B 중 선택

## 설명 포인트

- 전체 대본을 한 번에 만드는 것이 아니라 Turn마다 `Debate State → Action → Persona preference → 발언 → Guard → State Update`가 실행됨
- Persona는 캐릭터 연기가 아니라 적법한 Action 사이의 soft preference
- Action Fidelity Guard와 Stance Guard가 발언 확정 전에 동작
- Proposition / Relation / Question을 구조화해 다음 Turn에서 사용
- Provider API Key는 Browser가 아니라 Python Serverless Function의 Environment Variable로만 사용

## 오류 발생 시

- 같은 버튼을 여러 번 연속 클릭하지 않음
- 오류 메시지가 나오면 먼저 Vercel 로그 확인
- 전체 시연을 재실행하기보다 새로고침 후 하나의 짧은 주제로 다시 시작
- Provider 오류가 반복되면 Mock mode 화면과 기존 Live smoke 검증 결과를 사용해 구조를 설명

## 이미 확보된 Provider 근거

실제 gpt-5.4 smoke에서 Topic Analysis, 3개 Debate Turn, Action/Stance compliance, State Patch, Relation/Question extraction, signed session roundtrip, Neutral Summary가 한 세션에서 검증되었다.

따라서 시연 전에는 이를 다시 benchmark할 필요가 없다.
