import json
from pathlib import Path
import unittest

from src.debate_engine.action_fidelity import ActionFidelityLabel, check_action_fidelity
from src.debate_engine.action_execution_contracts import CONTRACTS


class ActionFidelityTests(unittest.TestCase):
    def test_all_fifteen_actions_have_execution_contract(self):
        self.assertEqual(len(CONTRACTS), 15)
        for contract in CONTRACTS.values():
            self.assertTrue(contract.target_type)
            self.assertTrue(contract.required_semantic_effect)
            self.assertTrue(contract.allowed_realization)
            self.assertTrue(contract.failure_patterns)

    def test_known_turn_four_is_not_aligned(self):
        case = json.loads(Path("etc/fixtures/action_fidelity_audit.json").read_text(encoding="utf-8"))["cases"][3]
        result = check_action_fidelity(case["selected_action"], case["target_text"], case["utterance"])
        self.assertNotEqual(result.label, ActionFidelityLabel.ALIGNED)

    def test_valid_request_support(self):
        result = check_action_fidelity("REQUEST_SUPPORT", "원격근무가 생산성을 높인다", "원격근무가 생산성을 높인다는 근거는 무엇입니까?")
        self.assertEqual(result.label, ActionFidelityLabel.ALIGNED)

    def test_challenge_that_supports_target_fails(self):
        result = check_action_fidelity("CHALLENGE_PREMISE", "초기 비용이 크다", "초기 비용이 크다는 점은 맞고 이 주장의 좋은 근거입니다.")
        self.assertEqual(result.label, ActionFidelityLabel.MISALIGNED)

    def test_valid_local_concession(self):
        result = check_action_fidelity("CONCEDE_LOCAL", "초기 비용이 크다", "초기 비용이 크다는 점은 인정합니다. 다만 장기 효과는 별개입니다.")
        self.assertEqual(result.label, ActionFidelityLabel.ALIGNED)

    def test_fake_concession_fails(self):
        result = check_action_fidelity("CONCEDE_LOCAL", "초기 비용이 크다", "그 주장은 들었지만 초기 비용이 크다는 데 동의하지 않습니다.")
        self.assertEqual(result.label, ActionFidelityLabel.MISALIGNED)

    def test_valid_weigh(self):
        result = check_action_fidelity("WEIGH_COMPARATIVE", None, "비용은 A가 낮지만 효과의 지속성은 B가 더 크므로 장기 효과 기준에서는 B가 우선입니다.")
        self.assertEqual(result.label, ActionFidelityLabel.ALIGNED)

    def test_fake_weigh_fails(self):
        result = check_action_fidelity("WEIGH_COMPARATIVE", None, "A는 효과가 좋고 그래서 A가 낫습니다.")
        self.assertEqual(result.label, ActionFidelityLabel.MISALIGNED)

    def test_valid_crystallize(self):
        result = check_action_fidelity("CRYSTALLIZE", None, "지금까지의 핵심 충돌은 비용보다 장기 효과를 우선할지입니다. 제 핵심은 장기 효과가 더 크다는 점입니다.")
        self.assertEqual(result.label, ActionFidelityLabel.ALIGNED)

    def test_crystallize_with_new_argument_fails(self):
        result = check_action_fidelity("CRYSTALLIZE", None, "새로운 근거로 해외 연구 결과도 있습니다. 따라서 A가 낫습니다.")
        self.assertEqual(result.label, ActionFidelityLabel.MISALIGNED)


if __name__ == "__main__":
    unittest.main()
