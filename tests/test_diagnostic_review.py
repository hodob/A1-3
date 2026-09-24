import json
import tempfile
import unittest
from pathlib import Path

from etc.tools.question_response_review import load_cases, save_human_label
from etc.tools.question_response_eval import require_human_labels, summarize


class DiagnosticReviewTests(unittest.TestCase):
    def test_human_label_is_saved_without_changing_source_label(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cases.json"
            path.write_text(json.dumps({"cases": [{"id": "rr01", "source_human_label": "QUALIFIED", "question": "Q", "response": "A", "new_human_label": None, "rationale": None, "state_premise_evidence": None}]}), encoding="utf-8")
            save_human_label(path, "rr01", "DIRECT", "핵심 답변의 범위가 유지됨")
            case = load_cases(path)[0]
            self.assertEqual(case["new_human_label"], "DIRECT")
            self.assertEqual(case["source_human_label"], "QUALIFIED")
            self.assertEqual(case["rationale"], "핵심 답변의 범위가 유지됨")

    def test_evaluation_refuses_missing_human_label(self):
        with self.assertRaises(ValueError):
            require_human_labels([{"id": "rr01", "new_human_label": None}])

    def test_diagnostic_confusion_is_not_called_accuracy(self):
        rows = [{"case_id": "rr01", "human_label": "DIRECT", "model_label": "QUALIFIED", "match": False, "model_reason": "조건"}, {"case_id": "rr02", "human_label": "QUALIFIED", "model_label": "DIRECT", "match": False, "model_reason": "답변"}]
        result = summarize(rows)
        self.assertEqual(result["exact_match"], 0)
        self.assertEqual(result["confusion_pairs"]["DIRECT → QUALIFIED"], 1)
        self.assertEqual(result["confusion_pairs"]["QUALIFIED → DIRECT"], 1)
        self.assertNotIn("accuracy", result)


if __name__ == "__main__":
    unittest.main()
