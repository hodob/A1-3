"""Reconstruct the two known Action-Target failure states from saved logs."""

from __future__ import annotations

import json
from pathlib import Path

from src.debate_engine.debate_contracts import DebateState, apply_patch


CASES = [
    ("quality-definition-hotdog-v1", 6, "action_pair_hotdog_turn6.json", "REQUEST_SUPPORT", "C1"),
    ("quality-policy-attendance-v1", 7, "action_pair_attendance_turn7.json", "REQUEST_SUPPORT", "C13"),
]


def migrate_saved_patch(state: DebateState, patch: dict) -> dict:
    """Translate historical guessed C refs into Patch-local refs for replay."""
    operations = [dict(operation) for operation in patch["operations"]]
    predicted_to_temp = {}
    next_number = len(state.propositions) + 1
    temp_number = 1
    for operation in operations:
        if operation["op"] != "ADD_PROPOSITION":
            continue
        temp_id = f"P{temp_number}"
        temp_number += 1
        operation["temp_id"] = temp_id
        predicted_to_temp[f"C{next_number}"] = temp_id
        next_number += 1
    for operation in operations:
        if operation["op"] != "ADD_RELATION":
            continue
        source = operation.pop("from_proposition_id")
        target = operation.pop("to_proposition_id")
        operation["from_proposition_ref"] = predicted_to_temp.get(source, source)
        operation["to_proposition_ref"] = predicted_to_temp.get(target, target)
    return {"operations": operations}


def main() -> int:
    for run_name, failing_turn, fixture_name, action, target_id in CASES:
        rows = [json.loads(line) for line in Path("etc", "runs", run_name, "turns.jsonl").read_text(encoding="utf-8").splitlines()]
        state = DebateState()
        history = []
        for row in rows:
            if row["turn_id"] >= failing_turn:
                break
            patch = row.get("applied_patch")
            if patch:
                state = apply_patch(state, migrate_saved_patch(state, patch), speaker=row["speaker"], turn=row["turn_id"])
                history.append([row["speaker"], row["selected_primary_action"], row["target_ids"]])
        source = next(row for row in rows if row["turn_id"] == failing_turn)
        fixture = {
            "source_run": run_name, "turn_id": failing_turn, "speaker": source["speaker"],
            "action": action, "target_id": target_id, "expected_pair_state": "RESOLVED",
            "state": state.model_dump(), "action_history": history,
        }
        Path("etc", "fixtures", fixture_name).write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
