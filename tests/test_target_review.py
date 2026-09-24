import json
import tempfile
import unittest
from pathlib import Path

from etc.tools.target_review import build_target_review_fixture, save_target_review


class TargetReviewTests(unittest.TestCase):
    def test_fixture_keeps_label_blank_and_lists_other_targets(self):
        rows = [{
            "turn_id": 6, "speaker": "A", "phase": "CROSSFIRE",
            "selected_primary_action": "CHALLENGE_PREMISE", "target_ids": ["C24"],
            "selected_target": {"id": "C24", "text": "선택 대상"},
            "eligible_actions": [
                {"name": "CHALLENGE_PREMISE", "target_ids": ["C24"]},
                {"name": "CHALLENGE_PREMISE", "target_ids": ["C19"]},
                {"name": "REQUEST_SUPPORT", "target_ids": ["C21"]},
            ],
            "final_utterance": "반박",
        }]
        fixture = build_target_review_fixture(rows)
        case = fixture["cases"][0]
        self.assertIsNone(case["human_target_quality"])
        self.assertEqual(case["other_eligible_targets"], ["C19", "C21"])

    def test_human_label_can_be_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            path.write_text(json.dumps({"labels": ["HIGH_VALUE", "REASONABLE", "LOW_VALUE", "DISTRACTING", "INVALID"], "cases": [{"turn_id": 1, "human_target_quality": None, "human_notes": None}]}), encoding="utf-8")
            save_target_review(path, 1, "REASONABLE", "관련은 있음")
            case = json.loads(path.read_text(encoding="utf-8"))["cases"][0]
            self.assertEqual(case["human_target_quality"], "REASONABLE")


if __name__ == "__main__":
    unittest.main()
