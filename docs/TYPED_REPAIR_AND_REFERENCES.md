# Typed Repair & State References

## Runtime pipeline

```text
Debate State
  -> Turn Task
  -> Action x Target
  -> structured speech prompt
  -> Draft
  -> local surface validation
  -> semantic compliance
  -> typed failure codes
       -> TARGETED_REPAIR
       -> REPLAN_AND_REGENERATE
       -> HARD_FAILURE
  -> committed utterance
  -> State Patch
```

한 번의 사용자 요청 안에서 draft는 최대 3회입니다. 2차 시도는 이전 draft와 위반 코드를 함께 받은 targeted repair이고, 같은 전략으로 해결하기 어려운 반복/Task-Action 충돌은 3차 전에 Action x Target을 다시 고를 수 있습니다.

주요 failure code:

- `STANCE_REVERSAL`, `STANCE_AMBIGUOUS`
- `ACTION_NOT_PERFORMED`, `TARGET_NOT_USED`, `ACTION_NOT_CORE`
- `TASK_OFF_TASK`, `REPHRASE_ONLY`, `TASK_ACTION_CONFLICT`
- `RAW_STATE_ID_LEAK`, `UNKNOWN_STATE_REFERENCE`
- `MARKDOWN_DISALLOWED_ELEMENT`
- `FINAL_FOCUS_FORMAT`, `FINAL_FOCUS_LENGTH`, `FINAL_FOCUS_QUESTION`

`ANSWER_OPEN_QUESTION`과 `ADDRESS_AUDIENCE`는 직접 응답 의무가 primary이고 Strategic Action은 secondary입니다. 따라서 질문에 제대로 답하고 stance를 유지한 발언은 secondary Action이 `PARTIALLY_ALIGNED`여도 불필요하게 버리지 않습니다.

## State reference syntax

생성 모델에는 이번 턴에서 실제로 참조 가능한 State 항목만 제공합니다.

```text
[[C24]]
[[Q3]]
```

marker 밖의 raw `C24` / `Q3`는 허용하지 않습니다. 존재하지 않거나 이번 prompt에 제공되지 않은 marker도 local validation에서 거부합니다.

commit된 transcript는 reference metadata를 함께 갖습니다.

```json
{
  "id": "C24",
  "kind": "CLAIM",
  "speaker": "A",
  "turn": 11,
  "excerpt": "..."
}
```

브라우저는 이를 `↖ A · 발언 11` chip으로 렌더링하며, 클릭하면 해당 발언으로 이동해 잠시 강조합니다.

## Markdown surface contract

일반 발언에서 허용:

- `**굵게**`
- `*기울임*`
- 필요한 경우 2~3개의 짧은 목록
- 상대 표현을 짚는 짧은 blockquote

문서형 출력인 제목, 표, 코드 블록, HTML, 외부 링크는 생성 계약에서 금지하고 local validation으로 확인합니다.

Final Focus는 별도 제한을 적용합니다.

- 한 문단
- 최대 2문장
- 목록 / blockquote / 질문 금지
- 핵심 기준의 짧은 굵은 강조만 허용

## Prompt layout

Speech prompt는 `identity`, `hard_rules`, `grounding`, `assignment`, `phase_instruction`, `surface_style`, `surface_format`을 분리합니다. 논제, 사용자 맥락, transcript, 관객 질문은 data 영역으로 구분하며 XML escape 후 전달합니다.

retry prompt에는 다음을 분리해 전달합니다.

- `previous_draft`
- `violations`
- `preserve`
- 현재 또는 재계획된 `current_contract`
- `retry_strategy`

## State Patch context

Patch extractor에는 전체 누적 graph를 매번 재전송하지 않습니다. 현재 semantic facet의 대표/현재 명제, 최근 명제, 이번 Action target, 열린/최근 질문과 필요한 관계를 중심으로 bounded context를 구성합니다. debug mode에서는 patch별 `context_counts`를 기록합니다.
