"""Offline-only persona evidence index and tempo extraction from saved runs."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


QUALITY_RUNS = [
    "quality-playful-tangsuyuk-v1",
    "quality-definition-hotdog-v1",
    "quality-policy-attendance-v1",
    "quality-comparison-remote-v1",
]


def turn_tempo(row: dict, review: dict, previous_pairs: set, previous_targets: set) -> dict:
    operations = (row.get("applied_patch") or {}).get("operations", [])
    pair = (row.get("selected_primary_action"), tuple(row.get("target_ids") or []))
    targets = tuple(row.get("target_ids") or [])
    result = {
        "turn_id": row["turn_id"],
        "meaningful_state_change": review["human_state_progress"] == "MEANINGFUL",
        "new_clash": sum(op["op"] == "ADD_RELATION" and op["relation_type"] in ("ATTACKS", "CONTRADICTS") for op in operations),
        "new_support": sum(op["op"] == "ADD_RELATION" and op["relation_type"] == "SUPPORTS" for op in operations),
        "question_resolution": sum(op["op"] == "ANSWER_QUESTION" and op["resolution"] == "RESOLVED" for op in operations),
        "commitment_change": sum(op["op"] in ("CONCEDE_LOCAL", "REVISE_PROPOSITION", "WITHDRAW_PROPOSITION") for op in operations),
        "concession": sum(op["op"] == "CONCEDE_LOCAL" for op in operations),
        "revision": sum(op["op"] == "REVISE_PROPOSITION" for op in operations),
        "new_counterexample": int(row.get("selected_primary_action") == "TEST_BOUNDARY"),
        "new_qualification": sum((op["op"] == "ADD_RELATION" and op["relation_type"] == "QUALIFIES") or op["op"] == "REVISE_PROPOSITION" or (op["op"] == "ANSWER_QUESTION" and op["response_status"] == "QUALIFIED") for op in operations),
        "repeated_action_target": bool(targets and pair in previous_pairs),
        "repeated_clash": bool(targets and any(target in previous_targets for target in targets)),
        "safe_failure": row.get("safe_failure", False),
    }
    if targets:
        previous_pairs.add(pair)
    previous_targets.update(targets)
    return result


def analyze(root: Path = Path("etc/runs")) -> dict:
    result = {"method": "offline existing-log analysis; no API", "topics": {}}
    for run_name in QUALITY_RUNS:
        run_dir = root / run_name
        rows = [json.loads(line) for line in (run_dir / "turns.jsonl").read_text(encoding="utf-8").splitlines()]
        reviewed = json.loads((root / "quality-validation-v1" / f"{run_name}-quality-reviewed.json").read_text(encoding="utf-8"))
        reviews = {case["turn_id"]: case for case in reviewed["cases"]}
        previous_pairs: set = set()
        previous_targets: set = set()
        turns = [turn_tempo(row, reviews[row["turn_id"]], previous_pairs, previous_targets) for row in rows]
        result["topics"][run_name] = {
            "motion": json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))["motion"],
            "turns": turns,
            "counts": {
                "meaningful": sum(turn["meaningful_state_change"] for turn in turns),
                "non_meaningful": sum(not turn["meaningful_state_change"] for turn in turns),
                "new_clash": sum(turn["new_clash"] for turn in turns),
                "new_support": sum(turn["new_support"] for turn in turns),
                "question_resolution": sum(turn["question_resolution"] for turn in turns),
                "commitment_change": sum(turn["commitment_change"] for turn in turns),
                "repeated_action_target": sum(turn["repeated_action_target"] for turn in turns),
                "repeated_clash": sum(turn["repeated_clash"] for turn in turns),
            },
        }
    return result


def main() -> int:
    output = Path("etc/runs/persona-tempo-validation-v1")
    output.mkdir(parents=True, exist_ok=True)
    data = analyze()
    (output / "tempo.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: value["counts"] for name, value in data["topics"].items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
