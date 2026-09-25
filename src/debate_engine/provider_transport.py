"""Stream every Copa chat completion and assemble a validated complete response."""

from __future__ import annotations

import json
import urllib.request


def request_completion(provider: dict, body: dict, *, timeout: float = 90) -> dict:
    wire_body = {**body, "stream": True, "stream_options": {"include_usage": True}}
    request = urllib.request.Request(
        provider["url"],
        data=json.dumps(wire_body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
        method="POST",
    )
    content: list[str] = []
    tool_calls: dict[int, dict] = {}
    usage = None
    model = body["model"]
    finish_reason = None
    done = False
    event_lines: list[str] = []

    def consume_event() -> None:
        nonlocal usage, model, finish_reason, done
        data = "\n".join(event_lines)
        event_lines.clear()
        if not data:
            return
        if data == "[DONE]":
            done = True
            return
        chunk = json.loads(data)
        if chunk.get("error"):
            error = chunk["error"]
            code = error.get("code") if isinstance(error, dict) else None
            raise RuntimeError(f"LLM streaming response reported an error: {code or 'unknown'}")
        model = chunk.get("model") or model
        if chunk.get("usage") is not None:
            usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            if choice.get("finish_reason") is not None:
                finish_reason = choice["finish_reason"]
            delta = choice.get("delta") or {}
            part = delta.get("content")
            if isinstance(part, str):
                content.append(part)
            elif isinstance(part, list):
                content.extend(item.get("text", "") for item in part if isinstance(item, dict))
            for item in delta.get("tool_calls") or []:
                index = item["index"]
                call = tool_calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                if item.get("id"):
                    call["id"] = item["id"]
                if item.get("type"):
                    call["type"] = item["type"]
                function = item.get("function") or {}
                call["function"]["name"] += function.get("name") or ""
                call["function"]["arguments"] += function.get("arguments") or ""

    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").rstrip("\r\n")
            if not line:
                consume_event()
                if done:
                    break
            elif line.startswith("data:"):
                event_lines.append(line[5:].lstrip())
        if not done:
            consume_event()

    if not done or (not "".join(content).strip() and not tool_calls):
        raise RuntimeError("LLM streaming response was incomplete")
    return {
        "model": model,
        "choices": [{"message": {"content": "".join(content), "tool_calls": [tool_calls[index] for index in sorted(tool_calls)]}, "finish_reason": finish_reason}],
        "usage": usage,
    }
