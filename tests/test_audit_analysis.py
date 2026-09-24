import unittest

from etc.tools.audit_analysis import summarize_action_audit, summarize_proposition_audit


class AuditAnalysisTests(unittest.TestCase):
    def test_action_summary_counts_labels(self):
        result = summarize_action_audit([{"human_action_fidelity": "ALIGNED"}, {"human_action_fidelity": "MISALIGNED"}])
        self.assertEqual(result["reviewed"], 2)
        self.assertEqual(result["counts"]["MISALIGNED"], 1)

    def test_proposition_summary_counts_secondary_issue_types(self):
        cases = [{"turn_id": 1, "human_extraction_label": "DUPLICATE", "human_issue_type": ["DUPLICATE", "UNDER_SPLIT"]}, {"turn_id": 1, "human_extraction_label": "VALID", "human_issue_type": []}]
        result = summarize_proposition_audit(cases)
        self.assertEqual(result["valid_proposition_count"], 1)
        self.assertEqual(result["issue_counts"]["UNDER_SPLIT"], 1)
        self.assertEqual(result["unique_canonical_propositions_per_turn"]["1"], 1)


if __name__ == "__main__":
    unittest.main()
