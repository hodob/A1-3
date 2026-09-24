"""One-turn API diagnostic from a saved Action-Target failure fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.debate_engine.action_execution_contracts import CONTRACTS
from src.debate_engine.action_pair_state import evaluate_action_target_pair, filter_available_pairs
from src.debate_engine.action_policy import eligible_actions, select_action_for_speaker
from src.debate_engine.combined_compliance import judge_combined
from src.debate_engine.debate_contracts import DebateState
from src.debate_engine.debate_harness import call_model, load_config, load_scenario, select_debaters, speech_messages
from etc.tools.integrated_debate import commit_guarded_turn, state_integrity_issues
from src.debate_engine.stance_compliance import StanceAssignment
from src.debate_engine.state_harness import call_patch, extract_and_apply


def run(fixture_path: Path, scenario_path: Path, output: Path, *, model: str, env: Path, timeout: float) -> dict:
    if output.exists():
        raise ValueError(f"Output exists: {output}")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    scenario = load_scenario(scenario_path)
    state = DebateState.model_validate(fixture["state"])
    history = [(owner, action, tuple(targets)) for owner, action, targets in fixture["action_history"]]
    speaker = fixture["speaker"]
    turn_id = fixture["turn_id"]
    side_index = 0 if speaker == "A" else 1
    turn = {"turn": turn_id, "phase": "crossfire", "speaker": speaker, "side": scenario["sides"][side_index], "persona": scenario["personas"][side_index]}
    source_rows = [json.loads(line) for line in Path("etc", "runs", fixture["source_run"], "turns.jsonl").read_text(encoding="utf-8").splitlines()]
    transcript = [{"speaker": row["speaker"], "side": row["assigned_stance"], "persona": row["persona_id"], "speech": row["final_utterance"], "phase": row["phase"].lower(), "turn": row["turn_id"]} for row in source_rows if row["turn_id"] < turn_id and row["final_utterance"]]
    provider = select_debaters(load_config(env), model)[f"DEBATER_{speaker}"]

    raw_options = eligible_actions(state, speaker, "crossfire")
    options = filter_available_pairs(state, speaker, raw_options, history, current_turn=turn_id)
    selected = select_action_for_speaker(options, history, speaker, state=state, current_turn=turn_id, persona=turn["persona"])
    if selected is None:
        raise RuntimeError("No eligible action after pair filtering")
    target_id = selected.target_ids[0] if selected.target_ids else None
    target_text = next((p.text for p in state.propositions if p.id == target_id), None)
    pair = evaluate_action_target_pair(state, speaker, selected.name, target_id, history, current_turn=turn_id)
    failed_pair = evaluate_action_target_pair(state, speaker, fixture["action"], fixture["target_id"], history, current_turn=turn_id)
    token_usage = []
    calls = 0
    messages = speech_messages(scenario, turn, transcript)
    contract = CONTRACTS[selected.name]
    messages[1]["content"] += f"\n선택 Action: {selected.name}, target_ids: {list(selected.target_ids)}, target_text: {target_text}. Execution Contract: {contract.required_semantic_effect}"
    open_question = next((q for q in reversed(state.questions) if q.asker != speaker and q.resolution == "OPEN"), None)
    if open_question:
        messages[1]["content"] += f"\n먼저 열린 질문 {open_question.id}에 답하세요: {open_question.core_proposition}"

    def account(purpose, metadata):
        nonlocal calls
        calls += 1
        token_usage.append({"purpose": purpose, "usage": metadata.get("usage")})

    def generate(feedback):
        request_messages = messages if not feedback else [*messages, {"role": "user", "content": feedback}]
        speech, metadata = call_model(provider, request_messages, timeout=timeout)
        account("utterance_generation", metadata)
        return speech

    assignment = StanceAssignment(turn["side"], scenario["sides"][1 - side_index])

    def combined_check(speech, assigned, phase, action, checked_target_text):
        verdict, metadata = judge_combined(provider, action=action, target_id=target_id, target_text=checked_target_text, utterance=speech, assignment=assigned, phase=phase, timeout=timeout)
        account("combined_action_stance_check", metadata)
        return verdict

    def extract(speech, prior):
        def extractor(feedback):
            patch, metadata = call_patch(provider, {"turn": turn_id, "speaker": speaker, "speech": speech}, prior, timeout, feedback)
            account("state_patch_repair" if feedback else "state_patch", metadata)
            return patch, metadata
        return extract_and_apply(prior, speaker, turn_id, extractor, utterance=speech)

    result = commit_guarded_turn(state, generate, assignment, action=selected.name, target_text=target_text, phase="crossfire", combined_check=combined_check, extract_patch=extract)
    after = result["state"]
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for entry in token_usage:
        value = entry["usage"] or {}
        usage["input_tokens"] += value.get("prompt_tokens", value.get("input_tokens", 0)) or 0
        usage["output_tokens"] += value.get("completion_tokens", value.get("output_tokens", 0)) or 0
        usage["total_tokens"] += value.get("total_tokens", 0) or 0
    summary = {
        "source_fixture": fixture_path.as_posix(), "selected_action": selected.name, "selected_target_id": target_id,
        "failed_pair_state": failed_pair.state.value, "selected_pair_state": pair.state.value,
        "committed": result["committed"], "safe_failure": not result["committed"],
        "action_fidelity": result["compliance"].assessment.action_fidelity.value,
        "stance_compliance": result["compliance"].assessment.stance_compliance.value,
        "state_progress": {key: len(getattr(after, key)) - len(getattr(state, key)) for key in ("propositions", "relations", "questions", "commitment_events")},
        "state_integrity_issues": state_integrity_issues(after), "api_calls": calls, **usage,
        "token_usage": token_usage, "checks": list(result["compliance"].checks), "patch_attempts": result.get("patch_attempts", []),
    }
    output.mkdir(parents=True)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=Path("etc/fixtures/action_pair_hotdog_turn6.json"))
    parser.add_argument("--scenario", type=Path, default=Path("etc/scenarios/hotdog.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args(argv)
    result = run(args.fixture, args.scenario, args.output, model=args.model, env=args.env, timeout=args.timeout)
    print(json.dumps({key: result[key] for key in ("selected_action", "selected_target_id", "failed_pair_state", "committed", "safe_failure", "action_fidelity", "state_progress", "state_integrity_issues", "api_calls", "total_tokens")}, ensure_ascii=False))
    return 0 if result["committed"] and not result["state_integrity_issues"] and result["failed_pair_state"] == "RESOLVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
