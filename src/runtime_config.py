"""Runtime configuration split between committed non-secrets and secret environment values."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"
SECRET_KEYS = {"DEBATER_API_KEY", "SESSION_SECRET"}
NON_SECRET_ENV_KEYS = {"DEBATE_WEB_MODE", "DEBATER_URL", "DEBATE_MODEL"}


class RuntimeConfigError(ValueError):
    pass


class DebaterModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: Literal["GOOGLE", "ANTHROPIC", "OPENAI"]
    id: str = Field(min_length=1)


class ProviderRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    debater_models: tuple[DebaterModelConfig, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def distinct_debaters(self):
        companies = [item.company for item in self.debater_models]
        models = [item.id for item in self.debater_models]
        if len(companies) != len(set(companies)) or len(models) != len(set(models)):
            raise ValueError("debater_models must have distinct companies and model IDs")
        return self


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    web_mode: Literal["mock", "live"]
    provider: ProviderRuntimeConfig


def load_runtime_config(path: Path | str = DEFAULT_CONFIG_PATH) -> RuntimeConfig:
    path = Path(path)
    if not path.exists():
        raise RuntimeConfigError(f"설정 파일이 없습니다: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeConfigError(f"config.json을 읽을 수 없습니다: {type(exc).__name__}") from exc
    try:
        return RuntimeConfig.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        raise RuntimeConfigError(f"config.json 형식 오류: {'.'.join(map(str, first['loc']))}: {first['msg']}") from exc


def read_dotenv_secrets(path: Path | str, *, missing_ok: bool = False) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        if missing_ok:
            return {}
        raise RuntimeConfigError(f"비밀 설정 파일이 없습니다: {path}")
    result: dict[str, str] = {}
    forbidden: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeConfigError(f".env {number}행에 '='이 없습니다")
        key, value = line.split("=", 1)
        key = key.strip()
        if key in NON_SECRET_ENV_KEYS:
            forbidden.append(key)
            continue
        if key not in SECRET_KEYS:
            raise RuntimeConfigError(f".env에 허용되지 않은 키가 있습니다: {key}")
        result[key] = value.strip().strip('"').strip("'")
    if forbidden:
        raise RuntimeConfigError("비밀이 아닌 설정은 config.json으로 이동하세요: " + ", ".join(sorted(forbidden)))
    return result


def secret_values(*, env_path: Path | str | None = None, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    values = read_dotenv_secrets(env_path, missing_ok=True) if env_path is not None else {}
    source = os.environ if environ is None else environ
    for key in SECRET_KEYS:
        if source.get(key):
            values[key] = str(source[key]).strip()
    return values
