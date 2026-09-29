from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
LEGACY_DOCS = ROOT / "docs-legacy"


class ProjectDocumentationTests(unittest.TestCase):
    def test_env_example_documents_secrets_only_and_config_documents_runtime(self):
        env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("DEBATER_API_KEY", env_text)
        self.assertIn("SESSION_SECRET", env_text)
        for key in ("DEBATE_WEB_MODE", "DEBATER_URL", "DEBATE_MODEL"):
            self.assertNotIn(key, env_text)
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        self.assertIn("web_mode", config)
        self.assertIn("url", config["provider"])
        self.assertIn("model", config["provider"])

    def test_readme_has_local_test_and_deploy_guidance(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for phrase in ("Mock", "Vercel", "환경 변수", "config.json", "unittest", "web_dev_server", "기술 스택", "배포 URL"):
            self.assertIn(phrase, text)

    def test_service_plan_and_architecture_docs_exist(self):
        plan = (LEGACY_DOCS / "SERVICE_PLAN.md").read_text(encoding="utf-8")
        arch = (LEGACY_DOCS / "WEB_MVP_ARCHITECTURE.md").read_text(encoding="utf-8")
        for phrase in ("Home", "Debate", "How It Works", "Audience Question", "Neutral Summary", "타겟 사용자", "입력", "출력", "실패 처리"):
            self.assertIn(phrase, plan)
        for phrase in ("Browser", "Python", "Environment Variable", "Loading", "Failure"):
            self.assertIn(phrase, arch)

    def test_assignment_defense_qa_covers_evaluation_topics(self):
        text = (LEGACY_DOCS / "DEFENSE_QA.md").read_text(encoding="utf-8")
        for phrase in ("HTML", "CSS", "JavaScript", "fetch", "환경 변수", "응답 지연", "API 키 유출", "프레임워크"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
