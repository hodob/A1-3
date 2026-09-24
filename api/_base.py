"""Shared Vercel Python HTTP adapter."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from src.web_app.api import dispatch


class ApiHandler(BaseHTTPRequestHandler):
    route = ""
    max_body_bytes = 1_000_000

    def _write(self, status: int, payload: dict):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                self._write(400, {"ok": False, "error": {"code": "INVALID_INPUT", "message": "요청 본문이 비어 있습니다."}})
                return
            if length > self.max_body_bytes:
                self._write(413, {"ok": False, "error": {"code": "PAYLOAD_TOO_LARGE", "message": "요청이 너무 깁니다."}})
                return
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            self._write(400, {"ok": False, "error": {"code": "INVALID_INPUT", "message": "JSON 요청 형식이 올바르지 않습니다."}})
            return
        status, payload = dispatch(self.route, body)
        self._write(status, payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()
