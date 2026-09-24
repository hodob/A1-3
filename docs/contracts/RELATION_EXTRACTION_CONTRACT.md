# Relation Extraction Contract

## Patch-local Proposition reference

새 Proposition은 실제 State ID를 추측하지 않고 Patch-local `P1`, `P2`를 사용한다.

```json
{"op":"ADD_PROPOSITION","temp_id":"P1","text":"결론"}
{"op":"ADD_PROPOSITION","temp_id":"P2","text":"직접 근거"}
{"op":"ADD_RELATION","from_proposition_ref":"P2","to_proposition_ref":"P1","relation_type":"SUPPORTS"}
```

`apply_patch()`는 Patch의 모든 `P*`를 먼저 실제 `C*`에 예약한 뒤 Relation을 resolve한다. `C*`는 Patch 적용 전 State에 존재해야 한다. 존재하지 않는 P/C, 중복 temp ID는 Patch 전체를 거부한다.

## Relation semantics

| Relation | 저장 기준 |
|---|---|
| SUPPORTS | 한 Proposition이 다른 Proposition의 이유, 근거, 기준 또는 정당화를 제공한다. |
| ATTACKS | 다른 Proposition의 근거 또는 타당성을 약화시키지만 두 Proposition이 논리적으로 동시에 참일 수도 있다. |
| CONTRADICTS | 같은 scope, time, modal 조건에서 두 Proposition이 동시에 참일 수 없다. |
| QUALIFIES | 기존 Proposition의 적용 범위, 조건, 정도 또는 modality를 제한한다. |

- 명시적이거나 강하게 표현된 argumentative relation만 저장한다.
- implicit warrant를 생성하지 않는다.
- 수사적 연관이나 단순 주제 유사성으로 Relation을 만들지 않는다.
- 새 Proposition이 기존 핵심 Claim의 이유라면 SUPPORTS로 연결한다.
- 새 Proposition이 기존 Claim의 근거를 직접 약화하면 ATTACKS로 연결한다.
- 동일한 `from + to + relation_type`은 State에 한 번만 저장한다.

## Extraction context

Extractor에는 Proposition의 `id/text/speaker`, 기존 Relation의 `id/from/to/type`, open Question만 전달한다. 기존 Relation과 동일한 operation을 모델이 반환해도 `apply_patch()`가 deduplicate한다.

## Support sufficiency boundary

명시적 SUPPORTS는 SUFFICIENT다. SUPPORTS가 ATTACKS 또는 CONTRADICTS의 target이면 CONTESTED다. QUALIFIES는 WEAK다. Lexical overlap만으로는 최대 WEAK이며 SUFFICIENT가 될 수 없다. 명시적 local concession처럼 별도의 구조화 evidence가 있을 때만 동등한 강한 증거로 사용할 수 있다.
