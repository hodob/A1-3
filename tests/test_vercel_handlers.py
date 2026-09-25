from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VercelHandlerTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))

    def test_all_python_api_handlers_exist(self):
        for name in ("analyze_topic.py", "context_step.py", "create_motion.py", "debate_step.py", "neutral_summary.py", "health.py"):
            self.assertTrue((ROOT / "api" / name).is_file(), name)

    def test_vercel_routes_static_assets_exactly(self):
        rewrites = {item["source"]: item["destination"] for item in self.config["rewrites"]}
        self.assertEqual(rewrites["/"], "/public/index.html")
        self.assertEqual(rewrites["/styles.css"], "/public/styles.css")
        self.assertEqual(rewrites["/app.js"], "/public/app.js")
        self.assertEqual(rewrites["/debate_stream.js"], "/public/debate_stream.js")
        self.assertEqual(rewrites["/robots.txt"], "/public/robots.txt")

    def test_hyphenated_public_api_routes_rewrite_to_python_files(self):
        rewrites = {item["source"]: item["destination"] for item in self.config["rewrites"]}
        expected = {
            "/api/analyze-topic": "/api/analyze_topic",
            "/api/context-step": "/api/context_step",
            "/api/create-motion": "/api/create_motion",
            "/api/debate-step": "/api/debate_step",
            "/api/neutral-summary": "/api/neutral_summary",
        }
        for source, destination in expected.items():
            self.assertEqual(rewrites.get(source), destination)

    def test_health_route_is_not_rewritten_away_from_python_handler(self):
        rewrites = {item["source"]: item["destination"] for item in self.config["rewrites"]}
        self.assertNotIn("/api/health", rewrites)
        self.assertTrue((ROOT / "api" / "health.py").is_file())

    def test_no_api_key_literal_in_frontend(self):
        js = (ROOT / "public" / "app.js").read_text(encoding="utf-8").lower()
        self.assertNotIn("api_key", js)
        self.assertNotIn("authorization", js)
        self.assertNotIn("bearer ", js)


if __name__ == "__main__":
    unittest.main()
