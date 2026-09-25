(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.SaiModerator = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function latestTurn(session) {
    const transcript = Array.isArray(session?.transcript) ? session.transcript : [];
    const turn = transcript.length ? Number(transcript[transcript.length - 1]?.turn) : 0;
    return Number.isFinite(turn) && turn > 0 ? turn : transcript.length;
  }

  function latestPhase(session) {
    const transcript = Array.isArray(session?.transcript) ? session.transcript : [];
    return transcript.length ? transcript[transcript.length - 1]?.phase || null : null;
  }

  function event(kind, afterTurn, title, body, key = kind) {
    return {kind, afterTurn, title, body, key};
  }

  function eventsForStep(previousSession, data, context = {}) {
    const events = [];
    const beforeTurn = latestTurn(previousSession);
    const previousPhase = latestPhase(previousSession);
    const currentPhase = data?.phase || latestPhase(data?.session);
    const decision = data?.moderator_decision || null;
    const task = data?.turn_task || null;

    const audienceHandoff = decision === 'AUDIENCE_QUD_OPENED' || context.command === 'AUDIENCE_QUESTION';
    if (audienceHandoff) {
      const question = String(context.audienceQuestion || data?.session?.audience_question || '').trim();
      events.push(event(
        'AUDIENCE_HANDOFF', beforeTurn, '관객 질문을 두 입장에 전달합니다.',
        question ? `“${question}” 같은 질문에 A와 B가 차례로 직접 답합니다.` : '같은 관객 질문에 A와 B가 차례로 직접 답합니다.',
        'audience-handoff'
      ));
      return events;
    }

    if (decision === 'MOVE_PHASE') {
      events.push(event('MOVE_PHASE', beforeTurn, '이 쟁점은 여기까지 좁혀졌습니다.', '새로 풀 고가치 과제가 줄어 같은 공방을 반복하지 않고 다음 단계로 넘어갑니다.', `move-phase-${beforeTurn}`));
    }
    if (previousPhase === 'OPENING' && currentPhase === 'CROSSFIRE') {
      events.push(event('PHASE_HANDOFF', beforeTurn, '이제 서로의 기준을 직접 검토합니다.', '첫 입장에서 나온 이유를 바탕으로, 새 주장만 늘리기보다 상대의 핵심 이유를 확인하고 좁혀갑니다.', 'opening-to-crossfire'));
    }
    if (task === 'WEIGH_COMPETING_REASONS') {
      events.push(event('REFOCUS', beforeTurn, '같은 쟁점을 반복하지 않고 비교합니다.', '이미 나온 양측 핵심 이유를 같은 기준에서 직접 비교해 무엇이 더 중요한지 좁혀갑니다.', 'weigh-refocus'));
    }
    if (previousPhase !== 'FINAL_FOCUS' && currentPhase === 'FINAL_FOCUS') {
      events.push(event('FINAL_BRIEF', beforeTurn, '이제 가장 중요한 이유만 남깁니다.', '새 근거를 보태지 않고, 지금까지 남은 핵심 이유를 각 입장이 짧게 압축합니다.', 'final-brief'));
    }
    return events;
  }

  return {eventsForStep};
});
