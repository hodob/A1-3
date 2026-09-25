import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TangsuyukRepetitionFixtureTests(unittest.TestCase):
    def test_fixture_covers_all_14_observed_turns_and_distinguishes_valid_crystallization(self):
        data = json.loads((ROOT / "etc" / "fixtures" / "tangsuyuk_repetition_14turn.json").read_text(encoding="utf-8"))
        self.assertEqual([x["turn"] for x in data["turns"]], list(range(1, 15)))
        self.assertIn("NEW_COUNTEREXAMPLE", data["turns"][7]["label"])
        self.assertIn("REPHRASE_DOMINANT", data["turns"][10]["label"])
        self.assertIn("FINAL_CRYSTALLIZE_ALLOWED", data["turns"][12]["label"])
        self.assertIn("FINAL_CRYSTALLIZE_ALLOWED", data["turns"][13]["label"])

    def test_fixture_preserves_audience_grounding_failure_as_separate_regression(self):
        data = json.loads((ROOT / "etc" / "fixtures" / "tangsuyuk_repetition_14turn.json").read_text(encoding="utf-8"))
        self.assertEqual(data["audience_input"], "볶는다는 것도 있어")
        self.assertIn("AUDIENCE_NOT_GROUNDED", data["turns"][8]["label"])
        self.assertIn("AUDIENCE_NOT_GROUNDED", data["turns"][9]["label"])


if __name__ == "__main__":
    unittest.main()
