"""Live, human-labelled classification benchmarks for design section 68."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from src.debate_engine.debate_harness import ConfigError, load_config, select_debaters


def validate_tool_arguments(raw: str, schema: dict) -> dict:
    """Validate returned arguments locally; provider strict mode is not trusted."""
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Tool arguments are not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Tool arguments must be an object")
    required = set(schema.get("required", []))
    properties = schema.get("properties", {})
    if not required.issubset(value):
        raise ValueError("Tool arguments missing required fields")
    if schema.get("additionalProperties") is False and set(value) - set(properties):
        raise ValueError("Tool arguments contain extra fields")
    for field, item in value.items():
        field_schema = properties.get(field)
        if field_schema is None:
            continue
        kind = field_schema.get("type")
        if kind == "string" and not isinstance(item, str):
            raise ValueError(f"{field} must be a string")
        if kind == "integer" and type(item) is not int:
            raise ValueError(f"{field} must be an integer")
        if kind == "boolean" and type(item) is not bool:
            raise ValueError(f"{field} must be a boolean")
        if "enum" in field_schema and item not in field_schema["enum"]:
            raise ValueError(f"{field} outside allowed enum")
    return value


def score_predictions(cases: list[dict], predictions: dict[str, str | None], same_label: str | None = None) -> dict:
    total = len(cases)
    attempted = 0
    correct = 0
    false_merges = 0
    confusion: dict[str, dict[str, int]] = {}
    for case in cases:
        gold = case["gold"]
        predicted = predictions.get(case["id"])
        if predicted is None:
            continue
        attempted += 1
        correct += predicted == gold
        false_merges += bool(same_label and predicted == same_label and gold != same_label)
        row = confusion.setdefault(gold, {})
        row[predicted] = row.get(predicted, 0) + 1
    return {
        "total": total,
        "attempted": attempted,
        "missing": total - attempted,
        "correct": correct,
        "accuracy_all": correct / total if total else None,
        "accuracy_attempted": correct / attempted if attempted else None,
        "false_merges": false_merges,
        "confusion": confusion,
    }


def load_benchmark(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("task"), str) or not data["task"]:
        raise ValueError(f"Invalid benchmark task: {path}")
    if not isinstance(data.get("instructions"), str) or not data["instructions"]:
        raise ValueError(f"Invalid benchmark instructions: {path}")
    labels = data.get("labels")
    cases = data.get("cases")
    if not isinstance(labels, list) or not labels or len(set(labels)) != len(labels) or any(not isinstance(x, str) for x in labels):
        raise ValueError(f"Invalid benchmark labels: {path}")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"Empty benchmark: {path}")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not isinstance(case.get("input"), str) or case.get("gold") not in labels or case["id"] in seen:
            raise ValueError(f"Invalid benchmark case: {path}")
        seen.add(case["id"])
    return data


def call_classifier(provider: dict, benchmark: dict, case: dict, timeout: float) -> tuple[str, dict]:
    schema = {"type": "object", "properties": {"label": {"type": "string", "enum": benchmark["labels"]}}, "required": ["label"], "additionalProperties": False}
    body = {
        "model": provider["model"],
        "messages": [
            {"role": "system", "content": benchmark["instructions"] + "\n반드시 classify 도구를 호출하세요. 근거 없는 보충 설명은 하지 마세요."},
            {"role": "user", "content": case["input"]},
        ],
        "tools": [{"type": "function", "function": {"name": "classify", "description": "Record the selected label", "strict": True, "parameters": schema}}],
    }
    request = urllib.request.Request(
        provider["url"],
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
        method="POST",
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc.reason}") from exc
    try:
        choice = payload["choices"][0]
        calls = choice["message"].get("tool_calls") or []
        if len(calls) != 1 or calls[0]["function"]["name"] != "classify":
            raise ValueError("Expected one classify tool call")
        arguments = validate_tool_arguments(calls[0]["function"]["arguments"], schema)
        metadata = {"model": payload.get("model"), "usage": payload.get("usage"), "finish_reason": choice.get("finish_reason"), "elapsed_seconds": round(time.monotonic() - start, 3)}
        return arguments["label"], metadata
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid tool response: {exc}") from exc


def run_benchmarks(paths: list[Path], provider: dict, output: Path, timeout: float) -> dict:
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    benchmarks = [load_benchmark(path) for path in paths]
    tasks = [item["task"] for item in benchmarks]
    if len(set(tasks)) != len(tasks):
        raise ValueError("Duplicate task names")
    output.mkdir(parents=True)
    (output / "manifest.json").write_text(json.dumps({"model": provider["model"], "started_at": datetime.now(timezone.utc).isoformat(), "benchmarks": [str(path) for path in paths]}, ensure_ascii=False, indent=2), encoding="utf-8")
    summaries: dict[str, dict] = {}
    for benchmark in benchmarks:
        task = benchmark["task"]
        predictions: dict[str, str | None] = {}
        records: list[dict] = []
        for case in benchmark["cases"]:
            try:
                label, metadata = call_classifier(provider, benchmark, case, timeout)
                record = {"id": case["id"], "gold": case["gold"], "predicted": label, "metadata": metadata}
                predictions[case["id"]] = label
            except RuntimeError as exc:
                record = {"id": case["id"], "gold": case["gold"], "predicted": None, "error": str(exc)}
                predictions[case["id"]] = None
            records.append(record)
            print(f"{task}: {len(records)}/{len(benchmark['cases'])}", flush=True)
        (output / f"{task}.jsonl").write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
        summary = score_predictions(benchmark["cases"], predictions, "SAME" if task == "claim_identity" else None)
        summaries[task] = summary
    (output / "summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    return summaries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run human-labelled section 68 classification cases on a real model")
    parser.add_argument("--benchmark", type=Path, nargs="+", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args(argv)
    try:
        provider = select_debaters(load_config(args.env), args.model)["DEBATER_A"]
        result = run_benchmarks(args.benchmark, provider, args.output, args.timeout)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if all(item["missing"] == 0 for item in result.values()) else 1
    except (ConfigError, ValueError, RuntimeError, OSError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
