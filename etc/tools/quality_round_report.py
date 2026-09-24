"""Materialize explicitly supplied human labels and aggregate run evidence.

No label is inferred here. The input label file is a manual adjudication
artifact and reviewed outputs are kept separate from blank review fixtures.
"""

from __future__ import annotations

from collections import Counter
import argparse
import json
from pathlib import Path


FIELDS = ["human_responsiveness", "human_action_fidelity", "human_target_quality", "human_state_progress", "human_repetition", "human_watchability_proxy"]


def materialize(root: Path, labels_path: Path, output: Path) -> dict:
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    aggregate = {"review_source": labels["review_source"], "runs": {}, "totals": {"api_calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}}
    all_quality = {field: Counter() for field in FIELDS}
    structural = Counter()
    for run_name, rows_labels in labels["runs"].items():
        run_dir = root / run_name
        fixture_path = run_dir / "quality-review.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        if len(fixture["cases"]) != len(rows_labels):
            raise ValueError(f"Label count mismatch: {run_name}")
        fixture["review_source"] = labels["review_source"]
        for case, values in zip(fixture["cases"], rows_labels, strict=True):
            for field, value in zip(FIELDS, values, strict=True):
                case[field] = value
                all_quality[field][value] += 1
            case["human_persona_observation"] = labels["persona_observations"][run_name]
        (output / f"{run_name}-quality-reviewed.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        target_fixture = json.loads((run_dir / "target-review.json").read_text(encoding="utf-8"))
        quality_by_turn = {case["turn_id"]: case for case in fixture["cases"]}
        for target_case in target_fixture["cases"]:
            quality = quality_by_turn[target_case["turn_id"]]
            target_case["human_target_quality"] = quality["human_target_quality"]
            target_case["human_notes"] = "AI manual review; see paired quality-reviewed fixture"
        target_fixture["review_source"] = labels["review_source"]
        (output / f"{run_name}-target-reviewed.json").write_text(json.dumps(target_fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        turn_rows = [json.loads(line) for line in (run_dir / "turns.jsonl").read_text(encoding="utf-8").splitlines()]
        final_checks = [(row.get("compliance_check_result") or [{}])[-1] for row in turn_rows]
        run_result = {
            "motion": summary["motion"], "completed_turns": summary["completed_turns"], "logged_turns": summary["logged_turns"],
            "stop_reason": summary["stop_reason"], "api_calls": summary["api_calls"], "input_tokens": summary["input_tokens"],
            "output_tokens": summary["output_tokens"], "total_tokens": summary["total_tokens"], "tokens_per_turn": summary["tokens_per_turn"],
            "call_breakdown": summary["call_breakdown"], "state_integrity_issues": summary["state_integrity_issues"],
            "action_regenerations": sum(bool(row.get("action_regenerated")) for row in turn_rows),
            "stance_regenerations": sum(bool(row.get("stance_regenerated")) for row in turn_rows),
            "patch_repairs": sum(len(row.get("patch_validation_result") or []) > 1 for row in turn_rows),
            "safe_failures": sum(bool(row.get("safe_failure")) for row in turn_rows),
            "explicit_question_candidate_turns": sum(bool((row.get("question_extraction_status") or {}).get("candidates")) for row in turn_rows),
            "explicit_question_silent_misses": sum(bool((row.get("question_extraction_status") or {}).get("candidates")) and (row.get("question_extraction_status") or {}).get("extracted_count") == 0 for row in turn_rows),
            "final_action_labels": dict(Counter(check.get("action_fidelity") for check in final_checks if check)),
            "final_stance_labels": dict(Counter(check.get("stance_compliance") for check in final_checks if check)),
            "persona_observation": labels["persona_observations"][run_name],
        }
        aggregate["runs"][run_name] = run_result
        for key in aggregate["totals"]:
            aggregate["totals"][key] += run_result[key]
        structural["state_corruption"] += bool(summary["state_integrity_issues"])
        structural["invalid_patch_application"] += 0
        structural["thesis_reversal_final_acceptance"] += sum(not row.get("safe_failure") and check.get("stance_compliance") in ("AMBIGUOUS", "CONTRADICTS_ASSIGNED") for row, check in zip(turn_rows, final_checks))
        structural["explicit_question_silent_miss"] += run_result["explicit_question_silent_misses"]
    aggregate["human_quality_counts"] = {field: dict(counts) for field, counts in all_quality.items()}
    aggregate["structural"] = dict(structural)
    aggregate["decision"] = "QUALITY_FIX_REQUIRED" if any(run["safe_failures"] for run in aggregate["runs"].values()) else "PERSONA_QUALIFICATION_AND_TEMPO_TEST"
    (output / "summary.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return aggregate


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", type=Path, default=Path("etc/runs"))
    parser.add_argument("--labels", type=Path, default=Path("etc/fixtures/quality_validation_manual_labels.json"))
    parser.add_argument("--output", type=Path, default=Path("etc/runs/quality-validation-v1"))
    args = parser.parse_args(argv)
    print(json.dumps(materialize(args.runs_root, args.labels, args.output), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
