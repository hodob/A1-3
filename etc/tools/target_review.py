"""Create and edit human Target Quality review fixtures."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile


LABELS = ["HIGH_VALUE", "REASONABLE", "LOW_VALUE", "DISTRACTING", "INVALID"]


def build_target_review_fixture(rows: list[dict]) -> dict:
    cases = []
    for row in rows:
        target_ids = row.get("target_ids") or []
        if not target_ids:
            continue
        selected_id = target_ids[0]
        other = []
        for option in row.get("eligible_actions", []):
            for target_id in option.get("target_ids", []):
                if target_id != selected_id and target_id not in other:
                    other.append(target_id)
        selected = row.get("selected_target") or {"id": selected_id, "text": None}
        cases.append({
            "turn_id": row["turn_id"], "speaker": row.get("speaker"), "phase": row.get("phase"),
            "action": row.get("selected_primary_action"), "selected_target_id": selected_id,
            "selected_target_text": selected.get("text"), "other_eligible_targets": other,
            "utterance": row.get("final_utterance"), "target_quality_metadata": row.get("target_quality_metadata"),
            "human_target_quality": None, "human_notes": None,
        })
    return {"labels": LABELS, "cases": cases}


def save_target_review(path: Path, turn_id: int, label: str, notes: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if label not in data["labels"]:
        raise ValueError(f"Unknown label: {label}")
    case = next((item for item in data["cases"] if item["turn_id"] == turn_id), None)
    if case is None:
        raise ValueError(f"Unknown turn: {turn_id}")
    case["human_target_quality"] = label
    case["human_notes"] = notes.strip() or None
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".json") as handle:
        temp = Path(handle.name)
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp, path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Human Target Quality review")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args(argv)
    data = json.loads(args.fixture.read_text(encoding="utf-8"))
    for case in data["cases"]:
        print(f"\nTurn {case['turn_id']}\n\nAction:\n{case['action']}\n\nSelected Target:\n{case['selected_target_id']}: {case['selected_target_text']}\n\nOther eligible targets:\n{', '.join(case['other_eligible_targets']) or '(none)'}")
        if not args.interactive:
            continue
        print("\n".join(f"[{index}] {label}" for index, label in enumerate(data["labels"], 1)))
        choice = input("Label number/name (Enter=skip): ").strip().upper()
        if not choice:
            continue
        label = data["labels"][int(choice) - 1] if choice.isdigit() else choice
        save_target_review(args.fixture, case["turn_id"], label, input("Notes: "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
