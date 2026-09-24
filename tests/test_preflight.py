from pathlib import Path
import unittest

from etc.tools.preflight import collect_static_checks

ROOT = Path(__file__).resolve().parents[1]


class PreflightTests(unittest.TestCase):
    def test_static_preflight_checks_pass(self):
        checks = collect_static_checks(ROOT)
        failures = [item for item in checks if not item["ok"]]
        self.assertEqual(failures, [], failures)
        names = {item["name"] for item in checks}
        for expected in ("vercel_json", "frontend_secret_scan", "required_files", "config_secret_split"):
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main()
