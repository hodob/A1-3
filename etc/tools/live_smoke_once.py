"""One deliberate live-provider smoke session.

Default is a zero-network dry run. Pass --execute explicitly after all local tests pass.
The run is intentionally short (3 debate turns) but crosses the major provider paths.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from src.web_app.live_service import LiveDebateWebService, LiveRuntimeDependencies
from src.web_app.live_smoke import MeteredDependencies, SmokeBudgetExceeded, SmokePlan, run_smoke
from src.web_app.service_factory import ServiceConfigError, _provider_url
from src.web_app.session_token import SessionTokenCodec
from src.runtime_config import DEFAULT_CONFIG_PATH, RuntimeConfigError, load_runtime_config, secret_values


DEFAULT_TOPIC = "핫도그는 샌드위치인가?"
DEFAULT_TURNS = 3
DEFAULT_BUDGET = 20_000


def _live_settings(env_path: Path, config_path: Path = DEFAULT_CONFIG_PATH) -> tuple[dict, str]:
    try:
        runtime = load_runtime_config(config_path)
        secrets = secret_values(env_path=env_path)
    except RuntimeConfigError as exc:
        raise ServiceConfigError(str(exc)) from exc
    required = {
        "DEBATER_API_KEY": secrets.get("DEBATER_API_KEY", "").strip(),
        "SESSION_SECRET": secrets.get("SESSION_SECRET", "").strip(),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ServiceConfigError("Live 비밀 설정 누락: " + ", ".join(missing))
    provider = {
        "url": _provider_url(runtime.provider.url),
        "api_key": required["DEBATER_API_KEY"],
        "model": runtime.provider.model,
    }
    return provider, required["SESSION_SECRET"]


def _dry_plan(args) -> dict:
    return {
        "mode": "DRY_RUN",
        "topic": args.topic,
        "planned_debate_turns": args.turns,
        "max_total_tokens": args.max_tokens,
        "provider_calls": 0,
        "coverage_goal": [
            "topic_analysis",
            "opening_A",
            "opening_B",
            "crossfire_A",
            "combined_action_stance_compliance",
            "state_patch_and_relation_extraction",
            "question_extraction_if_emitted",
            "signed_session_roundtrip",
            "neutral_summary",
            "per_call_token_usage",
        ],
        "execute_hint": "python -m etc.tools.live_smoke_once --execute",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one token-bounded live smoke session")
    parser.add_argument("--execute", action="store_true", help="Actually call the configured provider")
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS, choices=(1, 2, 3))
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output", type=Path, default=Path("etc/runs/live-smoke-once.json"))
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args(argv)

    if not args.execute:
        print(json.dumps(_dry_plan(args), ensure_ascii=False, indent=2))
        return 0

    try:
        plan = SmokePlan(topic=args.topic, debate_turns=args.turns, max_total_tokens=args.max_tokens)
        provider, secret = _live_settings(args.env, args.config)
        deps = MeteredDependencies(LiveRuntimeDependencies(), max_total_tokens=plan.max_total_tokens)
        codec = SessionTokenCodec(secret)
        service = LiveDebateWebService(provider=provider, codec=codec, deps=deps, timeout=args.timeout)
        report = run_smoke(service, codec, deps, plan)
        report["mode"] = "LIVE"
        report["model"] = provider["model"]
        report["provider_url_redacted"] = provider["url"].split("/chat/completions")[0] + "/chat/completions"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "status": report["status"],
            "output": str(args.output),
            "calls": report["usage"]["calls"],
            "total_tokens": report["usage"]["total_tokens"],
            "state_counts": report["state_counts"],
            "coverage": report["coverage"],
        }, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "PASS" else 2
    except SmokeBudgetExceeded as exc:
        print(f"실측 토큰 예산 중단: {exc}", file=sys.stderr)
        return 3
    except (ServiceConfigError, ValueError) as exc:
        print(f"환경 변수/설정 오류: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"실측 실패: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
