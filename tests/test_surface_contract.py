import unittest

from src.debate_engine.debate_contracts import DebateState, Proposition, Question
from src.debate_engine.surface_contract import extract_state_references, validate_surface


class SurfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.state = DebateState(
            propositions=[
                Proposition(id="C1", text="첫 주장", speaker="A", turn=1),
                Proposition(id="C2", text="두 번째 주장", speaker="B", turn=2),
            ],
            questions=[
                Question(
                    id="Q1",
                    asker="A",
                    text="왜 그런가?",
                    core_proposition="근거를 설명하라.",
                    target_proposition_id="C2",
                    turn=3,
                    source_turn_id=3,
                )
            ],
        )
        self.ids = {"C1", "C2", "Q1"}

    def test_reference_marker_is_valid_and_raw_id_is_not(self):
        self.assertEqual(validate_surface("앞서 [[C1]]의 기준을 보겠습니다.", phase="crossfire", allowed_reference_ids=self.ids), [])
        issues = validate_surface("앞서 C1의 기준을 보겠습니다.", phase="crossfire", allowed_reference_ids=self.ids)
        self.assertEqual([x.code for x in issues], ["RAW_STATE_ID_LEAK"])

    def test_unknown_reference_is_rejected(self):
        issues = validate_surface("[[C99]]를 다시 보죠.", phase="crossfire", allowed_reference_ids=self.ids)
        self.assertEqual([x.code for x in issues], ["UNKNOWN_STATE_REFERENCE"])

    def test_readability_markdown_is_allowed(self):
        utterance = "**핵심 기준**은 두 가지입니다.\n\n- 첫째\n- 둘째\n\n> 상대가 말한 기준"
        self.assertEqual(validate_surface(utterance, phase="rebuttal", allowed_reference_ids=self.ids), [])

    def test_document_style_markdown_is_rejected(self):
        cases = [
            "# 제목\n내용",
            "```text\ncode\n```",
            "[외부 링크](https://example.com)",
            "| A | B |\n|---|---|\n|1|2|",
            "<div>html</div>",
        ]
        for utterance in cases:
            with self.subTest(utterance=utterance):
                issues = validate_surface(utterance, phase="rebuttal", allowed_reference_ids=self.ids)
                self.assertIn("MARKDOWN_DISALLOWED_ELEMENT", [x.code for x in issues])

    def test_final_focus_is_stricter_than_other_phases(self):
        issues = validate_surface("- 하나\n- 둘", phase="final_focus", allowed_reference_ids=self.ids)
        self.assertIn("FINAL_FOCUS_FORMAT", [x.code for x in issues])
        issues = validate_surface("하나입니다. 둘입니다. 셋입니다.", phase="final_focus", allowed_reference_ids=self.ids)
        self.assertIn("FINAL_FOCUS_LENGTH", [x.code for x in issues])
        issues = validate_surface("그래서 무엇이 더 중요한가요?", phase="final_focus", allowed_reference_ids=self.ids)
        self.assertIn("FINAL_FOCUS_QUESTION", [x.code for x in issues])

    def test_extract_references_preserves_first_occurrence_order(self):
        refs = extract_state_references("[[C2]]와 [[Q1]], 다시 [[C2]]", self.state)
        self.assertEqual([x["id"] for x in refs], ["C2", "Q1"])
        self.assertEqual(refs[0]["speaker"], "B")
        self.assertEqual(refs[0]["turn"], 2)
        self.assertEqual(refs[1]["turn"], 3)


if __name__ == "__main__":
    unittest.main()
