"""Human-only review fixture for the bounded quality validation round."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


LABELS = {
    "human_responsiveness": ["GOOD", "PARTIAL", "POOR"],
    "human_target_quality": ["HIGH_VALUE", "REASONABLE", "LOW_VALUE", "DISTRACTING", "INVALID", "NOT_APPLICABLE"],
    "human_state_progress": ["MEANINGFUL", "NONE", "UNCLEAR"],
    "human_repetition": ["NONE", "MINOR", "BAD_LOOP"],
    "human_watchability_proxy": ["ENGAGING", "OK", "DULL"],
}


def build_quality_review_fixture(rows: list[dict], topic: str) -> dict:
    cases = []
    for row in rows:
        cases.append({
            "turn_id": row["turn_id"], "speaker": row.get("speaker"), "phase": row.get("phase"),
            "action": row.get("selected_primary_action"), "selected_target": row.get("selected_target"),
            "utterance": row.get("final_utterance") or row.get("raw_utterance"),
            "action_fidelity": (row.get("action_fidelity_check_result") or [{}])[-1].get("result"),
            "novelty_delta": row.get("novelty_delta"), "safe_failure": row.get("safe_failure", False),
            "human_responsiveness": None, "human_action_fidelity": None, "human_target_quality": None, "human_state_progress": None,
            "human_repetition": None, "human_watchability_proxy": None, "human_persona_observation": None,
            "human_notes": None,
        })
    return {"topic": topic, "labels": LABELS, "review_source": None, "cases": cases}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build a blank quality review fixture")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print", action="store_true", dest="print_cases")
    args = parser.parse_args(argv)
    rows = [json.loads(line) for line in (args.run_dir / "turns.jsonl").read_text(encoding="utf-8").splitlines()]
    fixture = build_quality_review_fixture(rows, json.loads((args.run_dir / "scenario.json").read_text(encoding="utf-8"))["motion"])
    output = args.output or args.run_dir / "quality-review.json"
    output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.print_cases:
        for case in fixture["cases"]:
            target = case["selected_target"] or {}
            print(f"\nT{case['turn_id']} {case['speaker']} {case['phase']} {case['action']} -> {target.get('id')} {target.get('text')}\n{case['utterance']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
