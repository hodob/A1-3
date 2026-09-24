import hashlib
import json
from pathlib import Path
import unittest

from src.debate_engine.stance_compliance import StanceAssignment, StanceLabel, validate_utterance


class StanceDiagnosticTests(unittest.TestCase):
    def test_historical_fixture_is_self_contained_and_fingerprint_locked(self):
        fixture = json.loads(Path("etc/fixtures/stance_diagnostic.json").read_text(encoding="utf-8"))
        case = fixture["cases"][-1]
        self.assertIn("v1-persona-hotdog/swapped.jsonl turn 19", case["source"])
        digest = hashlib.sha256(case["utterance"].encode("utf-8")).hexdigest()
        self.assertEqual(digest, case["source_sha256"])

    def test_local_concession_is_compatible(self):
        case = json.loads(Path("etc/fixtures/stance_diagnostic.json").read_text(encoding="utf-8"))["cases"][0]
        result = validate_utterance(case["utterance"], StanceAssignment(case["assigned_thesis"], case["opposing_thesis"]), phase=case["phase"])
        self.assertEqual(result.label, StanceLabel.COMPATIBLE_WITH_ASSIGNED)

    def test_ambiguous_ending_not_committed(self):
        case = json.loads(Path("etc/fixtures/stance_diagnostic.json").read_text(encoding="utf-8"))["cases"][1]
        result = validate_utterance(case["utterance"], StanceAssignment(case["assigned_thesis"], case["opposing_thesis"]), phase=case["phase"])
        self.assertEqual(result.label, StanceLabel.AMBIGUOUS)
        self.assertFalse(result.accepted)

    def test_explicit_reversal_is_contradiction(self):
        case = json.loads(Path("etc/fixtures/stance_diagnostic.json").read_text(encoding="utf-8"))["cases"][2]
        result = validate_utterance(case["utterance"], StanceAssignment(case["assigned_thesis"], case["opposing_thesis"]), phase=case["phase"])
        self.assertEqual(result.label, StanceLabel.CONTRADICTS_ASSIGNED)
        self.assertFalse(result.accepted)


if __name__ == "__main__":
    unittest.main()
