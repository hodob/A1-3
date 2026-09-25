from pathlib import Path
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
        for phrase in ("주제를 살펴보고 있어요", "토론할 이야기를 한 줄 적어주세요", "준비를 마치지 못했어요"):
            self.assertIn(phrase, js)

    def test_context_summary_is_sent_to_motion_endpoint(self):
        js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        self.assertIn("context_summary", js)
        self.assertIn("/api/create-motion", js)

    def test_context_review_and_free_text_controls_exist(self):
        js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        self.assertIn("직접 본 일", js)
        self.assertIn("전해 들은 이야기", js)
        self.assertIn("내 해석", js)
        self.assertIn("알려주고 싶은 상황", (ROOT / "public" / "index.html").read_text(encoding="utf-8"))

    def test_summary_displays_agreements(self):
        js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        self.assertIn("함께 인정한 부분", (ROOT / "public" / "index.html").read_text(encoding="utf-8"))
        self.assertIn("state.summary.agreements", js)

    def test_frontend_has_timeout_abort_path(self):
        js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        self.assertIn("AbortController", js)
        self.assertIn("응답을 기다리는 시간이 길어져 멈췄어요", js)
        self.assertIn("180000", js)

    def test_css_has_mobile_breakpoint(self):
        css = (ROOT / "public" / "styles.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"@media\s*\([^)]*max-width")


if __name__ == "__main__":
    unittest.main()
