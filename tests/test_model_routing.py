import json
import random
import tempfile
import unittest
from pathlib import Path

from src.runtime_config import RuntimeConfigError, load_runtime_config
from src.web_app.contracts import AnalyzeTopicRequest, CreateMotionRequest, DebateSession, DebateStepRequest
from src.web_app.live_service import LiveDebateWebService
from src.web_app.session_token import SessionTokenCodec
from tests.test_live_web_service import FakeDeps


MODELS = (
    {"company": "GOOGLE", "id": "gemini-3-flash"},
    {"company": "ANTHROPIC", "id": "claude-haiku-4"},
    {"company": "OPENAI", "id": "gpt-5.4-mini"},
)


class RecordingDeps(FakeDeps):
    def __init__(self):
        super().__init__()
        self.generation_models = []
        self.generation_streams = []
        self.compliance_models = []
        self.extraction_models = []

    def generate_text(self, provider, messages, timeout=90):
        self.generation_models.append(provider["model"])
        self.generation_streams.append(bool(provider.get("stream")))
        return super().generate_text(provider, messages, timeout)

    def check_compliance(self, provider, **kwargs):
        self.compliance_models.append(provider["model"])
        return super().check_compliance(provider, **kwargs)

    def extract_patch(self, provider, turn, state, timeout, feedback=None):
        self.extraction_models.append(provider["model"])
        return super().extract_patch(provider, turn, state, timeout, feedback)


class ModelRoutingTests(unittest.TestCase):
    def test_config_accepts_three_company_model_array(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({"web_mode": "live", "provider": {
                "url": "https://example.test/v1", "model": "gpt-5.4", "debater_models": MODELS,
            }}), encoding="utf-8")
            config = load_runtime_config(path)
        self.assertEqual([item.id for item in config.provider.debater_models], [
            "gemini-3-flash", "claude-haiku-4", "gpt-5.4-mini",
        ])

    def test_config_rejects_duplicate_company_or_model(self):
        for candidates in (
            [MODELS[0], {"company": "GOOGLE", "id": "other-model"}],
            [MODELS[0], {"company": "ANTHROPIC", "id": "gemini-3-flash"}],
        ):
            with self.subTest(candidates=candidates), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "config.json"
                path.write_text(json.dumps({"web_mode": "live", "provider": {
                    "url": "https://example.test/v1", "model": "gpt-5.4", "debater_models": candidates,
                }}), encoding="utf-8")
                with self.assertRaises(RuntimeConfigError):
                    load_runtime_config(path)

    def test_debaters_use_distinct_models_and_coordinator_stays_fixed(self):
        deps = RecordingDeps()
        codec = SessionTokenCodec("unit-test-session-secret-123456789")
        service = LiveDebateWebService(
            provider={"url": "https://example.test/v1/chat/completions", "api_key": "test", "model": "gpt-5.4"},
            debater_models=MODELS, codec=codec, deps=deps, rng=random.Random(7),
        )
        analysis = service.analyze_topic(AnalyzeTopicRequest(topic="핫도그는 샌드위치인가?"))
        motion = service.create_motion(CreateMotionRequest(analysis=analysis, edit_count=0))
        session = DebateSession(motion=motion.motion, side_labels=motion.side_labels, personas=motion.personas, tone=motion.tone)
        first = service.debate_step(DebateStepRequest(session=session, command="NEXT"))
        selected = codec.decode(first.session.engine_token)["debater_models"]
        second = service.debate_step(DebateStepRequest(session=first.session, command="NEXT"))
        self.assertNotEqual(selected["A"], selected["B"])
        self.assertEqual(deps.generation_models, [selected["A"], selected["B"]])
        self.assertEqual(deps.generation_streams, [True, True])
        self.assertEqual(deps.compliance_models, ["gpt-5.4", "gpt-5.4"])
        self.assertEqual(deps.extraction_models, ["gpt-5.4", "gpt-5.4"])
        self.assertEqual(codec.decode(second.session.engine_token)["debater_models"], selected)


if __name__ == "__main__":
    unittest.main()
