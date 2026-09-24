import json
import os
from pathlib import Path
import tempfile
import unittest

from src.runtime_config import RuntimeConfigError, load_runtime_config, read_dotenv_secrets, secret_values


class RuntimeConfigTests(unittest.TestCase):
    def test_missing_and_malformed_config_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(RuntimeConfigError):
                load_runtime_config(root / "missing.json")
            malformed = root / "bad.json"
            malformed.write_text("{", encoding="utf-8")
            with self.assertRaises(RuntimeConfigError):
                load_runtime_config(malformed)

    def test_extra_or_secret_config_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({
                "web_mode": "live",
                "provider": {"url": "https://example.test/v1", "model": "gpt-test"},
                "session_secret": "must-not-be-here",
            }), encoding="utf-8")
            with self.assertRaises(RuntimeConfigError):
                load_runtime_config(path)

    def test_dotenv_rejects_non_secret_and_unknown_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            for text in (
                "DEBATER_URL=https://example.test/v1\nDEBATER_API_KEY=x\n",
                "SOMETHING_ELSE=x\n",
                "BROKEN_LINE\n",
            ):
                with self.subTest(text=text.splitlines()[0]):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises(RuntimeConfigError):
                        read_dotenv_secrets(path)

    def test_environment_secret_overrides_dotenv_secret_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("DEBATER_API_KEY=file-key\nSESSION_SECRET=file-secret\n", encoding="utf-8")
            values = secret_values(env_path=path, environ={"DEBATER_API_KEY": "env-key", "DEBATER_URL": "ignored"})
            self.assertEqual(values["DEBATER_API_KEY"], "env-key")
            self.assertEqual(values["SESSION_SECRET"], "file-secret")
            self.assertNotIn("DEBATER_URL", values)

    def test_missing_dotenv_is_allowed_when_loading_from_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = secret_values(env_path=Path(tmp) / "missing.env", environ={"SESSION_SECRET": "env-secret"})
            self.assertEqual(values, {"SESSION_SECRET": "env-secret"})


if __name__ == "__main__":
    unittest.main()
