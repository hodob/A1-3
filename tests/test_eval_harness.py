import unittest

from etc.tools.eval_harness import score_predictions, validate_tool_arguments


class EvalHarnessTests(unittest.TestCase):
    def test_tool_arguments_are_validated_even_with_strict_true(self):
        schema = {"type": "object", "properties": {"label": {"type": "string", "enum": ["SAME", "REVISION"]}}, "required": ["label"], "additionalProperties": False}
        self.assertEqual(validate_tool_arguments('{"label":"SAME"}', schema), {"label": "SAME"})
        for bad in ('{"label":"UNKNOWN"}', '{"label":"SAME","extra":1}', '{"label":1}', 'not json'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_tool_arguments(bad, schema)

    def test_score_counts_false_merges_without_shared_expected_constant(self):
        cases = [
            {"id": "one", "gold": "SAME"},
            {"id": "two", "gold": "RELATED_NEW"},
            {"id": "three", "gold": "CONTRADICTION"},
        ]
        predictions = {"one": "SAME", "two": "SAME", "three": None}
        result = score_predictions(cases, predictions, same_label="SAME")
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["attempted"], 2)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["false_merges"], 1)
        self.assertEqual(result["missing"], 1)


if __name__ == "__main__":
    unittest.main()
