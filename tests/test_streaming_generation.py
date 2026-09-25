import io
import json
import unittest
from unittest.mock import patch

from src.debate_engine.debate_harness import call_model
from src.debate_engine.provider_transport import request_completion


class StreamingGenerationTests(unittest.TestCase):
    def test_streamed_chat_assembles_content_and_usage(self):
        events = [
            {"id": "first", "model": "claude-haiku-4", "choices": [{"delta": {"content": "안녕"}, "finish_reason": None}]},
            {"id": "second", "model": "claude-haiku-4", "choices": [{"delta": {"content": "하세요"}, "finish_reason": "stop"}]},
            {"id": "third", "model": "claude-haiku-4", "choices": [], "usage": {"total_tokens": 36}},
        ]
        stream = io.BytesIO(b"".join(b"data: " + json.dumps(event, ensure_ascii=False).encode() + b"\n\n" for event in events) + b'data: [DONE]\n\ndata: {"error":{"code":"invalid_request"}}\n\n')
        provider = {"url": "https://example.test/v1/chat/completions", "api_key": "test", "model": "claude-haiku-4", "stream": True}
        with patch("src.debate_engine.provider_transport.urllib.request.urlopen", return_value=stream) as urlopen:
            text, meta = call_model(provider, [{"role": "user", "content": "인사"}])
        self.assertEqual(text, "안녕하세요")
        self.assertEqual(meta["usage"]["total_tokens"], 36)
        self.assertEqual(meta["finish_reason"], "stop")
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(body["stream"], True)
        self.assertEqual(body["stream_options"], {"include_usage": True})

    def test_stream_without_content_fails_closed(self):
        provider = {"url": "https://example.test/v1/chat/completions", "api_key": "test", "model": "claude-haiku-4", "stream": True}
        with patch("src.debate_engine.provider_transport.urllib.request.urlopen", return_value=io.BytesIO(b"data: [DONE]\n\n")):
            with self.assertRaises(RuntimeError):
                call_model(provider, [{"role": "user", "content": "인사"}])

    def test_tool_arguments_from_multiple_chunks_are_assembled_by_index(self):
        events = [
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "tool-1", "type": "function", "function": {"name": "result", "arguments": '{"answer":'}}]}, "finish_reason": None}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"yes"}'}}]}, "finish_reason": "tool_calls"}]},
        ]
        stream = io.BytesIO(b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events) + b"data: [DONE]\n\n")
        provider = {"url": "https://example.test/v1/chat/completions", "api_key": "test", "model": "gpt-5.4"}
        with patch("src.debate_engine.provider_transport.urllib.request.urlopen", return_value=stream):
            payload = request_completion(provider, {"model": "gpt-5.4", "messages": [], "tools": [{"type": "function"}]})
        call = payload["choices"][0]["message"]["tool_calls"][0]
        self.assertEqual(call["function"], {"name": "result", "arguments": '{"answer":"yes"}'})
        self.assertEqual(payload["choices"][0]["finish_reason"], "tool_calls")


if __name__ == "__main__":
    unittest.main()
