"""Provider-specific wire capabilities; core contracts remain Pydantic models."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError


T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_tool_calling: bool
    supports_forced_tool_call: bool
    supports_json_schema: bool


CURRENT_PROVIDER = ProviderCapabilities(True, False, False)


class ProviderOutputError(ValueError):
    def __init__(self, code: str, details: list[dict] | None = None):
        self.code = code
        self.details = details or []
        super().__init__(code)


class ProviderAdapter:
    def __init__(self, capabilities: ProviderCapabilities):
        self.capabilities = capabilities

    def build_structured_body(self, model: str, messages: list[dict], contract: type[T], tool_name: str) -> dict:
        body = {"model": model, "messages": messages}
        if self.capabilities.supports_tool_calling:
            body["tools"] = [{"type": "function", "function": {"name": tool_name, "description": "Return a locally validated structured result", "parameters": contract.model_json_schema()}}]
            if self.capabilities.supports_forced_tool_call:
                body["tool_choice"] = {"type": "function", "function": {"name": tool_name}}
        elif self.capabilities.supports_json_schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": tool_name, "schema": contract.model_json_schema()}}
        else:
            raise ValueError("Provider has no structured output transport")
        return body

    def parse_structured_response(self, payload: dict, contract: type[T], tool_name: str) -> T:
        try:
            message = payload["choices"][0]["message"]
            if self.capabilities.supports_tool_calling:
                calls = message.get("tool_calls") or []
                if len(calls) != 1 or calls[0]["function"]["name"] != tool_name:
                    raise ProviderOutputError("missing_or_wrong_tool_call")
                raw = json.loads(calls[0]["function"]["arguments"])
            else:
                raw = json.loads(message["content"])
            return contract.model_validate(raw)
        except ProviderOutputError:
            raise
        except ValidationError as exc:
            raise ProviderOutputError("local_validation_failed", exc.errors(include_url=False)) from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderOutputError("invalid_provider_output", [{"message": type(exc).__name__}]) from exc
