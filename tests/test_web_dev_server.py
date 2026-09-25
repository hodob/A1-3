import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from etc.tools.web_dev_server import Handler


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


if __name__ == "__main__":
    unittest.main()
