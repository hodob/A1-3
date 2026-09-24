import json
import unittest

from src.debate_engine.provider_adapter import ProviderAdapter, ProviderCapabilities, ProviderOutputError
from src.debate_engine.debate_contracts import PatchEnvelope


class ProviderAdapterTests(unittest.TestCase):
    def test_tool_transport_without_forced_choice_uses_local_schema(self):
        adapter = ProviderAdapter(ProviderCapabilities(True, False, False))
        body = adapter.build_structured_body("gpt-5.4", [{"role": "user", "content": "extract"}], PatchEnvelope, "extract_patch")
        self.assertEqual(body["model"], "gpt-5.4")
        self.assertEqual(body["tools"][0]["function"]["name"], "extract_patch")
        self.assertNotIn("response_format", body)
        self.assertNotIn("tool_choice", body)

    def test_forced_tool_choice_is_added_only_when_supported(self):
        adapter = ProviderAdapter(ProviderCapabilities(True, True, False))
        body = adapter.build_structured_body("m", [], PatchEnvelope, "extract_patch")
        self.assertEqual(body["tool_choice"]["function"]["name"], "extract_patch")

    def test_json_schema_transport_is_used_without_tool_calling(self):
        adapter = ProviderAdapter(ProviderCapabilities(False, False, True))
        body = adapter.build_structured_body("m", [], PatchEnvelope, "extract_patch")
        self.assertNotIn("tools", body)
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertEqual(body["response_format"]["json_schema"]["name"], "extract_patch")

    def test_no_structured_transport_is_rejected(self):
        adapter = ProviderAdapter(ProviderCapabilities(False, False, False))
        with self.assertRaises(ValueError):
            adapter.build_structured_body("m", [], PatchEnvelope, "extract_patch")

    def test_valid_tool_call_parses_to_contract(self):
        adapter = ProviderAdapter(ProviderCapabilities(True, False, False))
        payload = {"choices": [{"message": {"tool_calls": [{"function": {
            "name": "extract_patch",
            "arguments": json.dumps({"operations": [{"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "claim"}]})
        }}]}}]}
        parsed = adapter.parse_structured_response(payload, PatchEnvelope, "extract_patch")
        self.assertEqual(parsed.operations[0].op, "ADD_PROPOSITION")
        self.assertEqual(parsed.operations[0].text, "claim")

    def test_wrong_or_multiple_tool_calls_are_rejected_explicitly(self):
        adapter = ProviderAdapter(ProviderCapabilities(True, False, False))
        for calls in (
            [],
            [{"function": {"name": "wrong", "arguments": "{}"}}],
            [
                {"function": {"name": "extract_patch", "arguments": '{"operations":[]}'}},
                {"function": {"name": "extract_patch", "arguments": '{"operations":[]}'}},
            ],
        ):
            with self.subTest(calls=len(calls)):
                with self.assertRaises(ProviderOutputError) as caught:
                    adapter.parse_structured_response({"choices": [{"message": {"tool_calls": calls}}]}, PatchEnvelope, "extract_patch")
                self.assertEqual(caught.exception.code, "missing_or_wrong_tool_call")

    def test_malformed_tool_arguments_are_provider_output_error(self):
        adapter = ProviderAdapter(ProviderCapabilities(True, False, False))
        payload = {"choices": [{"message": {"tool_calls": [{"function": {"name": "extract_patch", "arguments": "{"}}]}}]}
        with self.assertRaises(ProviderOutputError) as caught:
            adapter.parse_structured_response(payload, PatchEnvelope, "extract_patch")
        self.assertEqual(caught.exception.code, "invalid_provider_output")

    def test_local_validation_failure_keeps_structured_details(self):
        adapter = ProviderAdapter(ProviderCapabilities(True, False, False))
        invalid = {"choices": [{"message": {"tool_calls": [{"function": {"name": "extract_patch", "arguments": '{"operations":[{"op":"ANSWER_QUESTION","question_id":"C1","response_status":"DIRECT","resolution":"RESOLVED"}]}'}}]}}]}
        with self.assertRaises(ProviderOutputError) as caught:
            adapter.parse_structured_response(invalid, PatchEnvelope, "extract_patch")
        self.assertEqual(caught.exception.code, "local_validation_failed")
        self.assertTrue(caught.exception.details)

    def test_json_schema_content_parses_when_tool_calling_is_disabled(self):
        adapter = ProviderAdapter(ProviderCapabilities(False, False, True))
        payload = {"choices": [{"message": {"content": '{"operations":[]}'}}]}
        parsed = adapter.parse_structured_response(payload, PatchEnvelope, "extract_patch")
        self.assertEqual(parsed.operations, [])


if __name__ == "__main__":
    unittest.main()
