# Action–Target Pair Derived State

Pair key는 MVP에서 `speaker + action + target_id`다. 이 값은 Proposition이나 Question의 authoritative identity가 아니라 Selector가 매 Turn 다시 계산하는 derived state다.

| State | 처리 |
|---|---|
| AVAILABLE | 의미 있게 처음 사용할 수 있다. |
| OPEN | 이미 다뤘지만 중요한 미해결 부분이 남았다. |
| PARTIALLY_RESOLVED | 일부 해결됐으며 별도 검증 여지가 있다. |
| RESOLVED | Action의 목적이 충족되어 선택에서 제외한다. |
| EXHAUSTED | 같은 pair의 반복 가치가 낮아 선택에서 제외한다. |
| BLOCKED | Entity, ownership, revision 또는 Protocol 조건상 사용할 수 없다. |

Support sufficiency는 `NONE`, `WEAK`, `SUFFICIENT`, `CONTESTED`만 사용한다. 명시적인 SUPPORTS/QUALIFIES relation을 우선하고, 기존 engagement 뒤 target owner가 만든 관련 Proposition은 보조 derived evidence로만 사용한다.

- `REQUEST_SUPPORT`: NONE은 AVAILABLE, WEAK은 AVAILABLE/OPEN, SUFFICIENT는 RESOLVED, CONTESTED는 EXHAUSTED다. SUFFICIENT/CONTESTED에서는 기존 support를 `CHALLENGE_INFERENCE`, `CHALLENGE_PREMISE`, `TEST_BOUNDARY`, `REFUTE_CLAIM`으로 다룬다.
- `CLARIFY_CLAIM`: 동일 target의 definition/scope 질문이 DIRECT, QUALIFIED 또는 FRAME_REJECTED_VALID로 해결되면 RESOLVED다.
- `PRESS_UNANSWERED`: DIRECT, 충분히 해결된 QUALIFIED, FRAME_REJECTED_VALID는 RESOLVED다. PARTIAL/EVADED이면서 OPEN이면 OPEN이다.
- `CHECK_CONSISTENCY`: revision 또는 concession으로 tension이 수리되면 RESOLVED다.
- `TEST_BOUNDARY`: 같은 MVP pair를 이미 사용했다면 EXHAUSTED다. sub-dimension 분리는 이번 구현에 넣지 않았다.
- `SEEK_COMMITMENT`: 명시적 commitment가 기록되면 RESOLVED다.
- revised/withdrawn old Proposition은 BLOCKED이며 새 Proposition은 별도 target으로 평가한다.

Selector 순서는 Action/Target eligibility → pair state filter → target quality ranking → strategic priority다. 따라서 `REQUEST_SUPPORT(C1)`만 제거해도 C1 자체와 다른 Action 후보는 유지된다.
