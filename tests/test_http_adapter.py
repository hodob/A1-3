import io
import json
import unittest
from unittest.mock import patch

from api._base import ApiHandler
from api.analyze_topic import handler as AnalyzeTopicHandler
from api.context_step import handler as ContextStepHandler
from api.create_motion import handler as CreateMotionHandler
from api.debate_step import handler as DebateStepHandler
from api.health import handler as HealthHandler
from api.neutral_summary import handler as NeutralSummaryHandler


class HttpAdapterTests(unittest.TestCase):
    def _handler(self, cls, body: bytes = b"{}", content_length: str | None = None):
        item = cls.__new__(cls)
        item.headers = {"Content-Length": content_length if content_length is not None else str(len(body))}
        item.rfile = io.BytesIO(body)
        item.wfile = io.BytesIO()
        item._status = None
        item._headers = {}
        item.send_response = lambda status: setattr(item, "_status", status)
        item.send_header = lambda key, value: item._headers.__setitem__(key, value)
        item.end_headers = lambda: None
        return item

    def _payload(self, item):
        return json.loads(item.wfile.getvalue().decode("utf-8"))

    def test_handler_routes_are_exact(self):
        self.assertEqual(AnalyzeTopicHandler.route, "/api/analyze-topic")
        self.assertEqual(ContextStepHandler.route, "/api/context-step")
        self.assertEqual(CreateMotionHandler.route, "/api/create-motion")
        self.assertEqual(DebateStepHandler.route, "/api/debate-step")
        self.assertEqual(NeutralSummaryHandler.route, "/api/neutral-summary")
        self.assertEqual(HealthHandler.route, "/api/health")

    def test_empty_post_body_returns_400_without_dispatch(self):
        item = self._handler(AnalyzeTopicHandler, b"", "0")
        with patch("api._base.dispatch") as dispatch:
            item.do_POST()
        self.assertEqual(item._status, 400)
        self.assertEqual(self._payload(item)["error"]["code"], "INVALID_INPUT")
        dispatch.assert_not_called()

    def test_invalid_json_returns_400_without_dispatch(self):
        item = self._handler(AnalyzeTopicHandler, b"not-json")
        with patch("api._base.dispatch") as dispatch:
            item.do_POST()
        self.assertEqual(item._status, 400)
        self.assertEqual(self._payload(item)["error"]["code"], "INVALID_INPUT")
        dispatch.assert_not_called()

    def test_non_object_json_returns_400(self):
        item = self._handler(AnalyzeTopicHandler, b"[]")
        with patch("api._base.dispatch") as dispatch:
            item.do_POST()
        self.assertEqual(item._status, 400)
        dispatch.assert_not_called()

    def test_oversized_body_returns_413_without_read_or_dispatch(self):
        item = self._handler(DebateStepHandler, b"{}", str(ApiHandler.max_body_bytes + 1))
        with patch("api._base.dispatch") as dispatch:
            item.do_POST()
        self.assertEqual(item._status, 413)
        self.assertEqual(self._payload(item)["error"]["code"], "PAYLOAD_TOO_LARGE")
        dispatch.assert_not_called()

    def test_valid_post_forwards_route_and_body_and_serializes_response(self):
        body = json.dumps({"topic": "핫도그는 샌드위치인가?"}, ensure_ascii=False).encode("utf-8")
        item = self._handler(AnalyzeTopicHandler, body)
        with patch("api._base.dispatch", return_value=(200, {"ok": True, "data": {"x": "한글"}})) as dispatch:
            item.do_POST()
        dispatch.assert_called_once_with("/api/analyze-topic", {"topic": "핫도그는 샌드위치인가?"})
        self.assertEqual(item._status, 200)
        self.assertEqual(item._headers["Cache-Control"], "no-store")
        self.assertEqual(self._payload(item), {"ok": True, "data": {"x": "한글"}})

    def test_options_is_zero_body_204(self):
        item = self._handler(AnalyzeTopicHandler)
        item.do_OPTIONS()
        self.assertEqual(item._status, 204)
        self.assertEqual(item.wfile.getvalue(), b"")

    def test_health_get_uses_dispatch_and_write_contract(self):
        item = self._handler(HealthHandler)
        with patch("api.health.dispatch", return_value=(200, {"ok": True, "data": {"provider_call": False}})) as dispatch:
            item.do_GET()
        dispatch.assert_called_once_with("/api/health", {})
        self.assertEqual(item._status, 200)
        self.assertFalse(self._payload(item)["data"]["provider_call"])

    def test_debate_stream_emits_draft_then_commit(self):
        item = self._handler(DebateStepHandler, b'{}')
        item.headers["Accept"] = "text/event-stream"
        def dispatch_stream(route, body, event_sink=None):
            event_sink("draft_reset", {"speaker": "A", "phase": "OPENING", "attempt": 1})
            event_sink("draft_delta", {"text": "임시"})
            return 200, {"ok": True, "data": {"utterance": "확정"}}
        with patch("api._base.dispatch", side_effect=dispatch_stream):
            item.do_POST()
        raw = item.wfile.getvalue().decode()
        self.assertEqual(item._headers["Content-Type"], "text/event-stream; charset=utf-8")
        self.assertLess(raw.index("event: draft_delta"), raw.index("event: commit"))
        self.assertIn('"utterance": "확정"', raw)

    def test_debate_stream_failure_never_emits_commit(self):
        item = self._handler(DebateStepHandler, b'{}')
        item.headers["Accept"] = "text/event-stream"
        def dispatch_stream(route, body, event_sink=None):
            event_sink("draft_delta", {"text": "폐기할 발언"})
            return 422, {"ok": False, "error": {"code": "SAFE_FAILURE", "message": "실패"}}
        with patch("api._base.dispatch", side_effect=dispatch_stream):
            item.do_POST()
        raw = item.wfile.getvalue().decode()
        self.assertIn("event: error", raw)
        self.assertNotIn("event: commit", raw)


if __name__ == "__main__":
    unittest.main()
