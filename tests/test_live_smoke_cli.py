import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LiveSmokeCliTests(unittest.TestCase):
    def test_dry_run_is_default_and_never_requires_credentials(self):
        result = subprocess.run(
            [sys.executable, "-m", "etc.tools.live_smoke_once"],
            cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "DRY_RUN")
        self.assertEqual(payload["planned_debate_turns"], 3)
        self.assertEqual(payload["max_total_tokens"], 20_000)
        self.assertEqual(payload["provider_calls"], 0)
        self.assertIn("--execute", payload["execute_hint"])

    def test_execute_without_live_credentials_fails_before_network(self):
        env = {"PATH": str(Path(sys.executable).parent), "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}
        with tempfile.TemporaryDirectory() as folder:
            missing_env = Path(folder) / ".env"
            result = subprocess.run(
                [sys.executable, "-m", "etc.tools.live_smoke_once", "--execute", "--env", str(missing_env)],
                cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("환경 변수", result.stderr)


if __name__ == "__main__":
    unittest.main()
