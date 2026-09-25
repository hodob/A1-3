const assert = require('assert');
const path = require('path');
const moderator = require(path.resolve(__dirname, '../../public/debate_moderator.js'));

function session(transcript = [], overrides = {}) {
  return {transcript, audience_question: null, ...overrides};
}

{
  const before = session([{turn: 1, phase: 'OPENING'}, {turn: 2, phase: 'OPENING'}]);
  const after = session([...before.transcript, {turn: 3, phase: 'CROSSFIRE'}]);
  assert(moderator.eventsForStep(before, {session: after, phase: 'CROSSFIRE', turn_task: 'TEST_UNRESOLVED_REASON', moderator_decision: 'CONTINUE'}).some(e => e.kind === 'PHASE_HANDOFF'));
}
{
  const before = session([{turn: 3, phase: 'CROSSFIRE'}]);
  const after = session([...before.transcript, {turn: 4, phase: 'CROSSFIRE'}]);
  assert(moderator.eventsForStep(before, {session: after, phase: 'CROSSFIRE', turn_task: 'WEIGH_COMPETING_REASONS', moderator_decision: 'CONTINUE'}).some(e => e.kind === 'REFOCUS'));
}
{
  const before = session([{turn: 8, phase: 'CROSSFIRE'}]);
  const after = session(before.transcript, {audience_question: '볶는다는 것도 있어'});
  const events = moderator.eventsForStep(before, {session: after, phase: 'CROSSFIRE'}, {command: 'AUDIENCE_QUESTION', audienceQuestion: '볶는다는 것도 있어'});
  assert(events.find(e => e.kind === 'AUDIENCE_HANDOFF').body.includes('볶는다는 것도 있어'));
}
console.log('debate_moderator tests passed');
