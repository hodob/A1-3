from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


class ActionStatusUxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (PUBLIC / 'index.html').read_text(encoding='utf-8')
        cls.css = (PUBLIC / 'styles.css').read_text(encoding='utf-8')
        cls.js = (PUBLIC / 'app.js').read_text(encoding='utf-8')

    def test_operation_status_is_viewport_fixed_and_visually_prominent(self):
        self.assertIn('id="app-status"', self.html)
        self.assertIn('class="status-line"', self.html)
        self.assertIn('.status-line:not(:empty) { position: fixed;', self.css)
        self.assertIn('bottom: max(20px, env(safe-area-inset-bottom));', self.css)

    def test_status_copy_uses_concrete_situation_language(self):
        expected = (
            '주제를 살펴보고 있어요.',
            '다음에 확인할 내용을 준비하고 있어요.',
            '토론할 문장을 정리하고 있어요.',
            '다음 발언을 준비하고 있어요.',
            '질문을 전달하고 있어요.',
            '토론 정리를 준비하고 있어요.',
        )
        for text in expected:
            self.assertIn(text, self.js)
        self.assertNotIn("setStatus('진행 중')", self.js)

    def test_done_actions_use_consistent_button_group(self):
        self.assertIn('class="done-actions"', self.html)
        self.assertIn('id="restart" class="button full"', self.html)
        self.assertIn('id="reread-debate" class="button secondary full"', self.html)
        self.assertIn('.done-actions .button.full { width: 100%;', self.css)


if __name__ == '__main__':
    unittest.main()
