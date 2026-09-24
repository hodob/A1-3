import unittest

from etc.tools.quality_review import build_quality_review_fixture


class QualityReviewTests(unittest.TestCase):
    def test_quality_fixture_never_auto_labels_human_axes(self):
        rows = [{"turn_id": 1, "speaker": "A", "phase": "OPENING", "final_utterance": "발언", "selected_primary_action": "EXTEND_ARGUMENT", "selected_target": None}]
        case = build_quality_review_fixture(rows, "topic")["cases"][0]
        for field in ("human_responsiveness", "human_action_fidelity", "human_target_quality", "human_state_progress", "human_repetition", "human_watchability_proxy", "human_persona_observation"):
            self.assertIsNone(case[field])


if __name__ == "__main__":
    unittest.main()
