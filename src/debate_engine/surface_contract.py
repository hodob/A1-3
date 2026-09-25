"""Deterministic validation for user-visible debate utterances.

Semantic debate quality belongs to the LLM compliance judge. Surface invariants that
can be checked exactly stay local so retries are cheaper and easier to diagnose.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .debate_contracts import DebateState

REFERENCE_RE = re.compile(r"\[\[([CQ]\d+)\]\]")
RAW_STATE_ID_RE = re.compile(r"(?<!\[\[)(?<![A-Z0-9_])([CQ]\d+)(?!\]\])(?!\d)")
HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")
FENCE_RE = re.compile(r"(?m)^\s*(`{3,}|~{3,})")
HTML_RE = re.compile(r"<\/?[A-Za-z][^>]*>")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]\n]+\]\([^\)\n]+\)")
TABLE_SEPARATOR_RE = re.compile(r"(?m)^\s*\|?\s*:?-{3,}[^\n]*\|[^\n]*$")
LIST_RE = re.compile(r"(?m)^\s*(?:[-*+] |\d+[.)] )")
QUOTE_RE = re.compile(r"(?m)^\s*>\s?")
SENTENCE_END_RE = re.compile(r"[.!?](?:[\"'”’)]*)\s*(?=\S|$)")


@dataclass(frozen=True)
class SurfaceIssue:
    code: str
    message: str
    reference: str | None = None

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "reference": self.reference}


def known_reference_ids(state: DebateState) -> frozenset[str]:
    return frozenset([*(p.id for p in state.propositions), *(q.id for q in state.questions)])


def validate_surface(utterance: str, *, phase: str, allowed_reference_ids: set[str] | frozenset[str]) -> list[SurfaceIssue]:
    text = utterance or ""
    issues: list[SurfaceIssue] = []
    markers = REFERENCE_RE.findall(text)

    for ref_id in markers:
        if ref_id not in allowed_reference_ids:
            issues.append(SurfaceIssue("UNKNOWN_STATE_REFERENCE", f"존재하지 않는 State reference [[{ref_id}]]를 사용했습니다.", ref_id))

    without_markers = REFERENCE_RE.sub("", text)
    raw_ids = []
    for match in RAW_STATE_ID_RE.finditer(without_markers):
        ref_id = match.group(1)
        if ref_id not in raw_ids:
            raw_ids.append(ref_id)
    for ref_id in raw_ids:
        issues.append(SurfaceIssue("RAW_STATE_ID_LEAK", f"State ID {ref_id}는 [[{ref_id}]] 형식으로만 출력해야 합니다.", ref_id))

    disallowed = []
    if HEADING_RE.search(text):
        disallowed.append("heading")
    if FENCE_RE.search(text):
        disallowed.append("code_fence")
    if HTML_RE.search(text):
        disallowed.append("html")
    if MARKDOWN_LINK_RE.search(text):
        disallowed.append("link")
    if TABLE_SEPARATOR_RE.search(text):
        disallowed.append("table")
    if disallowed:
        issues.append(SurfaceIssue("MARKDOWN_DISALLOWED_ELEMENT", "허용되지 않은 Markdown 요소가 있습니다: " + ", ".join(disallowed)))

    if phase.lower() == "final_focus":
        if LIST_RE.search(text) or QUOTE_RE.search(text):
            issues.append(SurfaceIssue("FINAL_FOCUS_FORMAT", "Final Focus는 목록이나 인용문 없이 한 문단으로 작성해야 합니다."))
        sentence_count = len(SENTENCE_END_RE.findall(text.strip()))
        if sentence_count > 2:
            issues.append(SurfaceIssue("FINAL_FOCUS_LENGTH", "Final Focus는 최대 2문장이어야 합니다."))
        if "?" in text:
            issues.append(SurfaceIssue("FINAL_FOCUS_QUESTION", "Final Focus에서는 상대에게 질문하지 않습니다."))

    return issues


def extract_state_references(utterance: str, state: DebateState) -> list[dict]:
    propositions = {p.id: p for p in state.propositions}
    questions = {q.id: q for q in state.questions}
    result: list[dict] = []
    seen: set[str] = set()
    for ref_id in REFERENCE_RE.findall(utterance or ""):
        if ref_id in seen:
            continue
        seen.add(ref_id)
        if ref_id in propositions:
            item = propositions[ref_id]
            result.append({
                "id": ref_id,
                "kind": "CLAIM",
                "speaker": item.speaker,
                "turn": item.turn,
                "excerpt": item.text,
            })
        elif ref_id in questions:
            item = questions[ref_id]
            result.append({
                "id": ref_id,
                "kind": "QUESTION",
                "speaker": item.asker,
                "turn": item.source_turn_id,
                "excerpt": item.core_proposition,
            })
    return result
