"""Derived debate control-plane state.

Raw DebateState remains authoritative. This module derives semantic facets,
QUD/question groups, progress, and the next conversational obligation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .debate_contracts import DebateState


class ProgressType(str, Enum):
    NEW_REASON = "NEW_REASON"
    NEW_COUNTEREXAMPLE = "NEW_COUNTEREXAMPLE"
    QUALIFICATION = "QUALIFICATION"
    RELATED_DISTINCT = "RELATED_DISTINCT"
    QUESTION_RESOLVED = "QUESTION_RESOLVED"
    CONCESSION = "CONCESSION"
    REVISION = "REVISION"
    REPHRASE = "REPHRASE"
    REPEAT_QUESTION = "REPEAT_QUESTION"
    REOPEN_RESOLVED = "REOPEN_RESOLVED"


MEANINGFUL_PROGRESS = {
    ProgressType.NEW_REASON,
    ProgressType.NEW_COUNTEREXAMPLE,
    ProgressType.QUALIFICATION,
    ProgressType.RELATED_DISTINCT,
    ProgressType.QUESTION_RESOLVED,
    ProgressType.CONCESSION,
    ProgressType.REVISION,
}


class TurnTaskKind(str, Enum):
    INTRODUCE_UNCOVERED_FACET = "INTRODUCE_UNCOVERED_FACET"
    ANSWER_OPEN_QUESTION = "ANSWER_OPEN_QUESTION"
    ADDRESS_AUDIENCE = "ADDRESS_AUDIENCE"
    ADDRESS_COUNTEREXAMPLE = "ADDRESS_COUNTEREXAMPLE"
    TEST_UNRESOLVED_REASON = "TEST_UNRESOLVED_REASON"
    WEIGH_COMPETING_REASONS = "WEIGH_COMPETING_REASONS"
    NARROW_DISAGREEMENT = "NARROW_DISAGREEMENT"
    CRYSTALLIZE = "CRYSTALLIZE"
    NO_VALUABLE_MOVE = "NO_VALUABLE_MOVE"


@dataclass(frozen=True)
class ArgumentFacet:
    id: str
    representative_id: str
    current_id: str
    member_ids: tuple[str, ...]
    speaker: str
    semantic_role: str
    last_turn: int


@dataclass(frozen=True)
class QuestionGroup:
    id: str
    representative_question_id: str
    current_question_id: str
    member_ids: tuple[str, ...]
    status: str
    asker: str
    target_proposition_id: str | None
    core_proposition: str
    last_turn: int
    repeated_count: int = 0


@dataclass(frozen=True)
class DebateControlView:
    facets: tuple[ArgumentFacet, ...]
    proposition_to_facet: dict[str, str]
    question_groups: tuple[QuestionGroup, ...]
    question_to_group: dict[str, str]
    progress_by_turn: dict[int, frozenset[ProgressType]]
    agreed_facet_ids: frozenset[str]

    def meaningful_progress(self, turn: int) -> bool:
        return bool(self.progress_by_turn.get(turn, frozenset()) & MEANINGFUL_PROGRESS)

    @property
    def latest_turn(self) -> int:
        return max(self.progress_by_turn, default=0)


@dataclass(frozen=True)
class TurnTask:
    kind: TurnTaskKind
    target_ids: tuple[str, ...]
    description: str
    issue_id: str = "ISSUE_MAIN"


def _control_records(state: DebateState) -> tuple[list[dict], list[dict]]:
    propositions: list[dict] = []
    questions: list[dict] = []
    for event in state.event_log:
        control = event.get("control") or {}
        turn = int(event.get("turn", 0))
        for item in control.get("propositions", []):
            propositions.append({**item, "turn": turn})
        for item in control.get("questions", []):
            questions.append({**item, "turn": turn})
    return propositions, questions


def build_control_view(state: DebateState) -> DebateControlView:
    prop_records, question_records = _control_records(state)
    props_by_id = {p.id: p for p in state.propositions}
    prop_record_by_id = {x["proposition_id"]: x for x in prop_records if x.get("proposition_id")}

    facet_members: dict[str, list[str]] = {}
    facet_meta: dict[str, tuple[str, str, int]] = {}
    facet_current: dict[str, str] = {}
    proposition_to_facet: dict[str, str] = {}

    for proposition in sorted(state.propositions, key=lambda p: (p.turn, int(p.id[1:]))):
        record = prop_record_by_id.get(proposition.id, {})
        kind = record.get("semantic_kind", "NEW_REASON")
        anchor = record.get("semantic_anchor_id")
        if kind in ("SAME_POINT", "REFINEMENT", "QUALIFICATION") and anchor in proposition_to_facet:
            facet_id = proposition_to_facet[anchor]
        else:
            facet_id = f"F-{proposition.id}"
        proposition_to_facet[proposition.id] = facet_id
        facet_members.setdefault(facet_id, []).append(proposition.id)
        representative = facet_members[facet_id][0]
        if facet_id not in facet_current or kind in ("REFINEMENT", "QUALIFICATION"):
            facet_current[facet_id] = proposition.id
        first = props_by_id[representative]
        old_role = facet_meta.get(facet_id, (first.speaker, kind, proposition.turn))[1]
        role = old_role if kind in ("SAME_POINT", "REFINEMENT") else kind
        facet_meta[facet_id] = (first.speaker, role, proposition.turn)

    facets = tuple(
        ArgumentFacet(fid, members[0], facet_current[fid], tuple(members), facet_meta[fid][0], facet_meta[fid][1], facet_meta[fid][2])
        for fid, members in facet_members.items()
    )

    question_to_group: dict[str, str] = {}
    group_members: dict[str, list[str]] = {}
    repeated: dict[str, int] = {}
    question_by_id = {q.id: q for q in state.questions}
    record_by_qid = {x["question_id"]: x for x in question_records if x.get("question_id")}

    def same_turn_target_group(question) -> str | None:
        if not question.target_proposition_id:
            return None
        facet_id = proposition_to_facet.get(question.target_proposition_id)
        for prior in reversed(state.questions):
            if prior.id == question.id:
                continue
            if prior.asker != question.asker or prior.source_turn_id != question.source_turn_id:
                continue
            if not prior.target_proposition_id:
                continue
            if proposition_to_facet.get(prior.target_proposition_id) == facet_id:
                return question_to_group.get(prior.id)
        return None

    for question in sorted(state.questions, key=lambda q: (q.turn, int(q.id[1:]))):
        record = record_by_qid.get(question.id, {})
        anchor = record.get("anchor_question_id")
        group_id = question_to_group.get(anchor) if anchor else None
        if group_id is None:
            group_id = same_turn_target_group(question)
        if group_id is None:
            group_id = f"QG-{question.id}"
        question_to_group[question.id] = group_id
        group_members.setdefault(group_id, []).append(question.id)

    for record in question_records:
        if record.get("semantic_kind") == "SAME_QUESTION" and record.get("anchor_question_id"):
            anchor = record["anchor_question_id"]
            group_id = question_to_group.get(anchor, f"QG-{anchor}")
            repeated[group_id] = repeated.get(group_id, 0) + 1

    question_groups: list[QuestionGroup] = []
    for group_id, members in group_members.items():
        representative = question_by_id[members[0]]
        current = question_by_id[members[-1]]
        # A direct/qualified resolution to one formulation resolves the Immediate QUD
        # represented by this MIU group, even if another surface question node remains OPEN.
        status = "RESOLVED" if any(question_by_id[qid].resolution == "RESOLVED" for qid in members) else "OPEN"
        question_groups.append(QuestionGroup(
            group_id,
            representative.id,
            current.id,
            tuple(members),
            status,
            current.asker,
            current.target_proposition_id,
            current.core_proposition,
            max(question_by_id[qid].source_turn_id for qid in members),
            repeated.get(group_id, 0),
        ))

    progress: dict[int, set[ProgressType]] = {}
    for record in prop_records:
        turn = int(record.get("turn", 0))
        kind = record.get("semantic_kind", "NEW_REASON")
        mapped = {
            "NEW_REASON": ProgressType.NEW_REASON,
            "NEW_COUNTEREXAMPLE": ProgressType.NEW_COUNTEREXAMPLE,
            "QUALIFICATION": ProgressType.QUALIFICATION,
            "RELATED_DISTINCT": ProgressType.RELATED_DISTINCT,
            "SAME_POINT": ProgressType.REPHRASE,
            "REFINEMENT": ProgressType.REPHRASE,
        }.get(kind)
        if mapped:
            progress.setdefault(turn, set()).add(mapped)
    for record in question_records:
        if record.get("semantic_kind") == "SAME_QUESTION":
            event = ProgressType.REOPEN_RESOLVED if record.get("anchor_resolution") == "RESOLVED" else ProgressType.REPEAT_QUESTION
            progress.setdefault(int(record.get("turn", 0)), set()).add(event)
    for event in state.question_response_events:
        if event.get("resolution") == "RESOLVED":
            progress.setdefault(int(event["turn"]), set()).add(ProgressType.QUESTION_RESOLVED)
    for event in state.commitment_events:
        if event.event == "CONCEDE":
            progress.setdefault(event.turn, set()).add(ProgressType.CONCESSION)
        elif event.event == "REVISE":
            progress.setdefault(event.turn, set()).add(ProgressType.REVISION)

    for proposition in state.propositions:
        progress.setdefault(proposition.turn, set())
        if proposition.id not in prop_record_by_id:
            progress[proposition.turn].add(ProgressType.NEW_REASON)

    agreed_facets = frozenset(
        proposition_to_facet[event.proposition_id]
        for event in state.commitment_events
        if event.event == "CONCEDE" and event.proposition_id in proposition_to_facet
    )

    return DebateControlView(
        facets=facets,
        proposition_to_facet=proposition_to_facet,
        question_groups=tuple(question_groups),
        question_to_group=question_to_group,
        progress_by_turn={turn: frozenset(events) for turn, events in progress.items()},
        agreed_facet_ids=agreed_facets,
    )


def immediate_qud(view: DebateControlView, state: DebateState, speaker: str) -> QuestionGroup | None:
    """Return only the top/current opponent QUD.

    We intentionally do not resurrect an older unrelated open question after a newer
    QUD has been resolved. Questions from one turn against the same target facet are
    treated as one MIU group.
    """
    groups = [g for g in view.question_groups if g.asker != speaker]
    if not groups:
        return None
    newest_turn = max(g.last_turn for g in groups)
    newest = [g for g in groups if g.last_turn == newest_turn]
    top = max(newest, key=lambda g: int(g.current_question_id[1:]))
    return top if top.status == "OPEN" else None


def _recent_counterexample(state: DebateState, speaker: str) -> str | None:
    prop_records, _ = _control_records(state)
    for record in reversed(prop_records):
        pid = record.get("proposition_id")
        proposition = next((p for p in state.propositions if p.id == pid), None)
        if proposition and proposition.speaker != speaker and record.get("semantic_kind") == "NEW_COUNTEREXAMPLE":
            if not any(p.speaker == speaker and p.turn > proposition.turn for p in state.propositions):
                return proposition.id
    return None


def _latest_facet_target(view: DebateControlView, state: DebateState, speaker: str, *, opponent: bool) -> str | None:
    candidates = [f for f in view.facets if (f.speaker != speaker) == opponent and f.id not in view.agreed_facet_ids]
    if not candidates:
        return None
    latest = max(candidates, key=lambda f: f.last_turn)
    return latest.current_id


def _recent_stagnation(view: DebateControlView) -> bool:
    turns = sorted(view.progress_by_turn)
    if len(turns) < 4:
        return False
    return all(not view.meaningful_progress(turn) for turn in turns[-2:])


def _question_pressure_on_facet(view: DebateControlView, state: DebateState, speaker: str, facet_id: str) -> int:
    count = 0
    for group in view.question_groups:
        if group.asker != speaker or not group.target_proposition_id:
            continue
        if view.proposition_to_facet.get(group.target_proposition_id) == facet_id:
            count += 1
    return count


def plan_turn_task(
    state: DebateState,
    *,
    speaker: str,
    phase: str,
    audience_question: str | None = None,
) -> TurnTask:
    """Choose the conversational obligation before choosing a strategic action."""
    phase = phase.lower()
    if phase == "audience_response" and audience_question:
        return TurnTask(TurnTaskKind.ADDRESS_AUDIENCE, (), f"관객 입력에 직접 답하세요: {audience_question}", "ISSUE_AUDIENCE")
    if phase == "final_focus":
        return TurnTask(TurnTaskKind.CRYSTALLIZE, (), "이미 다룬 핵심 쟁점과 이유만 압축하세요.")
    if phase == "opening":
        return TurnTask(TurnTaskKind.INTRODUCE_UNCOVERED_FACET, (), "입장을 지지하는 핵심 이유 1~2개를 처음 제시하세요.")

    view = build_control_view(state)
    qud = immediate_qud(view, state, speaker)
    if qud is not None:
        return TurnTask(
            TurnTaskKind.ANSWER_OPEN_QUESTION,
            (qud.current_question_id,),
            f"현재 핵심 질문에 먼저 직접 답하세요: {qud.core_proposition}",
            qud.id,
        )

    counterexample = _recent_counterexample(state, speaker)
    if counterexample:
        return TurnTask(TurnTaskKind.ADDRESS_COUNTEREXAMPLE, (counterexample,), "상대가 새로 제시한 반례를 수용·한정·반박 중 하나로 처리하세요.")

    opponent_target = _latest_facet_target(view, state, speaker, opponent=True)
    own_target = _latest_facet_target(view, state, speaker, opponent=False)

    if _recent_stagnation(view):
        if opponent_target and own_target:
            return TurnTask(TurnTaskKind.WEIGH_COMPETING_REASONS, (opponent_target, own_target), "이미 나온 양측 핵심 이유를 같은 기준에서 직접 비교해 우선순위를 설명하세요.")
        return TurnTask(TurnTaskKind.NO_VALUABLE_MOVE, (), "현재 issue에서 새롭게 해결할 고가치 과제가 없습니다.")

    if phase == "rebuttal" and opponent_target and own_target:
        return TurnTask(TurnTaskKind.WEIGH_COMPETING_REASONS, (opponent_target, own_target), "Rebuttal에서 양측 핵심 이유를 비교하고 남은 충돌을 좁히세요.")
    if opponent_target:
        facet_id = view.proposition_to_facet.get(opponent_target)
        if facet_id and own_target and _question_pressure_on_facet(view, state, speaker, facet_id) >= 2:
            return TurnTask(
                TurnTaskKind.WEIGH_COMPETING_REASONS,
                (opponent_target, own_target),
                "같은 상대 쟁점을 이미 두 차례 QUD로 검토했습니다. 새 질문을 반복하지 말고 양측 이유를 같은 기준에서 비교하세요.",
                facet_id,
            )
        return TurnTask(TurnTaskKind.TEST_UNRESOLVED_REASON, (opponent_target,), "아직 해결되지 않은 상대 핵심 이유 하나를 검증하거나 범위를 좁히세요.")
    return TurnTask(TurnTaskKind.NO_VALUABLE_MOVE, (), "현재 issue에서 검증할 상대 핵심 이유가 없습니다.")
