import unittest

from src.web_app.api import dispatch
from src.web_app.errors import SafeFailure


class RaisingService:
    def debate_step(self, request):
        raise SafeFailure("guard rejected turn")


class TimeoutService:
    def analyze_topic(self, request):
        raise TimeoutError()


class ApiFailureTests(unittest.TestCase):
    def test_safe_failure_has_stable_user_contract(self):
        body = {
            "session": {"motion":"m","side_labels":["A","B"],"personas":["Socratic","Falsifier"],"tone":"SERIOUS"},
            "command": "NEXT"
        }
        status, payload = dispatch("/api/debate-step", body, service=RaisingService())
        self.assertEqual(status, 422)
        self.assertEqual(payload["error"]["code"], "SAFE_FAILURE")
        self.assertNotIn("guard rejected", payload["error"]["message"])

    def test_timeout_has_504_contract(self):
        status, payload = dispatch("/api/analyze-topic", {"topic":"x"}, service=TimeoutService())
        self.assertEqual(status, 504)
        self.assertEqual(payload["error"]["code"], "TIMEOUT")


if __name__ == "__main__":
    unittest.main()
