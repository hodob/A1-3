"""CLI prototype harness for the AI Debate Harness design.

Uses one debate provider and selects one model per run.
Human review, not model self-grading, determines validation results.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Callable
from datetime import datetime, timezone
from pathlib import Path

from .stance_compliance import StanceAssignment, finalize_utterance
from .provider_transport import request_completion
from src.runtime_config import DEFAULT_CONFIG_PATH, RuntimeConfigError, load_runtime_config, secret_values


PERSONAS = {
    "Auditor": "중요한 주장에 근거를 요구하고 추론을 점검한다. 답변받은 질문은 반복하지 않는다.",
    "Socratic": "정의와 숨은 전제를 묻고 모호한 주장을 구체화한다.",
    "Falsifier": "반례와 경계 사례로 일반화를 시험한다.",
    "Pragmatist": "실제 결과, 비용, 실행 가능성과 상충 관계를 비교한다.",
    "Principlist": "원칙, 권리, 기준의 일관성을 점검한다.",
    "Synthesist": "강한 논거를 인정하고 주장 범위를 조정하며 쟁점을 압축한다.",
}
PERSONA_CARDS = {
    "Auditor": "DO: 중요한 경험적 주장에 근거를 요구하고 추론 연결을 점검한다. 충분히 답한 질문은 닫고 강한 반박은 인정한다. AVOID: 모든 문장에 출처를 요구하거나 이미 제공된 근거를 다시 요구하지 않는다. Style: 직접성 높음, 길이 짧음, 유머 낮음.",
    "Socratic": "DO: 정의를 확인하고 숨은 전제를 묻고 모호한 주장을 구체화한다. 상대가 이미 답한 정의는 받아들인다. AVOID: 질문만 연달아 던지거나 답변을 무시하지 않는다. Style: 직접성 중간, 길이 중간, 유머 낮음.",
    "Falsifier": "DO: 반례와 경계 사례로 상대 일반화의 적용 범위를 시험한다. 반례가 해결되면 다른 핵심 쟁점으로 이동한다. AVOID: 같은 반례를 근거 없이 반복하거나 가상 사례를 현실 사실처럼 말하지 않는다. Style: 직접성 높음, 길이 짧음, 유머 중간.",
    "Pragmatist": "DO: 실제 결과, 비용, 실행 가능성과 상충 관계를 비교한다. 불확실한 효과는 불확실하다고 말한다. AVOID: 근거 없는 비용 수치나 성과를 만들지 않는다. Style: 직접성 높음, 길이 중간, 유머 중간.",
    "Principlist": "DO: 원칙과 권리의 기준을 명시하고 같은 기준을 유사 사례에 일관되게 적용한다. AVOID: 원칙만 반복하거나 상대의 실제 결과 우려를 무시하지 않는다. Style: 직접성 중간, 길이 중간, 격식 높음.",
    "Synthesist": "DO: 상대의 강한 논거를 인정하고 필요하면 자기 주장을 한정·수정하며 핵심 충돌을 압축한다. AVOID: 양쪽 말을 기계적으로 절충하거나 자기 입장을 잃지 않는다. Style: 직접성 중간, 길이 중간, 유머 낮음.",
}


class ConfigError(ValueError):
    pass


def load_config(path: Path, config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """Load provider URL from config.json and API key from .env/environment."""
    try:
        runtime = load_runtime_config(config_path)
        secrets = secret_values(env_path=path)
    except RuntimeConfigError as exc:
        raise ConfigError(str(exc)) from exc
    api_key = secrets.get("DEBATER_API_KEY", "").strip()
    if not api_key:
        raise ConfigError("DEBATER 비밀 설정 누락: DEBATER_API_KEY")
    url = runtime.provider.url.strip().rstrip("/")
    if not re.match(r"^https?://", url):
        raise ConfigError("provider.url은 http(s) 주소여야 합니다")
    if url.endswith("/v1"):
        url += "/chat/completions"
    elif not url.endswith("/chat/completions"):
        raise ConfigError("provider.url은 /v1 또는 /chat/completions로 끝나야 합니다")
    return {"DEBATER": {"url": url, "api_key": api_key}}


def select_debaters(providers: dict, model: str) -> dict:
    shared = providers["DEBATER"]
    if not model.strip():
        raise ConfigError("실행할 모델명이 비어 있습니다")
    return {
        "DEBATER_A": {"url": shared["url"], "api_key": shared["api_key"], "model": model},
        "DEBATER_B": {"url": shared["url"], "api_key": shared["api_key"], "model": model},
    }


def load_scenario(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("시나리오는 JSON 객체여야 합니다")
    motion = value.get("motion")
    sides = value.get("sides")
    personas = value.get("personas")
    if not isinstance(motion, str) or not motion.strip():
        raise ValueError("motion이 비어 있습니다")
    if not isinstance(sides, list) or len(sides) != 2 or any(not isinstance(x, str) or not x.strip() for x in sides) or sides[0] == sides[1]:
        raise ValueError("sides에는 서로 다른 두 입장이 필요합니다")
    if not isinstance(personas, list) or len(personas) != 2 or any(x not in PERSONAS for x in personas):
        raise ValueError("personas에는 라이브러리의 두 Persona가 필요합니다")
    for name in ("context", "fact_anchor"):
        if name in value and not isinstance(value[name], str):
            raise ValueError(f"{name}은 문자열이어야 합니다")
    if value.get("tone", "SERIOUS") not in ("SERIOUS", "PLAYFUL"):
        raise ValueError("tone은 SERIOUS 또는 PLAYFUL이어야 합니다")
    return value


def build_schedule(scenario: dict, crossfire_pairs: int, swap: bool) -> list[dict[str, str]]:
    if not 1 <= crossfire_pairs <= 12:
        raise ValueError("crossfire_pairs는 1~12여야 합니다")
    sides = list(reversed(scenario["sides"])) if swap else scenario["sides"]
    speakers = [{"speaker": label, "persona": scenario["personas"][i], "side": sides[i]} for i, label in enumerate(("A", "B"))]
    order = [("opening", 0), ("opening", 1)]
    order += [("crossfire", i % 2) for i in range(crossfire_pairs * 2)]
    order += [("rebuttal", 0), ("rebuttal", 1), ("final_focus", 0), ("final_focus", 1)]
    return [{"turn": str(i + 1), "phase": phase, **speakers[index]} for i, (phase, index) in enumerate(order)]


def safe_record(value):
    """Remove credential-bearing fields from metadata before writing records."""
    if isinstance(value, dict):
        return {
            k: (
                "[REDACTED]"
                if k.lower() in {"token", "access_token", "refresh_token", "api_key", "authorization", "secret", "password"}
                or k.lower().endswith("_api_key")
                else safe_record(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [safe_record(x) for x in value]
    return value


def call_model(provider: dict[str, str], messages: list[dict[str, str]], *, timeout: float = 90, on_delta: Callable[[str], None] | None = None) -> tuple[str, dict]:
    body: dict = {"model": provider["model"], "messages": messages}
    started = time.monotonic()
    try:
        payload = request_completion(provider, body, timeout=timeout, on_text_delta=on_delta)
    except urllib.error.HTTPError as exc:
        # Provider error bodies can contain sensitive material; do not persist or print them.
        raise RuntimeError(f"LLM HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM 연결 실패: {exc.reason}") from exc
    try:
        message = payload["choices"][0]["message"]
        content = message["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str) or not content.strip():
            raise ValueError("빈 응답")
        metadata = {"model": payload.get("model", provider["model"]), "usage": payload.get("usage"), "finish_reason": payload["choices"][0].get("finish_reason"), "elapsed_seconds": round(time.monotonic() - started, 3)}
        return content.strip(), safe_record(metadata)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("LLM 응답에서 choices[0].message.content를 읽을 수 없습니다") from exc


def speech_messages(scenario: dict, turn: dict, transcript: list[dict]) -> list[dict[str, str]]:
    phase = turn["phase"]
    instruction = {
        "opening": "짧게 핵심 주장과 이유 1~2개를 제시하세요.",
        "crossfire": "직전 상대 발언의 한 핵심 지점에 직접 반응하고 새 반박 또는 질문 하나를 추가하세요.",
        "rebuttal": "드러난 핵심 충돌을 직접 해결하세요.",
        "final_focus": "새 핵심 근거 없이 가장 중요한 이유 1~2개만 남기세요.",
        "audience_response": "관객 질문에 직접 답하고 필요하면 자신의 핵심 주장을 한정하세요.",
    }[phase]
    tone = scenario.get("tone", "SERIOUS")
    surface_style = (
        "주제가 진지하다. 사실 명확성과 불확실성 표현을 우선하고 유머와 비꼼을 줄인다."
        if tone == "SERIOUS"
        else "가벼운 비유와 논증에서 나온 유머는 가능하다. 상대의 인격은 공격하지 않는다."
    )
    sentence_budget = {
        "opening": "2~3문장",
        "crossfire": "1~2문장" if tone == "PLAYFUL" else "1~3문장",
        "audience_response": "1~2문장",
        "rebuttal": "2~3문장",
        "final_focus": "2문장 안팎",
    }[phase]
    system = (
        "당신은 관전형 토론의 참가자입니다. 실제 사용자 사건, 통계, 연구, 인용을 지어내지 마세요. "
        "상대가 실제로 한 말에 반응하고, 유효한 반론은 인정하며, 불확실하면 밝히세요. "
        f"사실 기준: {scenario.get('fact_anchor', '(제공되지 않음)')}. "
        "Protocol: 질문에 답하고 상대의 실제 주장만 다루세요. 국소적 양보와 세부 주장 수정은 허용됩니다. "
        f"Assigned Stance: {turn['side']}. 최종 Thesis를 상대편 입장으로 뒤집지 마세요. "
        f"Persona: {turn['persona']} — {PERSONA_CARDS[turn['persona']]} "
        f"단계: {phase}. {instruction} "
        + ("최종 결론에서는 '제 최종 입장은 <Assigned Stance>'로 입장을 명시하고, 설명도 그 결론과 일치시켜 주세요. " if phase == "final_focus" else "")
        + f"Surface Style: {surface_style} 토론 발언만 한국어로 출력하세요. 이 단계는 {sentence_budget}을 기본 상한으로 삼고, 한 턴에는 한 과제만 처리하세요."
    )
    history = "\n".join(f"{item['speaker']}({item['side']}): {item['speech']}" for item in transcript[-12:]) or "(첫 발언)"
    user = f"논제: {scenario['motion']}\n맥락: {scenario.get('context', '(없음)')}\n사실 기준: {scenario.get('fact_anchor', '(없음)')}\n이전 발언:\n{history}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(safe_record(record), ensure_ascii=False) + "\n")


def run(scenario: dict, providers: dict, output: Path, crossfire_pairs: int, crossover: bool, timeout: float) -> None:
    if output.exists():
        raise ValueError(f"출력 폴더가 이미 있습니다: {output}")
    output.mkdir(parents=True)
    (output / "scenario.json").write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "run.json").write_text(json.dumps({"started_at": datetime.now(timezone.utc).isoformat(), "crossfire_pairs": crossfire_pairs, "crossover": crossover, "models": {key: value["model"] for key, value in providers.items()}}, ensure_ascii=False, indent=2), encoding="utf-8")
    for swap in ([False, True] if crossover else [False]):
        label = "swapped" if swap else "normal"
        transcript: list[dict] = []
        path = output / f"{label}.jsonl"
        for turn in build_schedule(scenario, crossfire_pairs, swap):
            provider = providers[f"DEBATER_{turn['speaker']}"]
            try:
                base_messages = speech_messages(scenario, turn, transcript)
                metadata = []

                def generate(feedback: str) -> str:
                    messages = base_messages if not feedback else [*base_messages, {"role": "user", "content": feedback}]
                    utterance, meta = call_model(provider, messages, timeout=timeout)
                    metadata.append(meta)
                    return utterance

                opposing = scenario["sides"][0] if turn["side"] == scenario["sides"][1] else scenario["sides"][1]
                from stance_api_diagnostic import judge
                def semantic_check(speech, assignment, phase):
                    from .stance_compliance import StanceAssessment, StanceLabel
                    verdict, meta = judge(provider, {"assigned_thesis": assignment.assigned_thesis, "opposing_thesis": assignment.opposing_thesis, "phase": phase, "utterance": speech}, timeout)
                    metadata.append(meta)
                    return StanceAssessment(verdict.label, verdict.label in (StanceLabel.SUPPORTS_ASSIGNED, StanceLabel.COMPATIBLE_WITH_ASSIGNED), verdict.reason)
                checked = finalize_utterance(generate, StanceAssignment(turn["side"], opposing), phase=turn["phase"], semantic_check=semantic_check)
                if not checked.committed:
                    append_jsonl(path, {"turn": turn, "safe_failure": True, "stance_label": checked.assessment.label, "attempts": checked.attempts, "raw_utterance": checked.raw_utterance, "stance_checks": checked.checks})
                    raise RuntimeError("Assigned Stance violation after one regeneration")
                speech, speech_meta = checked.utterance, next((item for item in reversed(metadata) if "finish_reason" in item), metadata[-1])
            except Exception as exc:
                append_jsonl(path, {"turn": turn, "error": str(exc)})
                raise RuntimeError(f"{label} turn {turn['turn']} 실패: {exc}") from exc
            item = {**turn, "speech": speech, "speech_meta": speech_meta}
            append_jsonl(path, item)
            transcript.append(item)
            print(f"{label}: {turn['turn']}/{len(build_schedule(scenario, crossfire_pairs, swap))} {turn['phase']} {turn['speaker']}", flush=True)
    (output / "review.md").write_text(
        "# 사람 검토\n\n발언 원문을 대조해 Persona·입장·상대 반응을 판정하세요. 빈칸은 미평가입니다.\n\n"
        "| 실행 | Turn | Persona 행동 | 입장 유지 | 직전 발언 반응 | 반복/근거 없는 사실 | 근거 |\n"
        "|---|---:|---|---|---|---|---|\n"
        + "".join(f"| {label} | {turn['turn']} |  |  |  |  |  |\n" for label in (["normal", "swapped"] if crossover else ["normal"]) for turn in build_schedule(scenario, crossfire_pairs, label == "swapped")),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Debate Harness prototype measurement runner")
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--crossfire-pairs", type=int, default=2)
    parser.add_argument("--crossover", action="store_true", help="같은 Persona의 입장을 바꿔 한 번 더 실행")
    parser.add_argument("--model", required=True, help="한 실행에서 A/B가 함께 사용할 모델")
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args(argv)
    try:
        scenario = load_scenario(args.scenario)
        providers = select_debaters(load_config(args.env), args.model)
        output = args.output or Path("etc/runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
        run(scenario, providers, output, args.crossfire_pairs, args.crossover, args.timeout)
        print(f"결과: {output}")
        return 0
    except (ConfigError, ValueError, RuntimeError, OSError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
