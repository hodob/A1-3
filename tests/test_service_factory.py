import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.web_app.service_factory import ServiceConfigError, build_service
from src.web_app.mock_service import MockDebateWebService
from src.web_app.live_service import LiveDebateWebService


class ServiceFactoryTests(unittest.TestCase):
    def _config(self, folder: str, *, mode: str = "mock", url: str = "https://example.com/v1", model: str = "gpt-test") -> Path:
        path = Path(folder) / "config.json"
        path.write_text(json.dumps({"web_mode": mode, "provider": {"url": url, "model": model, "debater_models": [
            {"company": "GOOGLE", "id": "gemini-test"},
            {"company": "ANTHROPIC", "id": "claude-test"},
        ]}}), encoding="utf-8")
        return path

    def test_mock_config_is_safe_without_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            config = self._config(folder, mode="mock")
            with patch.dict(os.environ, {}, clear=True):
                self.assertIsInstance(build_service(config_path=config), MockDebateWebService)

    def test_live_requires_all_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            config = self._config(folder, mode="live")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ServiceConfigError):
                    build_service(config_path=config)

    def test_live_combines_file_config_with_secret_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            config = self._config(folder, mode="live")
            env = {
                "DEBATER_API_KEY": "not-a-real-key",
                "SESSION_SECRET": "session-secret-abcdefghijklmnopqrstuvwxyz",
            }
            with patch.dict(os.environ, env, clear=True):
                service = build_service(config_path=config)
            self.assertIsInstance(service, LiveDebateWebService)
            self.assertEqual(service.provider["url"], "https://example.com/v1/chat/completions")
            self.assertEqual(service.provider["model"], "gpt-test")
            self.assertEqual([item.id for item in service.debater_models], ["gemini-test", "claude-test"])

    def test_invalid_mode_in_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            config = self._config(folder, mode="maybe")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ServiceConfigError):
                    build_service(config_path=config)


if __name__ == "__main__":
    unittest.main()
