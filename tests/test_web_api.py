import json
import unittest
from unittest.mock import patch

from src.web_app.api import dispatch
from src.web_app.service_factory import get_default_service


class WebApiTests(unittest.TestCase):
    def test_unknown_route_returns_404_contract(self):
        status, payload = dispatch("/api/nope", {})
        self.assertEqual(status, 404)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "NOT_FOUND")

    def test_blank_topic_returns_validation_error(self):
        status, payload = dispatch("/api/analyze-topic", {"topic": ""})
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")

    def test_analyze_topic_success_is_wrapped(self):
        status, payload = dispatch("/api/analyze-topic", {"topic": "탕수육 부먹 찍먹"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("data", payload)
        self.assertEqual(payload["data"]["interaction_state"], "READY")

    def test_health_route_is_zero_token_ready_in_mock_mode(self):
        status, payload = dispatch("/api/health", {})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], "ready")
        self.assertEqual(payload["data"]["mode"], "mock")

    def test_health_mode_comes_from_config_not_environment_override(self):
        with patch.dict("os.environ", {"DEBATE_WEB_MODE": "live"}, clear=True):
            status, payload = dispatch("/api/health", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["mode"], "mock")
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
        _, payload = dispatch("/api/analyze-topic", {"topic": "핫도그는 샌드위치인가?"})
        json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
