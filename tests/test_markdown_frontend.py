from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


class MarkdownFrontendTests(unittest.TestCase):
    def test_markdown_libraries_and_renderer_load_before_app(self):
        html = (PUBLIC / "index.html").read_text(encoding="utf-8")
        marked = "https://cdnjs.cloudflare.com/ajax/libs/marked/15.0.12/marked.min.js"
        purify = "https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.2.6/purify.min.js"
        renderer = "/markdown_renderer.js"
        self.assertIn(marked, html)
        self.assertIn(purify, html)
        self.assertIn(renderer, html)
        self.assertLess(html.index(marked), html.index(purify))
        self.assertLess(html.index(purify), html.index(renderer))
        self.assertLess(html.index(renderer), html.index('/app.js'))

    def test_csp_allows_only_the_pinned_markdown_cdn_for_external_scripts(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        headers = next(rule["headers"] for rule in config["headers"] if rule["source"] == "/(.*)")
        csp = next(item["value"] for item in headers if item["key"] == "Content-Security-Policy")
        self.assertIn("script-src 'self' https://cdnjs.cloudflare.com", csp)

    def test_ai_conversation_and_summary_use_markdown_renderer(self):
        js = (PUBLIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("SaiMarkdown.renderBlock", js)
        self.assertIn("SaiMarkdown.renderInline", js)
        self.assertIn("draftMarkdown", js)
        self.assertNotIn("element('p', 'utterance', item.utterance)", js)

    def test_markdown_renderer_uses_marked_then_dompurify_and_has_plain_text_fallback(self):
        js = (PUBLIC / "markdown_renderer.js").read_text(encoding="utf-8")
        self.assertIn("marked.parse", js)
        self.assertIn("marked.parseInline", js)
        self.assertIn("DOMPurify.sanitize", js)
        self.assertIn("node.textContent", js)
        self.assertIn("noopener noreferrer nofollow", js)

    def test_vercel_routes_local_markdown_renderer(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        rewrites = {item["source"]: item["destination"] for item in config["rewrites"]}
        self.assertEqual(rewrites.get("/markdown_renderer.js"), "/public/markdown_renderer.js")


if __name__ == "__main__":
    unittest.main()
