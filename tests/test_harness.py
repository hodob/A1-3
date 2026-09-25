import json
import tempfile
import unittest
from pathlib import Path

from src.debate_engine.debate_harness import ConfigError, PERSONAS, build_schedule, load_config, load_scenario, safe_record, select_debaters, speech_messages


class HarnessTests(unittest.TestCase):
    def _config(self, folder, url="https://example.test/v1"):
        path = Path(folder) / "config.json"
        path.write_text(json.dumps({"web_mode": "live", "provider": {"url": url, "model": "gpt-test", "debater_models": [
            {"company": "GOOGLE", "id": "gemini-test"},
            {"company": "ANTHROPIC", "id": "claude-test"},
        ]}}), encoding="utf-8")
        return path

    def test_missing_provider_credentials_fail_before_any_request(self):
        with tempfile.TemporaryDirectory() as folder:
            env_path = Path(folder) / ".env"
            env_path.write_text("", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(env_path, self._config(folder))

    def test_non_secret_values_in_dotenv_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            env_path = Path(folder) / ".env"
            env_path.write_text("DEBATER_URL=https://wrong-place.test/v1\nDEBATER_API_KEY=debater-key\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(env_path, self._config(folder))

    def test_one_selected_model_is_used_by_both_debaters(self):
        with tempfile.TemporaryDirectory() as folder:
            env_path = Path(folder) / ".env"
            env_path.write_text("DEBATER_API_KEY=debater-key\n", encoding="utf-8")
            providers = load_config(env_path, self._config(folder, "https://debater.test/v1/chat/completions"))
            selected = select_debaters(providers, "gpt-5.4")
            self.assertEqual(selected["DEBATER_A"]["model"], "gpt-5.4")
            self.assertEqual(selected["DEBATER_B"]["model"], "gpt-5.4")
            self.assertEqual(selected["DEBATER_A"]["url"], selected["DEBATER_B"]["url"])

    def test_provider_base_url_resolves_to_chat_completions(self):
        with tempfile.TemporaryDirectory() as folder:
            env_path = Path(folder) / ".env"
            env_path.write_text("DEBATER_API_KEY=test-key\n", encoding="utf-8")
            self.assertEqual(load_config(env_path, self._config(folder))["DEBATER"]["url"], "https://example.test/v1/chat/completions")

    def test_scenario_requires_distinct_sides_and_motion(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text(json.dumps({"motion": "", "sides": ["A", "A"]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_scenario(path)

    def test_crossover_reverses_stances_with_same_personas(self):
        scenario = {"motion": "M", "sides": ["left", "right"], "personas": ["Auditor", "Falsifier"]}
        normal = build_schedule(scenario, crossfire_pairs=1, swap=False)
        swapped = build_schedule(scenario, crossfire_pairs=1, swap=True)
        self.assertEqual(normal[0]["persona"], swapped[0]["persona"])
        self.assertNotEqual(normal[0]["side"], swapped[0]["side"])
        self.assertEqual([x["phase"] for x in normal], [x["phase"] for x in swapped])

    def test_every_persona_card_is_regrounded_with_phase_and_stance(self):
        scenario = {"motion": "M", "sides": ["left", "right"], "context": "confirmed only"}
        for persona in PERSONAS:
            turn = {"persona": persona, "side": "left", "phase": "crossfire", "speaker": "A"}
            messages = speech_messages(scenario, turn, [{"speaker": "B", "side": "right", "speech": "Opponent claim"}])
            system = messages[0]["content"]
            self.assertIn("DO:", system)
            self.assertIn("AVOID:", system)
            self.assertIn("left", system)
            self.assertIn("crossfire", system)
            self.assertIn("Opponent claim", messages[1]["content"])

    def test_serious_topic_reduces_humor_in_surface_style(self):
        turn = {"persona": "Falsifier", "side": "left", "phase": "crossfire", "speaker": "A"}
        serious = speech_messages({"motion": "M", "sides": ["left", "right"], "tone": "SERIOUS"}, turn, [])[0]["content"]
        playful = speech_messages({"motion": "M", "sides": ["left", "right"], "tone": "PLAYFUL"}, turn, [])[0]["content"]
        self.assertIn("유머와 비꼼을 줄인다", serious)
        self.assertIn("가벼운 비유", playful)

    def test_prompt_priority_puts_stance_above_persona(self):
        turn = {"persona": "Socratic", "side": "left", "phase": "final_focus", "speaker": "A"}
        prompt = speech_messages({"motion": "M", "sides": ["left", "right"]}, turn, [])[0]["content"]
        self.assertLess(prompt.index("Protocol:"), prompt.index("Assigned Stance:"))
        self.assertLess(prompt.index("Assigned Stance:"), prompt.index("Persona:"))

    def test_playful_crossfire_uses_short_surface_budget(self):
        turn = {"persona": "Falsifier", "side": "left", "phase": "crossfire", "speaker": "A"}
        prompt = speech_messages({"motion": "M", "sides": ["left", "right"], "tone": "PLAYFUL"}, turn, [])[0]["content"]
        self.assertIn("1~2문장", prompt)
        self.assertIn("한 턴에는 한 과제만", prompt)

    def test_final_focus_budget_stays_short_but_allows_crystallization(self):
        turn = {"persona": "Socratic", "side": "left", "phase": "final_focus", "speaker": "A"}
        prompt = speech_messages({"motion": "M", "sides": ["left", "right"], "tone": "SERIOUS"}, turn, [])[0]["content"]
        self.assertIn("반드시 2문장 이내", prompt)\n        self.assertIn("한 문단", prompt)\n        self.assertIn("질문하지 마세요", prompt)
        self.assertIn("새 핵심 근거 없이", prompt)

    def test_records_never_include_api_keys(self):
        record = safe_record({"api_key": "secret-value", "content": "debate text", "nested": {"authorization": "Bearer secret-value"}})
        encoded = json.dumps(record)
        self.assertNotIn("secret-value", encoded)
        self.assertIn("debate text", encoded)

    def test_usage_token_counts_remain_measurable(self):
        record = safe_record({"usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}})
        self.assertEqual(record["usage"]["total_tokens"], 18)


if __name__ == "__main__":
    unittest.main()
