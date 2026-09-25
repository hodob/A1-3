import json
import unittest
from unittest.mock import patch

from src.web_app.api import dispatch
from src.web_app.service_factory import get_default_service
from src.web_app.mock_service import MockDebateWebService


class WebApiTests(unittest.TestCase):
    def test_health_exposes_short_deployment_commit_without_provider_call(self):
        with patch.dict("os.environ", {"VERCEL_GIT_COMMIT_SHA": "8a94fb5609ed98ba592932dcc4a41c7a489d1464"}):
            status, payload = dispatch("/api/health", {}, service=MockDebateWebService())
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["version"], "8a94fb5")
        self.assertFalse(payload["data"]["provider_call"])

    def test_unknown_route_returns_404_contract(self):
        status, payload = dispatch("/api/nope", {}, service=MockDebateWebService())
        self.assertEqual(status, 404)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "NOT_FOUND")

    def test_blank_topic_returns_validation_error(self):
        status, payload = dispatch("/api/analyze-topic", {"topic": ""}, service=MockDebateWebService())
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")

    def test_analyze_topic_success_is_wrapped(self):
        status, payload = dispatch("/api/analyze-topic", {"topic": "탕수육 부먹 찍먹"}, service=MockDebateWebService())
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("data", payload)
        self.assertEqual(payload["data"]["interaction_state"], "READY")

    def test_health_route_is_zero_token_ready_in_live_mode(self):
        status, payload = dispatch("/api/health", {}, service=MockDebateWebService())
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], "ready")
        self.assertEqual(payload["data"]["mode"], "live")

    def test_health_mode_comes_from_config_not_environment_override(self):
        with patch.dict("os.environ", {"DEBATE_WEB_MODE": "live"}, clear=True):
            status, payload = dispatch("/api/health", {}, service=MockDebateWebService())
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["mode"], "live")
        self.assertFalse(payload["data"]["provider_call"])

    def test_health_reports_service_config_error_before_provider_use(self):
        get_default_service.cache_clear()
        try:
            with patch("src.web_app.api.get_default_service", side_effect=__import__("src.web_app.service_factory", fromlist=["ServiceConfigError"]).ServiceConfigError("bad config")):
                status, payload = dispatch("/api/health", {})
            self.assertEqual(status, 503)
            self.assertEqual(payload["error"]["code"], "CONFIG_ERROR")
        finally:
            get_default_service.cache_clear()

    def test_api_response_is_json_serializable(self):
        _, payload = dispatch("/api/analyze-topic", {"topic": "핫도그는 샌드위치인가?"}, service=MockDebateWebService())
        json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
