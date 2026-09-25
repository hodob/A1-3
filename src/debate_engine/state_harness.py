"""Replay transcripts through typed and locally validated State patches."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .debate_contracts import DebateState, PatchEnvelope, PatchIssue, PatchValidationError, apply_patch
from .debate_harness import ConfigError, load_config, select_debaters
from .provider_adapter import CURRENT_PROVIDER, ProviderAdapter, ProviderOutputError
from .provider_transport import request_completion
from .question_extraction_guard import explicit_question_candidates
from .debate_control import build_control_view, immediate_qud


ADAPTER = ProviderAdapter(CURRENT_PROVIDER)
PATCH_INSTRUCTIONS = (
    "새 발언에 명시된 내용만 operations로 추출하세요. 명제 C ID, 질문 Q ID, 관계 R ID를 구별하세요. "
    "새 ADD_PROPOSITION에는 Patch-local temp_id(P1, P2...)를 순서대로 부여하고 미래 C 번호를 추측하지 마세요. "
    "ADD_RELATION은 from_proposition_ref/to_proposition_ref에 기존 C ID 또는 이번 Patch의 P ID를 사용합니다. ASK_QUESTION은 target_proposition_id, "
    "ANSWER_QUESTION은 question_id, REVISE_PROPOSITION은 old_proposition_id/new_proposition_text를 사용합니다. "
    "기존 명제의 text는 변경하지 않습니다. 수정은 새 명제와 REVISE event를 만듭니다. "
    "발언자가 기존 명제를 인정하면 같은 내용을 새 ADD_PROPOSITION으로 만들지 말고 CONCEDE_LOCAL로 기존 C ID를 참조하세요. "
    "비유·수사적 예시는 그 자체가 독립적인 논증적 commitment가 아니라면 Proposition으로 저장하지 마세요. "
    "[[C24]], [[Q3]] 같은 표기는 기존 State 항목을 가리키는 citation marker입니다. marker 문자열 자체를 새 Proposition text에 복사하지 말고, 참조된 기존 항목과의 의미 관계만 추출하세요. "
    "서로 독립적인 명제를 하나의 Proposition으로 합치지 마세요. 의문형으로 명시된 실제 질문은 빠뜨리지 말고 ASK_QUESTION으로 기록하세요. "
    "Relation 의미 규칙: SUPPORTS는 한 Proposition이 다른 Proposition의 이유, 근거, 기준 또는 정당화를 제공합니다. "
    "ATTACKS는 다른 Proposition의 근거 또는 타당성을 약화시키지만 둘이 동시에 참일 수도 있습니다. "
    "CONTRADICTS는 같은 scope/time/modal 조건에서 둘이 동시에 참일 수 없습니다. "
    "QUALIFIES는 기존 Proposition의 적용 범위, 조건, 정도 또는 modality를 제한합니다. "
    "명시적 또는 강하게 표현된 argumentative relation만 저장하고 implicit warrant나 수사적 연관을 만들지 마세요. "
    "새 Proposition이 기존 핵심 Claim의 이유이면 SUPPORTS, 기존 Claim의 근거를 직접 약화하면 ATTACKS입니다. 단순 주제 유사성은 Relation이 아닙니다. "
    "각 ADD_PROPOSITION에는 semantic_kind를 반드시 판단하세요: NEW_REASON은 기존에 없던 독립 이유, SAME_POINT는 같은 논지의 말바꿈, REFINEMENT는 같은 논지의 표현/정교화, "
    "NEW_COUNTEREXAMPLE은 기존 주장에 대한 새 반례, QUALIFICATION은 범위·조건·정도를 실제로 제한, RELATED_DISTINCT는 관련 있지만 별개의 논지입니다. "
    "SAME_POINT/REFINEMENT/QUALIFICATION은 semantic_anchor_ref에 가장 가까운 기존 C 또는 이번 Patch의 P를 넣으세요. 단순 단어 유사성만으로 SAME_POINT로 합치지 마세요. "
    "ASK_QUESTION에는 semantic_kind를 NEW_QUESTION/SAME_QUESTION/REFINEMENT 중 선택하세요. 표현만 바뀐 같은 질문이면 SAME_QUESTION과 기존 anchor_question_id를 사용하세요. "    "한 발화에 의문문이 여러 개 있어도 같은 target과 같은 쟁점을 연속해서 묻고 하나에 답하면 나머지도 실질적으로 해결되는 경우에는 하나의 Immediate QUD로 보고 ASK_QUESTION 하나만 만드세요. core_proposition에는 여러 표면 질문을 포괄하는 핵심 질문을 적으세요. " +
    "서로 다른 target을 묻거나 하나에 답해도 다른 질문이 남는 경우에만 ASK_QUESTION을 분리하세요. 질문표('?') 개수만으로 Q 노드를 늘리지 마세요. "
    "turn.selected_target_ids에 기존 C target이 있고 새 질문이 그 주장을 직접 검증한다면 ASK_QUESTION.target_proposition_id에 그 C ID를 기록하세요. 관련 없는 target을 억지로 연결하지 마세요. "
    "이미 RESOLVED된 질문을 새 근거나 새 범위 없이 다시 묻는 것은 SAME_QUESTION입니다. "
    "입력 relations에 같은 from/to/type이 이미 있으면 ADD_RELATION을 다시 만들지 마세요. extract_patch 도구를 호출하세요."
)


def extraction_context(state: DebateState, turn: dict | None = None) -> dict:
    """Select an adaptive working set for State reconciliation.

    Selection is graph-aware rather than fixed-k: current Action/QUD targets and
    explicit [[...]] references are seeds, then their facet anchors and one-hop
    relations are added. A small recent-per-speaker fallback preserves local context.
    """
    turn = turn or {}
    control = build_control_view(state)
    prop_by_id = {p.id: p for p in state.propositions}
    question_by_id = {q.id: q for q in state.questions}
    relation_list = list(state.relations)
    target_ids = {str(x) for x in turn.get("target_ids", [])}
    reference_ids = {str(x) for x in turn.get("reference_ids", [])}
    all_refs = target_ids | reference_ids

    scores: dict[str, int] = {}
    reasons: dict[str, set[str]] = {}

    def include(pid: str | None, score: int, reason: str) -> None:
        if not pid or pid not in prop_by_id:
            return
        scores[pid] = max(scores.get(pid, 0), score)
        reasons.setdefault(pid, set()).add(reason)

    for ref_id in all_refs:
        if ref_id.startswith("C"):
            include(ref_id, 100, "explicit_target_or_reference")
        elif ref_id.startswith("Q") and ref_id in question_by_id:
            include(question_by_id[ref_id].target_proposition_id, 95, "question_target")

    speaker = str(turn.get("speaker", ""))
    qud = immediate_qud(control, state, speaker) if speaker else None
    if qud is not None:
        include(qud.target_proposition_id, 95, "immediate_qud_target")

    # Preserve the semantic anchor/current wording for every selected facet.
    selected_facets = {
        control.proposition_to_facet[pid]
        for pid in list(scores)
        if pid in control.proposition_to_facet
    }
    for facet in control.facets:
        if facet.id in selected_facets:
            include(facet.current_id, 85, "facet_current")
            include(facet.representative_id, 75, "facet_representative")

    # One-hop argumentative neighbors are useful to reconcile SUPPORT/ATTACK/QUALIFY.
    seed_ids = set(scores)
    for relation in relation_list:
        if relation.from_proposition_id in seed_ids:
            include(relation.to_proposition_id, 65, "one_hop_relation")
        if relation.to_proposition_id in seed_ids:
            include(relation.from_proposition_id, 65, "one_hop_relation")

    # Keep at most two recent propositions per speaker. This is a fallback, not the
    # primary retrieval mechanism.
    recent_per_speaker: dict[str, int] = {}
    for proposition in reversed(state.propositions):
        count = recent_per_speaker.get(proposition.speaker, 0)
        if count >= 2:
            continue
        include(proposition.id, 40, "recent")
        recent_per_speaker[proposition.speaker] = count + 1
        if len(recent_per_speaker) >= 2 and all(value >= 2 for value in recent_per_speaker.values()):
            break

    # Cap by relevance and recency so growing State does not imply growing prompt.
    ranked = sorted(
        scores,
        key=lambda pid: (scores[pid], prop_by_id[pid].turn, int(pid[1:])),
        reverse=True,
    )
    include_prop_ids = set(ranked[:10])

    propositions = [
        {"id": p.id, "text": p.text, "speaker": p.speaker}
        for p in state.propositions
        if p.id in include_prop_ids
    ]
    relations = [
        {"id": r.id, "from": r.from_proposition_id, "to": r.to_proposition_id, "type": r.relation_type}
        for r in relation_list
        if r.from_proposition_id in include_prop_ids and r.to_proposition_id in include_prop_ids
    ]

    include_question_ids = {x for x in all_refs if x.startswith("Q") and x in question_by_id}
    if qud is not None:
        include_question_ids.update(qud.member_ids)
    questions = [question_by_id[qid].model_dump() for qid in question_by_id if qid in include_question_ids]

    included_facets = []
    for facet in control.facets:
        if not set(facet.member_ids).intersection(include_prop_ids):
            continue
        current = prop_by_id.get(facet.current_id)
        representative = prop_by_id.get(facet.representative_id)
        if current is None or representative is None:
            continue
        included_facets.append({
            "id": facet.id,
            "representative_id": facet.representative_id,
            "representative_text": representative.text,
            "current_id": facet.current_id,
            "current_text": current.text,
            "member_count": len(facet.member_ids),
            "speaker": facet.speaker,
            "semantic_role": facet.semantic_role,
        })

    return {
        "propositions": propositions,
        "relations": relations,
        "questions": questions,
        "facets": included_facets,
        "selected_action": turn.get("action"),
        "selected_target_ids": list(turn.get("target_ids", [])),
        "selected_reference_ids": list(turn.get("reference_ids", [])),
        "working_set": {
            "proposition_ids": [pid for pid in ranked[:10]],
            "reasons": {pid: sorted(reasons.get(pid, ())) for pid in ranked[:10]},
            "immediate_qud_id": qud.id if qud else None,
        },
    }

def call_patch(provider: dict, turn: dict, state: DebateState, timeout: float, feedback: list[dict] | None = None) -> tuple[PatchEnvelope, dict]:
    relevant = extraction_context(state, turn)
    messages = [{"role": "system", "content": PATCH_INSTRUCTIONS}, {"role": "user", "content": json.dumps({"state": relevant, "turn": turn, "validation_errors": feedback or []}, ensure_ascii=False)}]
    body = ADAPTER.build_structured_body(provider["model"], messages, PatchEnvelope, "extract_patch")
    started = time.monotonic()
    try:
        payload = request_completion(provider, body, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc.reason}") from exc
    patch = ADAPTER.parse_structured_response(payload, PatchEnvelope, "extract_patch")
    return patch, {
        "model": payload.get("model"),
        "usage": payload.get("usage"),
        "finish_reason": payload["choices"][0].get("finish_reason"),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "context_counts": {key: len(value) for key, value in relevant.items() if isinstance(value, list)},
    }


def extract_and_apply(state: DebateState, speaker: str, turn: int, extractor, *, utterance: str | None = None) -> tuple[DebateState, list[dict]]:
    """Try once, repair once, then fail without committing a candidate State."""
    feedback: list[dict] = []
    attempts = []
    for _ in range(2):
        try:
            patch, metadata = extractor(feedback)
            candidates = explicit_question_candidates(utterance or "")
            extracted_questions = [op for op in patch.operations if op.op == "ASK_QUESTION"]
            if candidates and not extracted_questions:
                raise PatchValidationError([PatchIssue("missing_explicit_question", "operations", "Explicit question candidate was not extracted", reference=candidates[0])])
            candidate = apply_patch(state, patch, speaker=speaker, turn=turn)
            attempts.append({"valid": True, "patch": patch.model_dump(), "metadata": metadata, "question_guard": {"candidates": candidates, "extracted_count": len(extracted_questions), "status": "PASS"}})
            return candidate, attempts
        except PatchValidationError as exc:
            issues = exc.issues
        except ProviderOutputError as exc:
            issues = [PatchIssue(exc.code, ".".join(map(str, item.get("loc", []))), item.get("msg", item.get("message", exc.code))) for item in exc.details] or [PatchIssue(exc.code, "provider_output", exc.code)]
        feedback = [issue.as_dict() for issue in issues]
        attempts.append({"valid": False, "issues": feedback})
    raise PatchValidationError(issues)


def replay(transcript_path: Path, provider: dict, output: Path, timeout: float) -> DebateState:
    if output.exists():
        raise ValueError(f"Output exists: {output}")
    turns = [json.loads(line) for line in transcript_path.read_text(encoding="utf-8").splitlines()]
    if [int(x["turn"]) for x in turns] != list(range(1, len(turns) + 1)):
        raise ValueError("Transcript turns must be contiguous from 1")
    output.mkdir(parents=True)
    state = DebateState()
    with (output / "patches.jsonl").open("w", encoding="utf-8") as log:
        for turn in turns:
            index = int(turn["turn"])
            try:
                candidate, attempts = extract_and_apply(state, turn["speaker"], index, lambda feedback: call_patch(provider, turn, state, timeout, feedback), utterance=turn.get("speech"))
            except PatchValidationError as exc:
                log.write(json.dumps({"turn": index, "safe_failure": True, "issues": [issue.as_dict() for issue in exc.issues]}, ensure_ascii=False) + "\n")
                raise RuntimeError(f"Turn {index} state extraction failed after bounded repair") from exc
            state = candidate
            log.write(json.dumps({"turn": index, "attempts": attempts, "counts": {key: len(value) for key, value in state.model_dump().items()}}, ensure_ascii=False) + "\n")
            log.flush()
            if index in (5, 10, 20, 30):
                (output / f"checkpoint-{index}.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
            print(f"state: {index}/{len(turns)}", flush=True)
    (output / "final-state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay transcript into incremental debate state")
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args(argv)
    try:
        provider = select_debaters(load_config(args.env), args.model)["DEBATER_A"]
        state = replay(args.transcript, provider, args.output, args.timeout)
        print(json.dumps({key: len(value) for key, value in state.model_dump().items()}))
        return 0
    except (ConfigError, ValueError, RuntimeError, OSError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
