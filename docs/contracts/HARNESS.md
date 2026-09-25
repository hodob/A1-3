# 실측 하네스: Persona 파일럿

설계서 v1.0의 Persona Qualification을 위한 **UI 없는 초기 실행기**다. 한 실행에서 같은 모델이 두 Persona와 두 입장을 맡는다. `--crossover`를 쓰면 Persona는 유지하고 입장만 바꿔 다시 실행한다. 원문과 사용량을 저장하며, Persona 유지 여부는 사람이 원문을 검토해야 한다.

## 설정

설정은 비밀값과 일반 설정을 분리한다.

- `config.json`: `provider.url`, `provider.model`, `web_mode`처럼 Git에 커밋 가능한 비밀이 아닌 설정
- `.env`: `DEBATER_API_KEY`, `SESSION_SECRET` 같은 서버 전용 비밀값만 저장

Provider URL은 OpenAI 호환 Chat Completions의 `/v1` 기본 주소 또는 `/chat/completions` 전체 주소를 사용한다. CLI 실험에서 `--model`을 명시하면 해당 실행 모델을 선택한다. Web MVP는 `provider.model`을 토론 외 판단·추출에 사용하고, `provider.debater_models` 배열에서 서로 다른 회사의 모델 두 개를 A/B 발언 생성에 배정한다.

`.env`는 Git에서 제외한다. 실제 키를 문서, 시나리오, 결과 폴더에 넣지 않는다. API 호출은 비용 또는 쿼터를 소모한다.

## 실행

```powershell
.\.venv\Scripts\python.exe -m src.debate_engine.debate_harness --scenario etc\scenarios\hotdog.json --model gpt-5.4 --crossfire-pairs 2
```

`--crossfire-pairs`는 1~12다. `--output`으로 결과 폴더를 지정할 수 있다. 기본값은 `etc/runs/<시각>`이다. State replay는 `.venv`에 `requirements.txt`의 Pydantic 설치가 필요하다.

## 산출물과 한계

- `scenario.json`: 실행한 논제·입장·Persona 입력
- `run.json`: 모델명과 실행 조건(키 제외)
- `normal.jsonl`, 선택 시 `swapped.jsonl`: 발언 원문, 사용량, 지연 시간, 오류
- `review.md`: 사람이 판정할 표

각 발언은 최근 대화 일부를 입력으로 받는다. 명시적인 최종 Thesis 역전은 `stance_compliance.py`가 차단하고 한 번만 재생성을 허용한다. 최종 발언에서 입장이 명확하지 않아 `AMBIGUOUS`이면 확정하지 않고 같은 경로로 재생성한다. 의미 검사는 일반 Tool Calling 기반 semantic stance guard가 수행한다. **전체 15 Action Selector, Topic Analyzer, Context Intake, 자동 정확도 점수는 구현하지 않았다.** 따라서 이 실행만으로 State Drift나 전체 설계의 품질을 검증했다고 말할 수 없다.

2026-09-22 `gpt-5.4` Copa API 실측에서 일반 대화와 Tool Calling(강제 선택 옵션 없음)은 응답을 받았다. `response_format: json_schema`와 `tool_choice: required` 요청은 각각 HTTP 400 `unsupported_feature`였다. 이는 테스트한 요청의 결과이며 다른 모델·옵션 조합까지 일반화하지 않는다.

## State Patch와 provider 경계

`state_harness.py`는 `ProviderCapabilities(True, False, False)`에 따라 일반 Tool Calling을 쓰고, 결과를 항상 로컬 Pydantic `PatchEnvelope`로 검사한다. 이어서 `apply_patch`가 Entity 존재와 소유권을 검증한다. 두 단계 중 하나라도 실패하면 구조화된 오류를 전달해 한 번 수정 요청한다. 다시 실패하면 State를 확정하지 않고 중단한다. 실제 API 경로는 아래 소규모 진단과 통합 실행에서 확인했다.

Patch Operation별 참조 타입: `ADD_PROPOSITION` 참조 없음; `ADD_RELATION`의 `from_proposition_id`·`to_proposition_id`는 C; `ASK_QUESTION`의 `target_proposition_id`는 C 또는 없음; `ANSWER_QUESTION`의 `question_id`는 Q; `REVISE_PROPOSITION`의 `old_proposition_id`는 C; `CONCEDE_LOCAL`·`WITHDRAW_PROPOSITION`의 `proposition_id`는 C. R ID는 관계 Entity에만 부여한다. 기존 Proposition은 변경하지 않으며 Revision은 새 C와 REVISE event를 추가한다.

