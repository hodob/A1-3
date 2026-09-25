from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ModeratorUxTests(unittest.TestCase):
    def test_moderator_script_and_timeline_are_wired(self):
        html = (ROOT / 'public' / 'index.html').read_text(encoding='utf-8')
        js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('/debate_moderator.js', html)
        self.assertIn('moderatorEvents', js)
        self.assertIn('moderatorCard', js)
        self.assertIn('SaiModerator.eventsForStep', js)

    def test_vercel_routes_moderator_script(self):
        config = json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))
        rewrites = {item['source']: item['destination'] for item in config['rewrites']}
        self.assertEqual(rewrites.get('/debate_moderator.js'), '/public/debate_moderator.js')

    def test_compact_current_stage_is_the_sticky_phase_surface(self):
        html = (ROOT / 'public' / 'index.html').read_text(encoding='utf-8')
        css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        self.assertIn('id="current-stage"', html)
        self.assertIn('id="stage-description" class="stage-description"', html)
        self.assertNotIn('class="phase-intro"', html)
        self.assertIn('.current-stage { position: sticky;', css)
        self.assertIn('.stage-description { display: none;', css)
        self.assertIn('.current-stage strong { white-space: nowrap;', css)

    def test_final_focus_prompt_enforces_compact_one_paragraph_close(self):
        source = (ROOT / 'src' / 'debate_engine' / 'debate_harness.py').read_text(encoding='utf-8')
        self.assertIn('반드시 2문장 이내', source)
        self.assertIn('한 문단', source)
        self.assertIn('질문하지 마세요', source)


if __name__ == '__main__':
    unittest.main()
