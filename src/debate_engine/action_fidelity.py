"""Cheap deterministic checks; semantic provider verdict remains authoritative at runtime."""

from dataclasses import dataclass
from enum import StrEnum
import re

from .action_execution_contracts import CONTRACTS


class ActionFidelityLabel(StrEnum):
    ALIGNED = "ALIGNED"
    PARTIALLY_ALIGNED = "PARTIALLY_ALIGNED"
    MISALIGNED = "MISALIGNED"
    UNCLEAR = "UNCLEAR"


@dataclass(frozen=True)
class ActionFidelityAssessment:
    label: ActionFidelityLabel
    reason: str


def check_action_fidelity(action: str, target_text: str | None, utterance: str) -> ActionFidelityAssessment:
    if action not in CONTRACTS or not utterance.strip():
        return ActionFidelityAssessment(ActionFidelityLabel.UNCLEAR, "missing contract or utterance")
    text = utterance.replace("\n", " ")
    if action == "REQUEST_SUPPORT":
        ok = bool(re.search(r"근거|이유|정당화|자료|왜", text)) and (not target_text or any(token in text for token in target_text.split() if len(token) >= 3))
        return ActionFidelityAssessment(ActionFidelityLabel.ALIGNED if ok else ActionFidelityLabel.MISALIGNED, "support requested" if ok else "no support request for target")
    if action == "CHALLENGE_PREMISE":
        if re.search(r"맞(?:습니다|고)|동의|좋은 근거", text) and not re.search(r"전제|자명|항상|보장|의심|같진 않|아니|왜", text):
            return ActionFidelityAssessment(ActionFidelityLabel.MISALIGNED, "target is supported rather than challenged")
        # Known failure shape: target is explicitly defended, while a different premise is challenged.
        if target_text and "이유가" in text and "때문" in text and "전제" in text and "동의하기 어렵" in text:
            return ActionFidelityAssessment(ActionFidelityLabel.MISALIGNED, "different premise challenged while target is defended")
        ok = bool(re.search(r"전제|자명|항상|보장|가정|의심|같진 않|성립|왜", text))
        return ActionFidelityAssessment(ActionFidelityLabel.ALIGNED if ok else ActionFidelityLabel.UNCLEAR, "premise challenged" if ok else "challenge effect unclear")
    if action == "CONCEDE_LOCAL":
        denied = bool(re.search(r"동의하지 않|인정하지 않|맞지 않", text))
        accepted = bool(re.search(r"인정|맞습니다|동의|수용", text))
        return ActionFidelityAssessment(ActionFidelityLabel.ALIGNED if accepted and not denied else ActionFidelityLabel.MISALIGNED, "local proposition accepted" if accepted and not denied else "no actual concession")
    if action == "WEIGH_COMPARATIVE":
        compares = bool(re.search(r"하지만|반면|보다|A.+B|B.+A", text)) and bool(re.search(r"비용|효과|범위|확률|지속|장기|단기|기준", text))
        return ActionFidelityAssessment(ActionFidelityLabel.ALIGNED if compares else ActionFidelityLabel.MISALIGNED, "competing considerations compared" if compares else "one-sided assertion without comparison")
    if action == "CRYSTALLIZE":
        if re.search(r"새로운 근거|새 근거|연구 결과|추가 사례", text):
            return ActionFidelityAssessment(ActionFidelityLabel.MISALIGNED, "new substantive argument introduced")
        ok = bool(re.search(r"핵심|지금까지|결론|정리|가장 중요한", text))
        return ActionFidelityAssessment(ActionFidelityLabel.ALIGNED if ok else ActionFidelityLabel.UNCLEAR, "existing clash compressed" if ok else "crystallization unclear")
    return ActionFidelityAssessment(ActionFidelityLabel.UNCLEAR, "requires semantic validation")