Question Response 재판정 기준은 `QUESTION_RESPONSE_RUBRIC.md`, 사람의 6개 사례 재판정 입력은 `etc/fixtures/question_response_reannotation.json`에 있다.

## 소규모 실제 API 진단

```powershell
.\.venv\Scripts\python.exe -m etc.tools.question_response_review
.\.venv\Scripts\python.exe -m etc.tools.question_response_review --interactive
.\.venv\Scripts\python.exe -m etc.tools.question_response_review --set rr01 DIRECT --reason "핵심 질문에 직접 답함"
.\.venv\Scripts\python.exe -m etc.tools.question_response_eval --model gpt-5.4 --output etc\runs\question-response-next.json
.\.venv\Scripts\python.exe -m etc.tools.stance_api_diagnostic --model gpt-5.4 --output etc\runs\stance-next.json
.\.venv\Scripts\python.exe -m etc.tools.state_patch_api_diagnostic --model gpt-5.4 --output etc\runs\state-patch-next.json
```

Review script는 `QUESTION_RESPONSE_RUBRIC.md`를 표시하고 Label을 사람이 입력할 때만 저장한다. 평가 script는 6건의 새 Label이 모두 있어야 API를 호출한다. 현재 Label은 사용자 요청에 따라 AI가 수동 검토한 것이며 독립적인 사람의 검증은 아니다. 실제 진단 결과는 `etc/runs/diagnostic-question-response-v2.json`, `etc/runs/diagnostic-stance-v2.json`, `etc/runs/diagnostic-state-patch-v2.json`에 있다. State Patch의 최초 잘못된 후보는 fixture 주입이며, 수정 요청은 실제 API 호출이다.

## Guarded 10 Turn 통합 진단

```powershell
.\.venv\Scripts\python.exe -m etc.tools.integrated_debate --scenario etc\scenarios\tangsuyuk.json --model gpt-5.4 --crossfire-turns 6 --output etc\runs\integration-next
```

Opening 2, Crossfire 6, Rebuttal 2로 최대 10 Turn이다. Action 후보를 현재 State로 제한하고, 발언 생성 → 로컬 검사 → semantic stance 검사 → 확정 후 Patch 추출·검증·적용 순서를 지킨다. Stance 위반은 한 번 재생성한 뒤에도 남으면 발언과 State를 확정하지 않는다. Moderator는 hard budget, safe failure, eligible action 없음에서만 멈춘다. Novelty는 로그 신호이며 종료 조건이 아니다. 이 Action 정책은 통합 진단에 필요한 일부 Action만 다루며 전체 설계의 전략 선택기를 대체하지 않는다.

첫 실행 `etc/runs/integration-tangsuyuk-guarded-v1`은 Action 반복 기록을 발언자별로 분리하지 않아 1 Turn 뒤 멈췄다. 수정 후 같은 논제의 `etc/runs/integration-tangsuyuk-guarded-v2`는 10 Turn을 완료했다. `turns.jsonl`은 Turn별 필수 항목, `summary.json`은 최종 State, `audit.json`은 State replay와 참조·Action·질문 검사를 기록한다. Turn 4의 선택 Action과 실제 발언 초점 불일치는 후속 검증 대상으로 남아 있다.

## Action Fidelity와 Proposition audit

`ACTION_EXECUTION_CONTRACTS.md`는 15개 Action의 target type, required semantic effect, 허용 표현, 실패 패턴을 정의한다. Eligibility와 Fidelity는 별도 계약이다. Runtime은 발언 생성 뒤 일반 Tool Calling 한 번으로 `action_fidelity`와 `stance_compliance`를 함께 받지만, 각 결과의 enum·이유·처리 규칙은 `combined_compliance.py`에서 분리한다. `MISALIGNED`·`UNCLEAR` Action 또는 `AMBIGUOUS`·`CONTRADICTS_ASSIGNED` Stance는 한 번 재생성하고 재실패하면 State를 변경하지 않는다.

