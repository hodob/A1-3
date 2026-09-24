"""Four-case semantic stance diagnostic through ordinary tool calling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

from pydantic import BaseModel, ConfigDict, Field

from src.debate_engine.debate_harness import load_config, select_debaters
from src.debate_engine.provider_adapter import CURRENT_PROVIDER, ProviderAdapter
from src.debate_engine.stance_compliance import StanceAssignment, StanceLabel, validate_utterance


class SemanticVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: StanceLabel
    reason: str = Field(min_length=1)


def judge(provider: dict, case: dict, timeout: float) -> tuple[SemanticVerdict, dict]:
    adapter = ProviderAdapter(CURRENT_PROVIDER)
    instructions = (
        "발언을 Assigned Stance 기준으로 판정하세요. SUPPORTS_ASSIGNED는 명시적 지지, "
        "COMPATIBLE_WITH_ASSIGNED는 국소적 양보·불확실성·세부 수정이며 최종 thesis 유지, "
        "AMBIGUOUS는 최종 입장을 안정적으로 알 수 없음, CONTRADICTS_ASSIGNED는 반대 thesis를 최종 결론으로 채택함입니다. "
        "표면적인 stance 단어 포함만 보지 말고 최종 논제 답변을 확인하세요. 추가 사실을 만들지 마세요. stance_verdict 도구를 호출하세요."
    )
    messages = [{"role": "system", "content": instructions}, {"role": "user", "content": json.dumps({"assigned_thesis": case["assigned_thesis"], "opposing_thesis": case["opposing_thesis"], "phase": case["phase"], "utterance": case["utterance"]}, ensure_ascii=False)}]
    body = adapter.build_structured_body(provider["model"], messages, SemanticVerdict, "stance_verdict")
    request = urllib.request.Request(provider["url"], data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"}, method="POST")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc.reason}") from exc
    verdict = adapter.parse_structured_response(payload, SemanticVerdict, "stance_verdict")
    return verdict, {"usage": payload.get("usage"), "elapsed_seconds": round(time.monotonic() - started, 3)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Minimal semantic stance check")
    parser.add_argument("--fixture", type=Path, default=Path("etc/fixtures/stance_diagnostic.json"))
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError(f"Output exists: {args.output}")
    cases = json.loads(args.fixture.read_text(encoding="utf-8"))["cases"]
    provider = select_debaters(load_config(args.env), args.model)["DEBATER_A"]
    rows = []
    for case in cases:
        local = validate_utterance(case["utterance"], StanceAssignment(case["assigned_thesis"], case["opposing_thesis"]), phase=case["phase"])
        verdict, meta = judge(provider, case, args.timeout)
        rows.append({"case_id": case["id"], "expected_semantic": case["expected_semantic"], "local_label": local.label.value, "local_accepted": local.accepted, "model_label": verdict.label.value, "model_reason": verdict.reason, "expected_match": verdict.label.value == case["expected_semantic"], "usage": meta["usage"]})
    result = {"model": provider["model"], "api_calls": len(rows), "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
