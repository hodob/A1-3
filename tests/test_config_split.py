import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.web_app.service_factory import ServiceConfigError, build_service
from src.web_app.live_service import LiveDebateWebService
from src.web_app.mock_service import MockDebateWebService

ROOT = Path(__file__).resolve().parents[1]


class ConfigSplitTests(unittest.TestCase):
    def _config(self, root: Path, *, mode: str = "live", url: str = "https://example.test/v1", model: str = "gpt-test") -> Path:
        path = root / "config.json"
        path.write_text(json.dumps({
            "web_mode": mode,
            "provider": {"url": url, "model": model, "debater_models": [
                {"company": "GOOGLE", "id": "gemini-test"},
                {"company": "ANTHROPIC", "id": "claude-test"},
            ]},
        }), encoding="utf-8")
        return path

    def test_committed_config_contains_only_non_secret_runtime_settings(self):
        data = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        self.assertIn(data["web_mode"], ("mock", "live"))
        self.assertTrue(data["provider"]["url"].startswith("https://"))
        self.assertTrue(data["provider"]["model"])
        self.assertGreaterEqual(len(data["provider"]["debater_models"]), 2)
        dumped = json.dumps(data).lower()
        self.assertNotIn("api_key", dumped)
        self.assertNotIn("session_secret", dumped)
        self.assertNotIn("secret", dumped)

    def test_env_example_contains_secrets_only(self):
        lines = [
            line.strip() for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        keys = {line.split("=", 1)[0] for line in lines}
        self.assertEqual(keys, {"DEBATER_API_KEY", "SESSION_SECRET"})

    def test_live_service_combines_config_with_secret_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(Path(tmp))
            env = {
                "DEBATER_API_KEY": "not-a-real-key",
                "SESSION_SECRET": "session-secret-abcdefghijklmnopqrstuvwxyz",
            }
            with patch.dict(os.environ, env, clear=True):
                service = build_service(config_path=config)
            self.assertIsInstance(service, LiveDebateWebService)
            self.assertEqual(service.provider["url"], "https://example.test/v1/chat/completions")
            self.assertEqual(service.provider["model"], "gpt-test")
            self.assertEqual(service.provider["api_key"], "not-a-real-key")

    def test_non_secret_environment_does_not_override_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(Path(tmp), url="https://config.test/v1", model="config-model")
            env = {
                "DEBATER_API_KEY": "key",
                "SESSION_SECRET": "session-secret-abcdefghijklmnopqrstuvwxyz",
                "DEBATER_URL": "https://env-should-not-win.test/v1",
                "DEBATE_MODEL": "env-model",
                "DEBATE_WEB_MODE": "mock",
            }
            with patch.dict(os.environ, env, clear=True):
                service = build_service(config_path=config)
            self.assertIsInstance(service, LiveDebateWebService)
            self.assertEqual(service.provider["url"], "https://config.test/v1/chat/completions")
            self.assertEqual(service.provider["model"], "config-model")

    def test_mock_mode_needs_no_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(Path(tmp), mode="mock")
            with patch.dict(os.environ, {}, clear=True):
                self.assertIsInstance(build_service(config_path=config), MockDebateWebService)

    def test_live_mode_requires_both_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(Path(tmp), mode="live")
            with patch.dict(os.environ, {"DEBATER_API_KEY": "only-key"}, clear=True):
                with self.assertRaises(ServiceConfigError):
                    build_service(config_path=config)

    def test_config_rejects_secret_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({
                "web_mode": "live",
                "provider": {"url": "https://example.test/v1", "model": "gpt-test", "debater_models": [
                    {"company": "GOOGLE", "id": "gemini-test"},
                    {"company": "ANTHROPIC", "id": "claude-test"},
                ], "api_key": "bad"},
            }), encoding="utf-8")
            with patch.dict(os.environ, {
                "DEBATER_API_KEY": "key",
                "SESSION_SECRET": "session-secret-abcdefghijklmnopqrstuvwxyz",
            }, clear=True):
                with self.assertRaises(ServiceConfigError):
                    build_service(config_path=path)


if __name__ == "__main__":
    unittest.main()
