import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from etc.tools.web_dev_server import Handler
from src.web_app.contracts import DebateSession


class LocalDevServerTests(unittest.TestCase):
    def test_local_server_stays_mock_when_deployment_config_is_live(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(root + "/api/health", timeout=3) as response:
                health = json.load(response)
            self.assertEqual(health["data"]["mode"], "mock")
            body = json.dumps({"topic": "핫도그는 샌드위치인가?"}).encode()
            request = urllib.request.Request(root + "/api/analyze-topic", data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=3) as response:
                analysis = json.load(response)
            self.assertTrue(analysis["ok"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_local_mock_accepts_debate_sse_contract(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            session = DebateSession(motion="핫도그는 샌드위치다", side_labels=("찬성", "반대"), personas=("Socratic", "Falsifier"), tone="SERIOUS")
            body = json.dumps({"session": session.model_dump(mode="json"), "command": "NEXT"}).encode()
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_address[1]}/api/debate-step",
                data=body, headers={"Content-Type": "application/json", "Accept": "text/event-stream"}, method="POST",
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                raw = response.read().decode("utf-8")
                self.assertIn("text/event-stream", response.headers["Content-Type"])
            self.assertIn("event: commit", raw)
            self.assertIn('"utterance"', raw)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
