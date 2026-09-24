import unittest

from src.debate_engine.action_fidelity import ActionFidelityLabel
from src.debate_engine.combined_compliance import CombinedComplianceAssessment
from src.debate_engine.debate_contracts import PatchEnvelope
from src.debate_engine.stance_compliance import StanceLabel
from src.web_app.live_service import LiveDebateWebService, LiveRuntimeDependencies
from src.web_app.live_smoke import MeteredDependencies, SmokePlan, run_smoke
from src.web_app.session_token import SessionTokenCodec


class DeterministicDeps(LiveRuntimeDependencies):
    def __init__(self):
        self.turn = 0

    def generate_text(self, provider, messages, timeout=90):
        self.turn += 1
        text = (
            "핫도그는 빵과 속재료의 구조가 샌드위치와 유사하므로 같은 범주로 볼 수 있습니다."
            if self.turn == 1 else
            "그 기준은 너무 넓습니다. 이어진 번이라는 구조 차이가 분류 기준에서 왜 무의미한가요?"
        )
        return text, {"usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}}

    def check_compliance(self, provider, **kwargs):
        return CombinedComplianceAssessment(
            ActionFidelityLabel.ALIGNED, StanceLabel.SUPPORTS_ASSIGNED,
            "action ok", "stance ok",
        ), {"usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100}}

    def extract_patch(self, provider, turn, state, timeout, feedback=None):
        if turn["turn"] == 1:
            ops = [
                {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "핫도그는 샌드위치에 속한다."},
                {"op": "ADD_PROPOSITION", "temp_id": "P2", "text": "빵과 속재료 구조가 샌드위치와 유사하다."},
                {"op": "ADD_RELATION", "from_proposition_ref": "P2", "to_proposition_ref": "P1", "relation_type": "SUPPORTS"},
            ]
        else:
            ops = [
                {"op": "ADD_PROPOSITION", "temp_id": "P1", "text": "이어진 번이라는 구조 차이는 분류상 중요하다."},
                {"op": "ADD_RELATION", "from_proposition_ref": "P1", "to_proposition_ref": "C1", "relation_type": "ATTACKS"},
                {"op": "ASK_QUESTION", "text": "구조 차이가 왜 무의미한가요?", "core_proposition": "이어진 번의 구조 차이가 분류상 무의미한지 답해야 한다.", "target_proposition_id": "C1"},
            ]
        return PatchEnvelope.model_validate({"operations": ops}), {"usage": {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160}}

    def structured(self, provider, messages, contract, tool_name, timeout=90):
        if tool_name == "topic_analysis":
            value = {
                "original_topic": "핫도그는 샌드위치인가?", "claim_type": "DEFINITION",
                "epistemic_status": "NON_FACTUAL", "treatment_mode": "NATURAL_DEBATE",
                "interaction_state": "READY", "normalized_motion": "핫도그는 샌드위치에 속한다.",
                "side_labels": ["샌드위치", "별도 범주"], "context_required": False,
                "confirmation_reason": None,
            }
        elif tool_name == "neutral_summary":
            value = {
                "key_clashes": ["분류 기준"], "side_a_strong_points": ["구조 유사성"],
                "side_b_strong_points": ["번 구조 차이"], "agreements": ["기준이 필요함"],
                "unresolved": ["어떤 기준을 우선할지"],
            }
        else:
            raise AssertionError(tool_name)
        return contract.model_validate(value), {"usage": {"prompt_tokens": 90, "completion_tokens": 30, "total_tokens": 120}}


class LiveSmokeTests(unittest.TestCase):
    def test_two_turn_smoke_collects_maximum_cross_layer_evidence(self):
        codec = SessionTokenCodec("test-session-secret-123456789")
        deps = MeteredDependencies(DeterministicDeps(), max_total_tokens=5000)
        service = LiveDebateWebService(
            provider={"url": "https://example.invalid", "api_key": "secret", "model": "gpt-test"},
            codec=codec, deps=deps,
        )
        report = run_smoke(service, codec, deps, SmokePlan(topic="핫도그는 샌드위치인가?", debate_turns=2, max_total_tokens=5000))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["debate_turns"], 2)
        self.assertEqual(report["speakers"], ["A", "B"])
        self.assertGreaterEqual(report["state_counts"]["propositions"], 3)
        self.assertGreaterEqual(report["state_counts"]["relations"], 2)
        self.assertGreaterEqual(report["state_counts"]["questions"], 1)
        self.assertEqual(report["compliance_failures"], 0)
        self.assertEqual(len(report["transcript"]), 2)
        self.assertTrue(report["coverage"]["relation_extraction_observed"])
        self.assertTrue(report["coverage"]["question_extraction_observed"])
        self.assertTrue(report["coverage"]["signed_session_roundtrip"])
        self.assertTrue(report["coverage"]["neutral_summary"])
        self.assertLessEqual(report["usage"]["total_tokens"], 5000)
        self.assertIn("topic_analysis", report["call_purposes"])
        self.assertIn("utterance_generation", report["call_purposes"])
        self.assertIn("combined_compliance", report["call_purposes"])
        self.assertIn("state_patch", report["call_purposes"])
        self.assertIn("neutral_summary", report["call_purposes"])

    def test_budget_stops_before_starting_another_provider_call(self):
        inner = DeterministicDeps()
        deps = MeteredDependencies(inner, max_total_tokens=200)
        deps.generate_text({}, [], timeout=1)
        with self.assertRaises(RuntimeError):
            deps.check_compliance({}, action="EXTEND_ARGUMENT", target_id=None, target_text=None, utterance="x", assignment=None, phase="opening", timeout=1)


if __name__ == "__main__":
    unittest.main()
