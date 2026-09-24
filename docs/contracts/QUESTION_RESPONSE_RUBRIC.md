# Question Response Annotation Guideline v2

판정 단위는 직전 질문과 그 다음 발언이다. 먼저 질문의 핵심 proposition과 복수 요구를 분리하고, 답변이 실제로 해결한 부분을 표시한다. 발언 끝의 새 질문은 직전 질문에 대한 응답 판정에 넣지 않는다. State의 사실과 질문 전제의 충돌은 별도로 확인한다.

| Label | 판정 기준 |
|---|---|
| DIRECT | 핵심 proposition에 명확하게 답한다. 후속 설명이 있어도 핵심 답변의 적용 범위, 조건, 정도, 시점을 바꾸지 않는다. |
| QUALIFIED | 핵심에 답하지만 답의 실제 적용 범위, 조건, 정도, 시점을 제한한다. 단순 이유 설명이나 문장 길이만으로 이 Label을 주지 않는다. |
| PARTIAL | 복수 요구 중 일부만, 또는 핵심 proposition 일부만 해결한다. |
| EVADED | 핵심 proposition을 해결하지 않고 다른 화제로 이동하거나 답을 피한다. |
| FRAME_REJECTED_VALID | 질문 전제가 기록된 State와 충돌하고 답변이 그 전제를 구체적으로 교정한다. 충돌 근거를 기록하지 못하면 이 Label을 주지 않는다. |
| UNCLEAR | 위 판정이 안정적으로 불가능하다. 전제 충돌 여부가 불명확하거나 답변의 핵심이 모호한 경우를 포함한다. |

판정 순서: (1) State 근거가 있는 정당한 frame 교정인지, (2) 복수 요구의 일부만 해결했는지, (3) 핵심 proposition에 답했는지, (4) 실제 scope 제한이 있는지 확인한다. `question_rubric.py`는 사람이 채운 근거 필드의 결정 규칙이며 자연어 의미를 자동 판독하지 않는다.

재판정 작업 파일: `etc/fixtures/question_response_reannotation.json`. 기존 6개 발언 원문과 과거 human label을 보존했다. 현재 `new_human_label`은 사용자의 요청에 따라 AI가 원문을 수동 검토해 채웠다. 독립적인 사람의 확정 정답은 아니며 `annotation_provenance`에 출처를 기록했다. 이 6건의 일치 건수는 일반화된 정확도가 아니다.
