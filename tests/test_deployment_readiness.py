from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeploymentReadinessTests(unittest.TestCase):
    def test_python_version_is_pinned_for_vercel(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('requires-python = "~=3.12.0"', text)
        self.assertIn('pydantic>=2.13,<3', text)

    def test_vercel_has_schema_and_adequate_function_duration(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(config.get("$schema"), "https://openapi.vercel.sh/vercel.json")
        self.assertGreaterEqual(config["functions"]["api/*.py"]["maxDuration"], 120)

    def test_vercel_uses_other_preset_for_multiple_python_functions(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertIn("framework", config)
        self.assertIsNone(config["framework"])

    def test_vercel_security_headers_are_defined(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        header_map = {}
        for rule in config.get("headers", []):
            if rule.get("source") == "/(.*)":
                header_map = {item["key"]: item["value"] for item in rule["headers"]}
        self.assertEqual(header_map.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(header_map.get("Referrer-Policy"), "no-referrer")
        self.assertIn("default-src 'self'", header_map.get("Content-Security-Policy", ""))
        self.assertEqual(header_map.get("X-Robots-Tag"), "noindex, nofollow")

    def test_robots_disallows_crawling_and_is_routed(self):
        self.assertIn("Disallow: /", (ROOT / "public" / "robots.txt").read_text(encoding="utf-8"))
        config = (ROOT / "vercel.json").read_text(encoding="utf-8")
        self.assertIn('"/robots.txt"', config)
        self.assertIn('"/public/robots.txt"', config)

    def test_gitignore_protects_local_secrets_and_vercel_metadata(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for entry in (".env", ".env.*", "!.env.example", ".vercel/", ".venv/", "__pycache__/"):
            self.assertIn(entry, text)

    def test_vercelignore_excludes_non_runtime_artifacts(self):
        text = (ROOT / ".vercelignore").read_text(encoding="utf-8")
        for entry in (".env", ".venv/", "tests/", "etc/", "docs/", "__pycache__/", "*.pyc"):
            self.assertIn(entry, text)

    def test_final_deployment_and_demo_docs_exist(self):
        deploy = (ROOT / "docs" / "DEPLOYMENT_CHECKLIST.md").read_text(encoding="utf-8")
        demo = (ROOT / "docs" / "DEMO_RUNBOOK.md").read_text(encoding="utf-8")
        for phrase in ("config.json", "DEBATER_API_KEY", "SESSION_SECRET", "Vercel"):
            self.assertIn(phrase, deploy)
        for phrase in ("150만", "Provider", "Audience Question", "Neutral Summary"):
            self.assertIn(phrase, demo)

    def test_github_ci_targets_deployment_python(self):
        text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        self.assertIn("python-version: '3.12'", text)
        self.assertIn("python -m unittest discover -s tests -q", text)
        self.assertIn("node --check public/app.js", text)

    def test_runtime_bundle_does_not_depend_on_tests_docs_or_etc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("api", "src", "public"):
                shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            for name in ("pyproject.toml", "requirements.txt", "vercel.json", "config.json"):
                shutil.copy2(ROOT / name, root / name)
            code = (
                "from src.web_app.api import dispatch; "
                "status,payload=dispatch('/api/analyze-topic', {'topic':'탕수육 부먹 vs 찍먹'}); "
                "assert status==200 and payload['ok'] is True; "
                "import api.analyze_topic, api.debate_step; print('runtime-bundle-ok')"
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(root)
            result = subprocess.run([sys.executable, "-c", code], cwd=root, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("runtime-bundle-ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
