"""Interactive, label-free review utility for action and proposition fixtures."""

import argparse
import json
import os
from pathlib import Path
import tempfile


def load_audit(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_review(path: Path, case_id: str, label: str, notes: str, issues: list[str] | None = None) -> None:
    data = load_audit(path)
    if label not in data["labels"]:
        raise ValueError(f"Unknown label: {label}")
    key = "turn_id" if any("turn_id" in case and "selected_action" in case for case in data["cases"]) else "proposition_id"
    normalized = int(case_id) if key == "turn_id" else case_id
    case = next((case for case in data["cases"] if case[key] == normalized), None)
    if case is None:
        raise ValueError(f"Unknown case: {case_id}")
    if key == "turn_id":
        case["human_action_fidelity"] = label
    else:
        case["human_extraction_label"] = label
        case["human_issue_type"] = issues or []
    case["human_notes"] = notes.strip() or None
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".json") as handle:
        temp = Path(handle.name)
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp, path)


def _show(case: dict) -> None:
    if "selected_action" in case:
        print(f"\nTurn {case['turn_id']} / Action {case['selected_action']}\nTarget {case['target_id']}: {case['target_text']}\nUtterance:\n{case['utterance']}")
    else:
        print(f"\n{case['proposition_id']} / Turn {case['turn_id']} / {case['speaker']}\nSource:\n{case['source_utterance']}\nExtracted:\n{case['extracted_text']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Human audit utility")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args(argv)
    data = load_audit(args.fixture)
    for case in data["cases"]:
        _show(case)
        if not args.interactive:
            continue
        print("\n".join(f"[{index}] {label}" for index, label in enumerate(data["labels"], 1)))
        label = input("Label number/name (Enter=skip): ").strip().upper()
        if not label:
            continue
        if label.isdigit():
            label = data["labels"][int(label) - 1]
        notes = input("Notes: ").strip()
        issues = input("Issue types comma-separated: ").strip().split(",") if "proposition_id" in case else []
        save_review(args.fixture, str(case.get("turn_id", case.get("proposition_id"))), label, notes, [x.strip() for x in issues if x.strip()])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
