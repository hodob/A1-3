"""Signed, compressed client-carried session state for stateless serverless execution."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import zlib


class SessionTokenError(ValueError):
    pass


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class SessionTokenCodec:
    def __init__(self, secret: str, *, max_payload_bytes: int = 512_000):
        if not secret:
            raise ValueError("SESSION_SECRET is required")
        self._secret = secret.encode("utf-8")
        self._max_payload_bytes = max_payload_bytes

    def encode(self, payload: dict) -> str:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if len(raw) > self._max_payload_bytes:
            raise SessionTokenError("session payload is too large")
        body = _b64encode(zlib.compress(raw, level=6))
        signature = _b64encode(hmac.new(self._secret, body.encode("ascii"), hashlib.sha256).digest())
        return f"{body}.{signature}"

    def decode(self, token: str) -> dict:
        try:
            body, supplied = token.split(".", 1)
            expected = _b64encode(hmac.new(self._secret, body.encode("ascii"), hashlib.sha256).digest())
            if not hmac.compare_digest(supplied, expected):
                raise SessionTokenError("invalid session signature")
            raw = zlib.decompress(_b64decode(body))
            if len(raw) > self._max_payload_bytes:
                raise SessionTokenError("session payload is too large")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise SessionTokenError("invalid session payload")
            return value
        except SessionTokenError:
            raise
        except Exception as exc:
            raise SessionTokenError("invalid session token") from exc
