"""Build the web service from committed non-secret config plus secret environment values."""
from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import re

from src.runtime_config import DEFAULT_CONFIG_PATH, RuntimeConfigError, load_runtime_config
from .live_service import LiveDebateWebService
from .mock_service import MockDebateWebService
from .session_token import SessionTokenCodec


class ServiceConfigError(ValueError):
    pass


def _provider_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not re.match(r"^https?://", value):
        raise ServiceConfigError("provider.url은 http(s) 주소여야 합니다.")
    if value.endswith("/v1"):
        return value + "/chat/completions"
    if value.endswith("/chat/completions"):
        return value
    raise ServiceConfigError("provider.url은 /v1 또는 /chat/completions로 끝나야 합니다.")


def build_service(*, config_path: Path | str = DEFAULT_CONFIG_PATH):
    try:
        config = load_runtime_config(config_path)
    except RuntimeConfigError as exc:
        raise ServiceConfigError(str(exc)) from exc
    if config.web_mode == "mock":
        return MockDebateWebService()
    required = {
        "DEBATER_API_KEY": os.getenv("DEBATER_API_KEY", "").strip(),
        "SESSION_SECRET": os.getenv("SESSION_SECRET", "").strip(),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ServiceConfigError("Live 비밀 환경 변수 누락: " + ", ".join(missing))
    provider = {
        "url": _provider_url(config.provider.url),
        "api_key": required["DEBATER_API_KEY"],
        "model": config.provider.model,
    }
    return LiveDebateWebService(provider=provider, codec=SessionTokenCodec(required["SESSION_SECRET"]))


@lru_cache(maxsize=1)
def get_default_service():
    return build_service()
