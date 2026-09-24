"""Small real-provider State Patch probe; invalid first candidates are explicit fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.debate_engine.debate_contracts import DebateState, PatchValidationError, apply_patch
from src.debate_engine.debate_harness import load_config, select_debaters
from src.debate_engine.state_harness import call_patch, extract_and_apply


def run_steps(steps: list[dict], provider: dict, timeout: float) -> dict:
    state = DebateState()
    rows = []
    api_calls = 0
    usages = []

    def call(step: dict, feedback: list[dict]):
        nonlocal api_calls
        api_calls += 1
        prompt_turn = {key: step[key] for key in ("speaker", "turn", "speech") if key in step}
        patch, meta = call_patch(provider, prompt_turn, state, timeout, feedback)
        usages.append(meta.get("usage"))
        return patch, meta

    for step in steps:
        before = state.model_dump()
        row = {"case_id": step["id"]}
        if "candidate" in step:
            try:
                apply_patch(state, step["candidate"], speaker=step["speaker"], turn=step["turn"])
                row.update({"passed": False, "error": "invalid candidate was accepted"})
            except PatchValidationError as exc:
                row.update({"passed": state.model_dump() == before and exc.issues[0].code == step["expected_error"], "issues": [issue.as_dict() for issue in exc.issues], "state_unchanged": state.model_dump() == before, "source": "injected_invalid_fixture"})
        elif "first_candidate" in step:
            returned = []

            def extractor(feedback):
                if not feedback:
                    return step["first_candidate"], {"source": "injected_invalid_fixture"}
                result = call(step, feedback)
                returned.append(result[0].model_dump())
                return result

            try:
                candidate, attempts = extract_and_apply(state, step["speaker"], step["turn"], extractor)
                repaired_ops = [op["op"] for op in returned[-1]["operations"]]
                if step.get("expected_safe_failure"):
                    row.update({"passed": False, "repair_result": "valid_patch_returned", "actual_ops": repaired_ops, "state_unchanged": state.model_dump() == before, "attempts": attempts})
                else:
                    passed = step["expected_repaired_op"] in repaired_ops and state.model_dump() == before
                    row.update({"passed": passed, "repair_result": "success" if passed else "unexpected_patch", "actual_ops": repaired_ops, "attempts": attempts})
                    if passed:
                        state = candidate
            except PatchValidationError as exc:
                row.update({"passed": bool(step.get("expected_safe_failure")) and state.model_dump() == before, "repair_result": "safe_failure", "issues": [issue.as_dict() for issue in exc.issues], "state_unchanged": state.model_dump() == before, "attempts": 2})
        else:
            patch, meta = call(step, [])
            ops = [op.op for op in patch.operations]
            if step["expected_op"] in ops:
                candidate = apply_patch(state, patch, speaker=step["speaker"], turn=step["turn"])
                revision_ok = True
                if step["id"] == "revision":
                    revision_ok = len(candidate.propositions) > len(state.propositions) and candidate.propositions[0].text == state.propositions[0].text and candidate.commitment_events[-1].event == "REVISE"
                row.update({"passed": revision_ok, "actual_ops": ops, "metadata": meta, "revision_preserved_old": revision_ok if step["id"] == "revision" else None})
                if revision_ok:
                    state = candidate
            else:
                row.update({"passed": False, "actual_ops": ops, "error": "expected operation absent", "metadata": meta})
        rows.append(row)
    return {"model": provider["model"], "capabilities": {"supports_tool_calling": True, "supports_forced_tool_call": False, "supports_json_schema": False}, "api_calls": api_calls, "usage_by_call": usages, "rows": rows, "final_state": state.model_dump()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Minimal real API State Patch diagnostic")
    parser.add_argument("--fixture", type=Path, default=Path("etc/fixtures/state_patch_diagnostic.json"))
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError(f"Output exists: {args.output}")
    provider = select_debaters(load_config(args.env), args.model)["DEBATER_A"]
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    result = run_steps(fixture["steps"], provider, args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"api_calls": result["api_calls"], "rows": [{key: value for key, value in row.items() if key not in ("metadata", "attempts")} for row in result["rows"]]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
