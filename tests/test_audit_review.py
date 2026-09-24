import json
import tempfile
from pathlib import Path
import unittest

from etc.tools.audit_review import load_audit, save_review


class AuditReviewTests(unittest.TestCase):
    def test_action_fixture_preserves_turn_four(self):
        cases = load_audit(Path("etc/fixtures/action_fidelity_audit.json"))["cases"]
        case = cases[3]
        self.assertEqual(case["turn_id"], 4)
        self.assertEqual(case["selected_action"], "CHALLENGE_PREMISE")
        self.assertEqual(case["target_id"], "C14")
        self.assertIsNone(case["human_action_fidelity"])

    def test_proposition_fixture_contains_all_51_unlabelled(self):
        cases = load_audit(Path("etc/fixtures/proposition_extraction_audit.json"))["cases"]
        self.assertEqual(len(cases), 51)
        self.assertTrue(all(case["human_extraction_label"] is None for case in cases))

    def test_review_save_changes_only_requested_case(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "review.json"
            path.write_text(json.dumps({"labels": ["VALID"], "cases": [{"proposition_id": "C1", "human_extraction_label": None, "human_issue_type": [], "human_notes": None}]}), encoding="utf-8")
            save_review(path, "C1", "VALID", "정확함", [])
            case = load_audit(path)["cases"][0]
            self.assertEqual(case["human_extraction_label"], "VALID")
            self.assertEqual(case["human_notes"], "정확함")


if __name__ == "__main__":
    unittest.main()
