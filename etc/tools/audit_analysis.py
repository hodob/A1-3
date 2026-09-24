"""Summaries of completed manual audit fixtures."""

from collections import Counter, defaultdict


def summarize_action_audit(cases: list[dict]) -> dict:
    counts = Counter(case.get("human_action_fidelity") for case in cases if case.get("human_action_fidelity"))
    return {"reviewed": sum(counts.values()), "counts": dict(counts), "problem_turns": [case["turn_id"] for case in cases if "turn_id" in case and case.get("human_action_fidelity") in ("MISALIGNED", "PARTIALLY_ALIGNED", "UNCLEAR")]}


def summarize_proposition_audit(cases: list[dict]) -> dict:
    primary = Counter(case.get("human_extraction_label") for case in cases if case.get("human_extraction_label"))
    issues = Counter(issue for case in cases for issue in case.get("human_issue_type", []))
    valid_per_turn = Counter(str(case["turn_id"]) for case in cases if case.get("human_extraction_label") == "VALID")
    canonical_per_turn = Counter(str(case["turn_id"]) for case in cases if case.get("human_extraction_label") == "VALID")
    return {
        "reviewed": sum(primary.values()), "primary_label_counts": dict(primary),
        "valid_proposition_count": primary.get("VALID", 0), "invalid_count": primary.get("INVALID", 0),
        "duplicate_count": primary.get("DUPLICATE", 0), "over_split_count": issues.get("OVER_SPLIT", 0),
        "under_split_count": issues.get("UNDER_SPLIT", 0),
        "scope_or_polarity_errors": issues.get("WRONG_SCOPE", 0) + issues.get("WRONG_POLARITY", 0),
        "issue_counts": dict(issues), "valid_propositions_per_turn": dict(sorted(valid_per_turn.items(), key=lambda item: int(item[0]))),
        "unique_canonical_propositions_per_turn": dict(sorted(canonical_per_turn.items(), key=lambda item: int(item[0]))),
    }
