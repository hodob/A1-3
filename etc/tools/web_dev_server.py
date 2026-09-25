"""Zero-token local server for browser-testing the vanilla frontend against the API dispatcher."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse

from src.web_app.api import dispatch
from src.web_app.mock_service import MockDebateWebService

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "public"
STATIC = {
    "/": (PUBLIC / "index.html", "text/html; charset=utf-8"),
    "/index.html": (PUBLIC / "index.html", "text/html; charset=utf-8"),
    "/styles.css": (PUBLIC / "styles.css", "text/css; charset=utf-8"),
    "/app.js": (PUBLIC / "app.js", "application/javascript; charset=utf-8"),
    "/debate_stream.js": (PUBLIC / "debate_stream.js", "application/javascript; charset=utf-8"),
}

class Handler(BaseHTTPRequestHandler):
    _service = MockDebateWebService()

    def log_message(self, format, *args):
        pass

    def _write(self, status: int, raw: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            payload = {"ok": True, "data": {"status": "ready", "mode": "mock", "provider_call": False, "version": None}}
            self._write(200, json.dumps(payload).encode(), "application/json; charset=utf-8")
            return
        item = STATIC.get(path)
        if not item:
            self._write(404, b"Not Found", "text/plain; charset=utf-8")
            return
        file, content_type = item
        self._write(200, file.read_bytes(), content_type)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length)) if length else {}
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            self._write(400, json.dumps({"ok": False, "error": {"code": "INVALID_INPUT", "message": "JSON 요청 형식이 올바르지 않습니다."}}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        status, payload = dispatch(path, body, service=self._service)
        if path == "/api/debate-step" and "text/event-stream" in self.headers.get("Accept", ""):
            kind = "commit" if status == 200 else "error"
            data = payload["data"] if status == 200 else payload["error"]
            raw = f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")
            self._write(200, raw, "text/event-stream; charset=utf-8")
        else:
            self._write(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
