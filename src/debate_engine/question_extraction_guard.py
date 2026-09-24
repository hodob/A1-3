"""Deterministic sanity check for explicit Korean questions.

This is intentionally a recall guard. The LLM still creates the semantic
Question entity; this module only detects a clear omission before State commit.
"""

from __future__ import annotations

import re


_QUOTED = re.compile(r'"[^"\n]*"|“[^”\n]*”|\'[^\'\n]*\'|‘[^’\n]*’')
_QUESTION_ENDING = re.compile(
    r"(?:인가요|아닌가요|건가요|뭔가요|가요|입니까|합니까|됩니까|습니까|나요|하나요|보십니까|그렇죠|무엇인가요|인정하나요|설명할 수 있나요|할 수 있습니까)\s*[?.!]?$"
)
_QUESTION_WORD = re.compile(r"(?:왜|무엇|어떤|어떻게|누가|언제|어디|근거|이유|차이)")
_CLAUSE_START = re.compile(r"(?:그\s+(?:차이|근거|이유)|왜|무엇|어떤|어떻게|누가|언제|어디서|근거는|이유는)")


def explicit_question_candidates(text: str) -> list[str]:
    """Return unquoted clauses with an explicit interrogative form."""
    unquoted = _QUOTED.sub("", text)
    candidates: list[str] = []
    for segment in re.split(r"(?<=[.!?;])\s+|\n+", unquoted):
        segment = segment.strip()
        if not segment or not _QUESTION_ENDING.search(segment):
            continue
        # Avoid treating a declarative Korean honorific ending as a question
        # unless it has a question mark or an interrogative word.
        if "?" not in segment and not _QUESTION_WORD.search(segment):
            continue
        preferred = re.search(r"그\s+(?:차이|근거|이유)", segment)
        starts = list(_CLAUSE_START.finditer(segment))
        if preferred:
            segment = segment[preferred.start():].strip()
        elif starts:
            segment = segment[starts[-1].start():].strip()
        candidates.append(segment)
    return candidates
