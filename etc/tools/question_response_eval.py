"""Six-case diagnostic only; requires completed reviewer labels."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

from pydantic import BaseModel, ConfigDict, Field

from src.debate_engine.debate_harness import load_config, select_debaters
from src.debate_engine.provider_adapter import CURRENT_PROVIDER, ProviderAdapter
from etc.tools.question_response_review import DEFAULT_FIXTURE, LABELS, RUBRIC, load_cases
from src.debate_engine.question_rubric import ResponseLabel


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: ResponseLabel
    reason: str = Field(min_length=1)


def require_human_labels(cases: list[dict]) -> None:
    missing = [case["id"] for case in cases if case.get("new_human_label") not in LABELS]
    if missing:
        raise ValueError("Reviewer labels missing: " + ", ".join(missing))


def summarize(rows: list[dict]) -> dict:
    confusion = Counter(f"{row['human_label']} → {row['model_label']}" for row in rows if not row["match"])
    return {"exact_match": sum(row["match"] for row in rows), "case_count": len(rows), "confusion_pairs": dict(sorted(confusion.items()))}


def classify_one(provider: dict, case: dict, rubric: str, timeout: float) -> tuple[Classification, dict]:
    adapter = ProviderAdapter(CURRENT_PROVIDER)
    messages = [
        {"role": "system", "content": rubric + "\n이 기준만 사용해 classify_response 도구로 label과 짧은 판정 근거를 반환하세요. 과거 정답 Label은 제공되지 않습니다."},
        {"role": "user", "content": f"질문: {case['question']}\n다음 발언: {case['response']}\nState 전제 충돌 근거: {case.get('state_premise_evidence') or '(제공되지 않음)'}"},
    ]
    body = adapter.build_structured_body(provider["model"], messages, Classification, "classify_response")
    request = urllib.request.Request(provider["url"], data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"}, method="POST")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc.reason}") from exc
    result = adapter.parse_structured_response(payload, Classification, "classify_response")
    return result, {"usage": payload.get("usage"), "elapsed_seconds": round(time.monotonic() - started, 3), "finish_reason": payload["choices"][0].get("finish_reason")}


def evaluate(cases: list[dict], provider: dict, timeout: float) -> dict:
    require_human_labels(cases)
    rubric = RUBRIC.read_text(encoding="utf-8")
    rows = []
    usages = []
    for case in cases:
        result, meta = classify_one(provider, case, rubric, timeout)
        rows.append({"case_id": case["id"], "human_label": case["new_human_label"], "model_label": result.label.value, "match": case["new_human_label"] == result.label.value, "model_reason": result.reason})
        usages.append(meta)
    return {"kind": "six_case_diagnostic", "created_at": datetime.now(timezone.utc).isoformat(), "model": provider["model"], "rows": rows, "summary": summarize(rows), "api_calls": len(usages), "usage_by_call": usages}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate six reannotated question responses")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    cases = load_cases(args.fixture)
    require_human_labels(cases)
    if args.output.exists():
        raise ValueError(f"Output exists: {args.output}")
    provider = select_debaters(load_config(args.env), args.model)["DEBATER_A"]
    result = evaluate(cases, provider, args.timeout)
    result["annotation_provenance"] = json.loads(args.fixture.read_text(encoding="utf-8")).get("annotation_provenance", "unspecified")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": result["rows"], "summary": result["summary"], "api_calls": result["api_calls"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
