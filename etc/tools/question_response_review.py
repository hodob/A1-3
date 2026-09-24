"""Human review of the six existing debate responses; never assigns labels automatically."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from src.debate_engine.question_rubric import ResponseLabel


DEFAULT_FIXTURE = Path(__file__).parents[1] / "fixtures" / "question_response_reannotation.json"
RUBRIC = Path(__file__).parents[2] / "docs" / "contracts" / "QUESTION_RESPONSE_RUBRIC.md"
LABELS = {label.value for label in ResponseLabel}


def load_cases(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"]
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Duplicate case IDs")
    return cases


def save_human_label(path: Path, case_id: str, label: str, rationale: str, state_premise_evidence: str | None = None) -> None:
    if label not in LABELS:
        raise ValueError(f"Unknown label: {label}")
    if not rationale.strip():
        raise ValueError("Human rationale is required")
    if label == "FRAME_REJECTED_VALID" and not (state_premise_evidence or "").strip():
        raise ValueError("FRAME_REJECTED_VALID requires State conflict evidence")
    data = json.loads(path.read_text(encoding="utf-8"))
    case = next((item for item in data["cases"] if item["id"] == case_id), None)
    if case is None:
        raise ValueError(f"Unknown case: {case_id}")
    case["new_human_label"] = label
    case["rationale"] = rationale.strip()
    case["state_premise_evidence"] = state_premise_evidence.strip() if state_premise_evidence else None
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".question-review-", suffix=".json", delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def display(path: Path) -> None:
    print(RUBRIC.read_text(encoding="utf-8"))
    for case in load_cases(path):
        print(f"\n[{case['id']}] 질문: {case['question']}\n답변: {case['response']}\n새 human label: {case['new_human_label'] or '(미입력)'}")


def main(argv: list[str] | None = None) -> int:
    if sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Review the six real question responses")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--set", nargs=2, metavar=("CASE_ID", "LABEL"))
    parser.add_argument("--reason")
    parser.add_argument("--state-evidence")
    args = parser.parse_args(argv)
    if args.set:
        save_human_label(args.fixture, args.set[0], args.set[1], args.reason or "", args.state_evidence)
        print(f"저장: {args.set[0]} = {args.set[1]}")
        return 0
    display(args.fixture)
    if args.interactive:
        for case in load_cases(args.fixture):
            if case["new_human_label"] is not None:
                continue
            print(f"\n[{case['id']}] 질문: {case['question']}\n답변: {case['response']}")
            label = input("Label (Enter=건너뛰기): ").strip().upper()
            if not label:
                continue
            reason = input("판정 근거: ").strip()
            evidence = input("State 전제 충돌 근거: ").strip() if label == "FRAME_REJECTED_VALID" else None
            save_human_label(args.fixture, case["id"], label, reason, evidence)
            print("저장됨")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
