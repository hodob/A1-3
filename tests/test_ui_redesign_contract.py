from html.parser import HTMLParser
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


class _DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.h1_count = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "a" and values.get("href", "").startswith("#"):
            self.links.append(values["href"][1:])
        if tag == "h1":
            self.h1_count += 1


class UiRedesignContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (PUBLIC / "index.html").read_text(encoding="utf-8")
        cls.css = (PUBLIC / "styles.css").read_text(encoding="utf-8")
        cls.js = (PUBLIC / "app.js").read_text(encoding="utf-8")

    def test_sai_brand_and_plain_language_copy_replace_old_brand(self):
        self.assertIn("<title>사이 — 두 AI의 토론을 구경하세요</title>", self.html)
        self.assertIn("두 생각 사이", self.html)
        self.assertIn("마지막 판단은 내가", self.html)
        self.assertNotIn("CLASH LAB", self.html)
        self.assertNotIn("LIVE HARNESS", self.html)

    def test_three_routes_and_skip_link_have_valid_targets(self):
        parser = _DocumentParser()
        parser.feed(self.html)
        for route in ("main", "home", "debate", "how-it-works"):
            self.assertIn(route, parser.ids)
        self.assertIn('<a class="skip-link" href="#main">본문으로 건너뛰기</a>', self.html)
        self.assertFalse(set(parser.links) - parser.ids)

    def test_preparation_and_result_views_are_explicit(self):
        for view_id in (
            "topic-view",
            "context-view",
            "context-review-view",
            "motion-view",
            "debate-empty",
            "debate-arena",
            "summary-view",
            "choice-view",
            "done-view",
        ):
            self.assertIn(f'id="{view_id}"', self.html)

    def test_accessible_forms_and_live_regions_exist(self):
        for control in ("topic-input", "context-free-input", "motion-edit-input", "audience-input"):
            self.assertIn(f'for="{control}"', self.html)
        self.assertIn('id="app-status"', self.html)
        self.assertIn('aria-live="polite"', self.html)
        self.assertIn('id="app-error"', self.html)
        self.assertIn('role="alert"', self.html)
        self.assertNotRegex(self.html, r'id="debate-log"[^>]*aria-live')

    def test_runtime_state_and_request_race_protection_are_explicit(self):
        for state_key in (
            "route:",
            "view:",
            "pendingOperation:",
            "confirmedContextAnswers:",
            "summary:",
            "choice:",
        ):
            self.assertIn(state_key, self.js)
        self.assertIn("operationId", self.js)
        self.assertIn("STALE_OPERATION", self.js)
        self.assertIn("candidateAnswers", self.js)

    def test_motion_edit_is_inline_and_first_turn_is_requested_automatically(self):
        self.assertNotIn("window.prompt", self.js)
        self.assertIn("motion-edit-form", self.html)
        self.assertIn("await runStep('NEXT')", self.js)

    def test_unverified_previous_turn_callback_is_not_rendered(self):
        self.assertNotIn("앞서 ${previous.speaker}가 한 말", self.js)
        self.assertNotIn("원문 보기 ↑", self.js)
        self.assertNotIn("class=\"reply\"", self.html)

    def test_user_facing_phase_and_persona_copy_is_localized(self):
        for phase in ("첫 입장", "주고받기", "함께 답하기", "쟁점 되짚기", "마지막 한마디", "토론 정리"):
            self.assertIn(phase, self.js + self.html)
        for persona in ("Auditor", "Socratic", "Falsifier", "Pragmatist", "Principlist", "Synthesist"):
            self.assertIn(persona, self.js)

    def test_mobile_first_tokens_and_accessibility_media_rules_exist(self):
        for token in ("--color-bg", "--color-text", "--color-a", "--color-b", "--width-site"):
            self.assertIn(token, self.css)
        self.assertRegex(self.css, r"@media\s*\(min-width:\s*768px\)")
        self.assertRegex(self.css, r"@media\s*\(min-width:\s*1200px\)")
        self.assertIn("prefers-reduced-motion: reduce", self.css)
        self.assertIn("forced-colors: active", self.css)
        self.assertIn("min-height: 52px", self.css)

    def test_javascript_is_syntactically_valid(self):
        result = subprocess.run(
            ["node", "--check", str(PUBLIC / "app.js")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