```powershell
.\.venv\Scripts\python.exe -m etc.tools.audit_review etc\fixtures\action_fidelity_audit.json --interactive
.\.venv\Scripts\python.exe -m etc.tools.audit_review etc\fixtures\proposition_extraction_audit.json --interactive
```

Label이 비어 있는 원본 fixture와 수동 검토 완료본을 분리했다. 완료본은 `action_fidelity_audit_reviewed.json`, `proposition_extraction_audit_reviewed.json`이다. 검토 출처는 AI 수동 검토이며 독립적인 사람의 adjudication은 아니다. 기존 실행의 분석은 `etc/runs/integration-tangsuyuk-guarded-v2/human-audit-summary.json`에 있다.

Action guard를 연결한 단일 후속 실행은 `etc/runs/integration-tangsuyuk-action-guard-v1`이다. 10 Turn, 30 API call, 49,479 tokens를 사용했다. 결합 guard 결과와 수동 대조는 모든 Turn에서 ALIGNED였고 State replay 무결성은 `audit.json`에 기록했다.

## Quality validation guard

State Patch 적용 전 `question_extraction_guard.py`가 인용문을 제외한 명시적 한국어 질문 형태를 검사한다. 후보가 있는데 `ASK_QUESTION`이 없으면 State를 적용하지 않고 한 번 repair하며, 재실패 시 기존 safe failure 정책으로 종료한다. Question은 원문 text, core proposition, asker, 선택 target, 상태, resolution, source turn을 보존한다.

`target_quality.py`는 Proposition identity와 분리된 derived metadata를 만든다. Actionability는 CORE, SUPPORTING, CONTEXTUAL, RHETORICAL이며 clash relevance, centrality, unresolved 상태, recentness, commitment strength, question dependency, downstream reuse risk와 함께 coarse ranking에 사용한다. 수사적 표현, 철회·수정된 명제, 해결·양보·반복 소진 target에는 강한 penalty를 준다. 사람 판정은 `target_review.py <fixture> --interactive`로 입력하며 자동 label은 만들지 않는다.

`action_pair_state.py`는 `speaker + action + target_id`별 AVAILABLE/OPEN/PARTIALLY_RESOLVED/RESOLVED/EXHAUSTED/BLOCKED 상태를 계산한다. Selector는 pair filter를 target ranking보다 먼저 적용한다. `REQUEST_SUPPORT`는 support가 SUFFICIENT이면 RESOLVED, CONTESTED이면 EXHAUSTED로 제외하지만 같은 target의 다른 Action은 유지한다. 세부 규칙은 `ACTION_TARGET_PAIR_STATE.md`에 있다. 기존 핫도그·출석 실패 State는 `etc/fixtures/action_pair_*`에 보존했다.

`persona_preferences.py`는 Persona별 strong preference를 `HIGH`로, 그 밖의 적법한 Action을 `MEDIUM`으로 표현한다. `LOW`는 ordinal에만 예약되어 있고 현재 확정 계약에는 임의의 기피 Action을 추가하지 않았다. Selector 순서는 hard eligibility와 pair filter → target quality → strategic utility → Persona preference → repetition/saturation이다. Persona는 후보를 생성하거나 BLOCKED/RESOLVED/EXHAUSTED pair를 복구하지 않으며, `persona=None`은 모든 Action을 `MEDIUM`으로 취급하는 control path다.

State extraction의 새 Proposition은 `P1`, `P2` Patch-local ID를 사용하고 Relation은 기존 `C*` 또는 같은 Patch의 `P*`를 참조한다. 적용 시 실제 C ID로 resolve하며 없는 P/C는 전체 Patch를 거부한다. Extractor context에는 기존 Relation도 포함하고 동일한 from/to/type은 중복 저장하지 않는다. 의미 규칙은 `RELATION_EXTRACTION_CONTRACT.md`에 있다.

핫도그 Turn 6 State의 단일 후속 API 진단은 `etc/runs/action-pair-hotdog-turn6-v1`이다. 기존 `REQUEST_SUPPORT(C1)` 대신 `CHALLENGE_INFERENCE(C1)`이 선택됐고, 3 API call과 5,235 tokens를 사용해 ALIGNED, State commit, integrity issue 0을 확인했다.
