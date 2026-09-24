from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    def test_three_navigable_sections_exist(self):
        html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        for section_id in ("home", "debate", "how-it-works"):
            self.assertRegex(html, rf'id=["\']{section_id}["\']')
            self.assertRegex(html, rf'href=["\']#{section_id}["\']')

    def test_frontend_calls_relative_api_routes(self):
        js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        self.assertIn("'/api/analyze-topic'", js)
        self.assertIn("'/api/debate-step'", js)
        self.assertIn("fetch(path", js)
        self.assertNotRegex(js, r"https?://[^\"']+/api/")

    def test_loading_error_and_empty_input_copy_exist(self):
        js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        for phrase in ("주제를 분석하고 있습니다", "토론할 주제를 입력해주세요", "응답을 생성하지 못했습니다"):
            self.assertIn(phrase, js)

    def test_context_summary_is_sent_to_motion_endpoint(self):
        js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        self.assertIn("context_summary", js)
        self.assertIn("/api/create-motion", js)

    def test_context_review_and_free_text_controls_exist(self):
        js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        self.assertIn("직접 확인", js)
        self.assertIn("전달된 주장", js)
        self.assertIn("사용자의 해석", js)
        self.assertIn("직접 입력", js)

    def test_summary_displays_agreements(self):
        js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        self.assertIn("합의한 부분", js)
        self.assertIn("data.agreements", js)

    def test_frontend_has_timeout_abort_path(self):
        js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        self.assertIn("AbortController", js)
        self.assertIn("응답이 지연되고 있습니다", js)
        match = re.search(r"setTimeout\(\(\) => controller\.abort\(\),\s*(\d+)\)", js)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(int(match.group(1)), 120_000)

    def test_css_has_mobile_breakpoint(self):
        css = (ROOT / "public" / "styles.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"@media\s*\([^)]*max-width")


if __name__ == "__main__":
    unittest.main()
