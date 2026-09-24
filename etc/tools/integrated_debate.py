"""Bounded end-to-end debate integration runner with guarded State commit."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from src.debate_engine.action_policy import eligible_actions, select_action_for_speaker
from src.debate_engine.action_pair_state import evaluate_action_target_pair, filter_available_pairs
from src.debate_engine.action_execution_contracts import CONTRACTS
from src.debate_engine.debate_contracts import DebateState, PatchValidationError
from src.debate_engine.debate_harness import append_jsonl, call_model, load_config, load_scenario, select_debaters, speech_messages
from src.debate_engine.combined_compliance import finalize_compliant_utterance, judge_combined
from src.debate_engine.stance_compliance import StanceAssessment, StanceAssignment, StanceLabel, finalize_utterance
from src.debate_engine.state_harness import call_patch, extract_and_apply
from src.debate_engine.target_quality import derive_target_metadata
from etc.tools.target_review import build_target_review_fixture


def commit_turn(state: DebateState, generate, assignment: StanceAssignment, *, phase: str, semantic_check, extract_patch) -> dict:
    """No extraction or State commit occurs until the utterance passes both gates."""
    checked = finalize_utterance(generate, assignment, phase=phase, semantic_check=semantic_check)
    if not checked.committed:
        return {"committed": False, "state": state, "utterance": None, "stance": checked, "patch_attempts": []}
    try:
        candidate, attempts = extract_patch(checked.utterance, state)
    except PatchValidationError as exc:
        return {"committed": False, "state": state, "utterance": None, "stance": checked, "patch_attempts": [], "patch_error": [issue.as_dict() for issue in exc.issues]}
    return {"committed": True, "state": candidate, "utterance": checked.utterance, "stance": checked, "patch_attempts": attempts}


def commit_guarded_turn(state: DebateState, generate, assignment: StanceAssignment, *, action: str, target_text: str | None, phase: str, combined_check, extract_patch) -> dict:
    """Action Fidelity and Stance remain separate verdicts inside one provider call."""
    checked = finalize_compliant_utterance(generate, assignment, action, target_text, phase, combined_check)
    if not checked.committed:
        return {"committed": False, "state": state, "utterance": None, "compliance": checked, "patch_attempts": []}
    try:
        candidate, attempts = extract_patch(checked.utterance, state)
    except PatchValidationError as exc:
        return {"committed": False, "state": state, "utterance": None, "compliance": checked, "patch_attempts": [], "patch_error": [issue.as_dict() for issue in exc.issues]}
    return {"committed": True, "state": candidate, "utterance": checked.utterance, "compliance": checked, "patch_attempts": attempts}


def state_integrity_issues(state: DebateState) -> list[str]:
    propositions = {p.id for p in state.propositions}
    questions = {q.id for q in state.questions}
    relations = {r.id for r in state.relations}
    issues = []
    if len(propositions) != len(state.propositions) or len(questions) != len(state.questions) or len(relations) != len(state.relations):
        issues.append("duplicate_entity_id")
    for relation in state.relations:
        if relation.from_proposition_id not in propositions or relation.to_proposition_id not in propositions:
            issues.append(f"dangling_relation:{relation.id}")
    for question in state.questions:
        if question.target_proposition_id and question.target_proposition_id not in propositions:
            issues.append(f"dangling_question_target:{question.id}")
    for event in state.commitment_events:
        if event.proposition_id not in propositions or (event.old_proposition_id and event.old_proposition_id not in propositions):
            issues.append(f"dangling_commitment:{event.proposition_id}")
    return issues


def build_integration_schedule(scenario: dict, crossfire_turns: int = 6) -> list[dict]:
    if not 5 <= crossfire_turns <= 6:
        raise ValueError("This diagnostic permits 5 or 6 crossfire turns")
    order = [("opening", 0), ("opening", 1)] + [("crossfire", i % 2) for i in range(crossfire_turns)] + [("rebuttal", 0), ("rebuttal", 1)]
    if len(order) > 10:
        raise ValueError("Integration turn budget exceeded")
    return [{"turn": index + 1, "phase": phase, "speaker": "A" if side == 0 else "B", "side": scenario["sides"][side], "persona": scenario["personas"][side]} for index, (phase, side) in enumerate(order)]


def _response_obligation(state: DebateState, speaker: str) -> dict | None:
    question = next((q for q in reversed(state.questions) if q.asker != speaker and q.resolution == "OPEN"), None)
    return {"question_id": question.id, "mode": "ANSWER", "core_proposition": question.core_proposition} if question else None


def run_integration(scenario: dict, providers: dict, output: Path, *, crossfire_turns: int = 6, timeout: float = 90) -> dict:
    if output.exists():
        raise ValueError(f"Output exists: {output}")
    schedule = build_integration_schedule(scenario, crossfire_turns)
    output.mkdir(parents=True)
    (output / "scenario.json").write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    state = DebateState()
    transcript = []
    action_history = []
    rows = []
    log_path = output / "turns.jsonl"
    stop_reason = None
    for turn in schedule:
        speaker = turn["speaker"]
        phase = turn["phase"]
        provider = providers[f"DEBATER_{speaker}"]
        raw_options = eligible_actions(state, speaker, phase)
        options = filter_available_pairs(state, speaker, raw_options, action_history, current_turn=turn["turn"])
        selected = select_action_for_speaker(options, action_history, speaker, state=state, current_turn=turn["turn"], persona=turn["persona"])
        obligation = _response_obligation(state, speaker)
        target_id = selected.target_ids[0] if selected and selected.target_ids else None
        target_text = next((p.text for p in state.propositions if p.id == target_id), None)
        if target_text is None and target_id:
            target_text = next((q.core_proposition for q in state.questions if q.id == target_id), None)
        target_metadata = derive_target_metadata(state, target_id, current_turn=turn["turn"], action_history=action_history).as_dict() if target_id and target_id.startswith("C") else None
        pair_status = evaluate_action_target_pair(state, speaker, selected.name, target_id, action_history, current_turn=turn["turn"]) if selected and target_id else None
        record = {
            "turn_id": turn["turn"], "speaker": speaker, "phase": phase.upper(), "assigned_stance": turn["side"], "persona_id": turn["persona"],
            "response_obligation": obligation, "eligible_actions": [{"name": a.name, "target_ids": list(a.target_ids), "target_quality_metadata": derive_target_metadata(state, a.target_ids[0], current_turn=turn["turn"], action_history=action_history).as_dict() if a.target_ids and a.target_ids[0].startswith("C") else None} for a in options],
            "selected_primary_action": selected.name if selected else None, "selected_secondary_action": None, "target_ids": list(selected.target_ids) if selected else [],
            "selected_target": {"id": target_id, "text": target_text} if target_id else None, "target_quality_metadata": target_metadata,
            "action_target_pair_state": {"state": pair_status.state.value, "support_sufficiency": pair_status.support_sufficiency.value if pair_status.support_sufficiency else None, "reason": pair_status.reason} if pair_status else None,
            "raw_utterance": None, "final_utterance": None, "stance_check_result": None, "stance_regenerated": False,
            "action_fidelity_check_result": None, "action_regenerated": False, "compliance_check_result": None,
            "candidate_patch": None, "patch_validation_result": None, "applied_patch": None, "question_response_status": None,
            "moderator_decision": "CONTINUE", "token_usage": [], "provider_call_count": 0, "safe_failure": False,
            "responsiveness": {"status": "NEEDS_HUMAN_REVIEW", "previous_opponent_utterance": next((item["speech"] for item in reversed(transcript) if item["speaker"] != speaker), None)},
            "novelty_delta": None, "action_eligibility_valid": selected in options if selected else None,
            "question_extraction_status": None, "response_status": None, "novel_state_change": False,
            "callback_used": False, "contradiction_used": False, "concession_used": False, "revision_used": False,
        }
        if selected is None:
            record["moderator_decision"] = "STOP_NO_ELIGIBLE_ACTION"
            stop_reason = record["moderator_decision"]
        else:
            before = state.model_dump()
            raw_attempts = []

            def account(purpose: str, meta: dict) -> None:
                record["provider_call_count"] += 1
                record["token_usage"].append({"purpose": purpose, "usage": meta.get("usage")})

            try:
                messages = speech_messages(scenario, turn, transcript)
                contract = CONTRACTS[selected.name]
                messages[1]["content"] += (
                    f"\n선택 Action: {selected.name}, target_ids: {list(selected.target_ids)}, target_text: {target_text or '(없음)'}. "
                    f"Execution Contract: {contract.required_semantic_effect} 해당 target에 이 효과를 실제로 수행하세요."
                )
                if obligation:
                    messages[1]["content"] += f"\n먼저 열린 질문 {obligation['question_id']}에 답하세요: {obligation['core_proposition']}"

                def generate(feedback: str) -> str:
                    request_messages = messages if not feedback else [*messages, {"role": "user", "content": feedback}]
                    record["provider_call_count"] += 1
                    speech, meta = call_model(provider, request_messages, timeout=timeout)
                    record["token_usage"].append({"purpose": "utterance_generation", "usage": meta.get("usage")})
                    raw_attempts.append(speech)
                    record["raw_utterance"] = raw_attempts[0]
                    return speech

                opposing = scenario["sides"][1] if speaker == "A" else scenario["sides"][0]
                assignment = StanceAssignment(turn["side"], opposing)

                def combined_check(speech: str, assigned: StanceAssignment, current_phase: str, action: str, checked_target_text: str | None):
                    record["provider_call_count"] += 1
                    verdict, meta = judge_combined(provider, action=action, target_id=target_id, target_text=checked_target_text, utterance=speech, assignment=assigned, phase=current_phase, timeout=timeout)
                    record["token_usage"].append({"purpose": "combined_action_stance_check", "usage": meta.get("usage")})
                    return verdict

                def extract(speech: str, prior: DebateState):
                    def extractor(feedback):
                        record["provider_call_count"] += 1
                        patch, meta = call_patch(provider, {"turn": turn["turn"], "speaker": speaker, "speech": speech}, prior, timeout, feedback)
                        record["token_usage"].append({"purpose": "state_patch" if not feedback else "state_patch_repair", "usage": meta.get("usage")})
                        record["candidate_patch"] = patch.model_dump()
                        return patch, meta
                    return extract_and_apply(prior, speaker, turn["turn"], extractor, utterance=speech)

                result = commit_guarded_turn(state, generate, assignment, action=selected.name, target_text=target_text, phase=phase, combined_check=combined_check, extract_patch=extract)
                checked = result["compliance"]
                record["compliance_check_result"] = list(checked.checks)
                record["action_fidelity_check_result"] = [{"attempt": item["attempt"], "result": item["action_fidelity"], "reason": item["action_reason"]} for item in checked.checks]
                record["stance_check_result"] = [{"attempt": item["attempt"], "result": item["stance_compliance"], "reason": item["stance_reason"]} for item in checked.checks]
                record["stance_regenerated"] = checked.attempts == 2 and checked.checks[0]["stance_compliance"] in ("AMBIGUOUS", "CONTRADICTS_ASSIGNED")
                record["action_regenerated"] = checked.attempts == 2 and checked.checks[0]["action_fidelity"] in ("MISALIGNED", "UNCLEAR")
                if checked.attempts == 2 and checked.checks[0]["action_fidelity"] == "PARTIALLY_ALIGNED" and not checked.checks[0]["partial_policy"]["accepted"]:
                    record["action_regenerated"] = True
                record["final_utterance"] = result["utterance"]
                if not result["committed"]:
                    record["safe_failure"] = True
                    if result.get("patch_error"):
                        record["patch_validation_result"] = {"valid": False, "issues": result["patch_error"], "attempts": 2}
                    record["moderator_decision"] = "STOP_SAFE_FAILURE"
                    stop_reason = record["moderator_decision"]
                else:
                    candidate = result["state"]
                    record["patch_validation_result"] = result["patch_attempts"]
                    record["applied_patch"] = result["patch_attempts"][-1]["patch"]
                    record["question_extraction_status"] = result["patch_attempts"][-1].get("question_guard")
                    issues = state_integrity_issues(candidate)
                    if issues:
                        record["safe_failure"] = True
                        record["state_integrity_issues"] = issues
                        record["moderator_decision"] = "STOP_SAFE_FAILURE"
                        stop_reason = record["moderator_decision"]
                    else:
                        state = candidate
                        transcript.append({**turn, "speech": checked.utterance})
                        action_history.append((speaker, selected.name, selected.target_ids))
                        events = [e for e in state.question_response_events if e["turn"] == turn["turn"]]
                        question = next((q for q in state.questions if obligation and q.id == obligation["question_id"]), None)
                        record["question_response_status"] = events or ({"question_id": question.id, "status": None, "resolution": question.resolution} if question else None)
                        record["response_status"] = events[-1]["response_status"] if events else None
                        record["novelty_delta"] = {key: len(getattr(state, key)) - len(before[key]) for key in ("propositions", "relations", "questions", "commitment_events")}
                        record["novel_state_change"] = any(record["novelty_delta"].values())
                        operations = record["applied_patch"]["operations"]
                        record["contradiction_used"] = any(op["op"] == "ADD_RELATION" and op["relation_type"] == "CONTRADICTS" for op in operations)
                        record["concession_used"] = any(op["op"] == "CONCEDE_LOCAL" for op in operations)
                        record["revision_used"] = any(op["op"] == "REVISE_PROPOSITION" for op in operations)
                        target_node = next((p for p in state.propositions if p.id == target_id), None)
                        record["callback_used"] = bool(target_node and target_node.turn < turn["turn"] - 1)
                        if turn["turn"] == len(schedule):
                            record["moderator_decision"] = "STOP_HARD_BUDGET"
                            stop_reason = record["moderator_decision"]
            except Exception as exc:
                record["safe_failure"] = True
                record["error"] = f"{type(exc).__name__}: {exc}"
                record["moderator_decision"] = "STOP_SAFE_FAILURE"
                stop_reason = record["moderator_decision"]
            if record["safe_failure"]:
                record["state_unchanged_on_failure"] = state.model_dump() == before
        append_jsonl(log_path, record)
        rows.append(record)
        print(f"integration: {turn['turn']}/{len(schedule)} {phase} {speaker} {record['moderator_decision']}", flush=True)
        if stop_reason:
            break
    purposes = {}
    for row in rows:
        for entry in row["token_usage"]:
            usage = entry["usage"] or {}
            bucket = purposes.setdefault(entry["purpose"], {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
            bucket["calls"] += 1
            bucket["input_tokens"] += usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
            bucket["output_tokens"] += usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
            bucket["total_tokens"] += usage.get("total_tokens", 0) or 0
    summary = {"started_at": datetime.now(timezone.utc).isoformat(), "model": providers["DEBATER_A"]["model"], "motion": scenario["motion"], "completed_turns": sum(bool(r["final_utterance"] and not r["safe_failure"]) for r in rows), "logged_turns": len(rows), "stop_reason": stop_reason, "api_calls": sum(r["provider_call_count"] for r in rows), "input_tokens": sum(item["input_tokens"] for item in purposes.values()), "output_tokens": sum(item["output_tokens"] for item in purposes.values()), "total_tokens": sum(item["total_tokens"] for item in purposes.values()), "tokens_per_turn": round(sum(item["total_tokens"] for item in purposes.values()) / max(1, sum(bool(r["final_utterance"] and not r["safe_failure"]) for r in rows)), 1), "call_breakdown": purposes, "state_integrity_issues": state_integrity_issues(state), "final_state": state.model_dump()}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "target-review.json").write_text(json.dumps(build_target_review_fixture(rows), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded guarded end-to-end debate diagnostic")
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--crossfire-turns", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args(argv)
    scenario = load_scenario(args.scenario)
    providers = select_debaters(load_config(args.env), args.model)
    result = run_integration(scenario, providers, args.output, crossfire_turns=args.crossfire_turns, timeout=args.timeout)
    print(json.dumps({key: result[key] for key in ("completed_turns", "logged_turns", "stop_reason", "api_calls", "total_tokens", "state_integrity_issues")}, ensure_ascii=False))
    return 0 if result["stop_reason"] == "STOP_HARD_BUDGET" else 1


if __name__ == "__main__":
    raise SystemExit(main())
