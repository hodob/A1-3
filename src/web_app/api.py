"""Pure API dispatcher. Vercel handlers are thin HTTP adapters around this module."""
from __future__ import annotations

import os
import re

from pydantic import ValidationError

from .contracts import AnalyzeTopicRequest, ContextStepRequest, CreateMotionRequest, DebateStepRequest, NeutralSummaryRequest
from .service_factory import ServiceConfigError, get_default_service
from .errors import SafeFailure
from src.runtime_config import load_runtime_config


def _success(data):
    return 200, {"ok": True, "data": data.model_dump(mode="json")}


def _error(status: int, code: str, message: str):
    return status, {"ok": False, "error": {"code": code, "message": message}}


def dispatch(path: str, body: dict, service=None):
    try:
        service = service or get_default_service()
        if path == "/api/health":
            mode = load_runtime_config().web_mode
            sha = os.getenv("VERCEL_GIT_COMMIT_SHA", "").lower()
            version = sha[:7] if re.fullmatch(r"[0-9a-f]{40,64}", sha) else None
            return 200, {"ok": True, "data": {"status": "ready", "mode": mode, "provider_call": False, "version": version}}
        if path == "/api/analyze-topic":
            return _success(service.analyze_topic(AnalyzeTopicRequest.model_validate(body)))
        if path == "/api/context-step":
            return _success(service.context_step(ContextStepRequest.model_validate(body)))
        if path == "/api/create-motion":
            return _success(service.create_motion(CreateMotionRequest.model_validate(body)))
        if path == "/api/debate-step":
            return _success(service.debate_step(DebateStepRequest.model_validate(body)))
        if path == "/api/neutral-summary":
            return _success(service.neutral_summary(NeutralSummaryRequest.model_validate(body)))
        return _error(404, "NOT_FOUND", "요청한 API를 찾을 수 없습니다.")
    except SafeFailure:
        return _error(422, "SAFE_FAILURE", "이번 발언을 안전하게 확정하지 못했습니다. 다시 시도해주세요.")
    except ServiceConfigError as exc:
        return _error(503, "CONFIG_ERROR", str(exc))
    except ValidationError as exc:
        return _error(400, "INVALID_INPUT", exc.errors(include_url=False)[0]["msg"])
    except ValueError as exc:
        return _error(400, "INVALID_INPUT", str(exc))
    except TimeoutError:
        return _error(504, "TIMEOUT", "응답이 지연되고 있습니다. 다시 시도해주세요.")
    except Exception:
        return _error(500, "API_ERROR", "응답을 생성하지 못했습니다. 다시 시도해주세요.")
