const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const HOME_VIEWS = ['topic-view', 'context-view', 'context-review-view', 'motion-view'];
const DEBATE_VIEWS = ['debate-empty', 'debate-arena', 'summary-view', 'choice-view', 'done-view'];
const ROUTES = ['home', 'debate', 'how-it-works'];

const PHASES = [
  {id: 'OPENING', name: '첫 입장', title: '먼저 각자의 생각을 들어보세요.', description: '두 입장이 어디서 출발하는지 살펴보세요.'},
  {id: 'CROSSFIRE', name: '주고받기', title: '상대의 말을 어떻게 받아칠까요?', description: '앞선 말을 되짚으며 두 입장을 따라가 보세요.'},
  {id: 'AUDIENCE_RESPONSE', name: '함께 답하기', title: '같은 질문, 두 가지 답변.', description: '같은 질문에 각 입장이 어떻게 답하는지 비교해 보세요.'},
  {id: 'REBUTTAL', name: '쟁점 되짚기', title: '부딪혔던 쟁점을 다시 짚어요.', description: '서로의 반박 뒤에도 남은 이유를 살펴보세요.'},
  {id: 'FINAL_FOCUS', name: '마지막 한마디', title: '끝으로 남길 가장 중요한 이유.', description: '마지막으로 남길 이유를 들어보세요.'},
  {id: 'COMPLETE', name: '토론 정리', title: '이제 토론을 되짚어볼까요?', description: '판단할 재료를 정리할 차례예요.'},
];

const PERSONA_DESCRIPTIONS = {
  Auditor: '근거와 결론의 연결을 확인해요.',
  Socratic: '말의 뜻과 숨은 전제를 확인해요.',
  Falsifier: '반례와 예외를 찾아요.',
  Pragmatist: '결과와 현실적인 선택을 비교해요.',
  Principlist: '원칙과 기준의 일관성을 살펴요.',
  Synthesist: '양쪽의 타당한 부분과 조정점을 찾아요.',
};

const PERSONA_LABELS = {
  Auditor: '근거 검증형',
  Socratic: '전제 탐구형',
  Falsifier: '반례 탐색형',
  Pragmatist: '현실 실용형',
  Principlist: '원칙 중심형',
  Synthesist: '조정 통합형',
};

async function loadBuildVersion() {
  try {
    const response = await fetch('/api/health', {cache: 'no-store'});
    if (!response.ok) return;
    const payload = await response.json();
    const version = payload?.data?.version;
    if (typeof version !== 'string' || !/^[0-9a-f]{7}$/.test(version)) return;
    const node = $('#build-version');
    node.textContent = `버전 ${version}`;
    node.hidden = false;
  } catch (_) {
    // Version is diagnostic only; the app remains usable without it.
  }
}

const state = {
  route: 'home',
  view: 'topic-view',
  pendingOperation: null,
  analysis: null,
  confirmedContextAnswers: [],
  contextQuestion: null,
  contextSummary: null,
  motion: null,
  session: null,
  summary: null,
  choice: null,
  lastRetry: null,
  operationSequence: 0,
  activeController: null,
  operationTimers: [],
  debugLog: [],
  moderatorEvents: [],
};

class AppError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function element(tag, className = '', text = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== '') node.textContent = text;
  return node;
}

function replaceChildren(node, children) {
  node.replaceChildren(...children.filter(Boolean));
}

function codePointLength(value) {
  return Array.from(String(value || '')).length;
}

function setStatus(message = '') {
  $('#app-status').textContent = message;
}

function clearError() {
  $('#app-error').hidden = true;
}

function friendlyError(operation, error) {
  if (error.code === 'SAFE_FAILURE') {
    return ['다음 발언을 이어가지 못했어요.', '여기까지의 토론은 그대로예요. 이 발언을 다시 준비할 수 있어요.'];
  }
  if (error.code === 'CONFIG_ERROR') {
    return ['지금은 토론을 준비할 수 없어요.', '입력은 그대로예요. 잠시 후 다시 시도해 주세요.'];
  }
  if (error.code === 'TIMEOUT' || error.code === 'STOPPED') {
    return ['응답을 기다리는 시간이 길어져 멈췄어요.', '입력과 여기까지의 토론은 그대로예요. 다시 시도할 수 있어요.'];
  }
  if (operation === 'summary') {
    return ['토론 정리를 불러오지 못했어요.', '토론 내용은 그대로 읽을 수 있어요. 정리만 다시 불러올 수 있어요.'];
  }
  if (operation === 'debate') {
    return ['다음 발언을 불러오지 못했어요.', '여기까지의 토론은 그대로예요.'];
  }
  return ['준비를 마치지 못했어요.', '입력한 내용은 그대로 있어요. 다시 시도해 주세요.'];
}

function showError(operation, error) {
  const [title, message] = friendlyError(operation, error);
  const sameTurnRetry = operation === 'debate' && error.code === 'SAFE_FAILURE';
  $('#error-title').textContent = title;
  $('#error-message').textContent = message;
  $('#retry-action').textContent = sameTurnRetry ? '이 발언 다시 준비하기' : '다시 시도하기';
  $('#retry-action').hidden = !state.lastRetry;
  if (sameTurnRetry && state.view === 'debate-arena') $('#next-turn').textContent = '이 발언 다시 준비하기 →';
  $('#app-error').hidden = false;
}

function setFieldError(input, errorNode, message) {
  input.setAttribute('aria-invalid', message ? 'true' : 'false');
  errorNode.textContent = message || '';
  errorNode.hidden = !message;
}

function showRoute(route, {focus = false} = {}) {
  const validRoute = ROUTES.includes(route) ? route : 'home';
  state.route = validRoute;
  $$('[data-route]').forEach(node => { node.hidden = node.dataset.route !== validRoute; });
  $$('[data-route-link]').forEach(link => {
    if (link.dataset.routeLink === validRoute) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  if (validRoute === 'debate' && !state.session) showDebateView('debate-empty');
  if (focus) focusActiveHeading();
}

function showHomeView(viewId, focus = true) {
  state.view = viewId;
  HOME_VIEWS.forEach(id => { $(`#${id}`).hidden = id !== viewId; });
  showRoute('home');
  if (focus) focusActiveHeading();
}

function showDebateView(viewId, focus = true) {
  state.view = viewId;
  DEBATE_VIEWS.forEach(id => { $(`#${id}`).hidden = id !== viewId; });
  if (focus) focusActiveHeading();
}

function focusActiveHeading() {
  requestAnimationFrame(() => {
    const activeRoute = $(`[data-route="${state.route}"]`);
    const heading = activeRoute?.querySelector('.view:not([hidden]) h1, :scope > .page-intro h1');
    if (heading) {
      if (!heading.hasAttribute('tabindex')) heading.setAttribute('tabindex', '-1');
      heading.focus({preventScroll: true});
    }
  });
}

function routeFromHash() {
  const route = location.hash.slice(1);
  showRoute(ROUTES.includes(route) ? route : 'home', {focus: true});
}

function clearOperationTimers() {
  state.operationTimers.forEach(clearTimeout);
  state.operationTimers = [];
}

function beginOperation(name, message, retry) {
  if (state.pendingOperation) return null;
  clearError();
  const operationId = `${Date.now()}-${++state.operationSequence}`;
  state.pendingOperation = {id: operationId, name};
  state.lastRetry = retry;
  state.activeController = new AbortController();
  $('#loading-turn').hidden = name !== 'debate';
  $('#loading-message').textContent = message;
  $('#stop-waiting').hidden = true;
  setStatus(message);
  $$('button', $(`[data-route="${state.route}"]`)).forEach(button => { button.disabled = true; });
  state.operationTimers = [
    setTimeout(() => {
      if (state.pendingOperation?.id === operationId) setStatus('평소보다 오래 걸리고 있어요.');
    }, 15000),
    setTimeout(() => {
      if (state.pendingOperation?.id === operationId) {
        setStatus('응답을 기다리고 있어요. 기다리기를 중단한 뒤 다시 시도할 수 있어요.');
        $('#stop-waiting').hidden = false;
        $('#stop-waiting').disabled = false;
      }
    }, 60000),
    setTimeout(() => {
      if (state.pendingOperation?.id === operationId) state.activeController?.abort('timeout');
    }, 180000),
  ];
  return operationId;
}

function endOperation(operationId) {
  if (state.pendingOperation?.id !== operationId) return;
  clearOperationTimers();
  state.pendingOperation = null;
  state.activeController = null;
  $('#loading-turn').hidden = true;
  $('#stop-waiting').hidden = true;
  $$('button').forEach(button => { button.disabled = false; });
  if (state.motion?.edit_count >= 1) $('#motion-edit-details').hidden = true;
  setStatus('');
}

async function api(path, body, operationId) {
  try {
    const response = await fetch(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
      signal: state.activeController?.signal,
    });
    const payload = await response.json().catch(() => ({ok: false, error: {code: 'INVALID_RESPONSE'}}));
    if (state.pendingOperation?.id !== operationId) throw new AppError('STALE_OPERATION', 'stale response');
    if (!response.ok || !payload.ok) throw new AppError(payload.error?.code || 'API_ERROR', payload.error?.message || 'request failed');
    return payload.data;
  } catch (error) {
    if (error?.name === 'AbortError') throw new AppError('TIMEOUT', 'request timed out');
    throw error;
  }
}

async function apiDebateStream(body, operationId, onDraft) {
  try {
    const response = await fetch('/api/debate-step', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Accept': 'text/event-stream'},
      body: JSON.stringify(body),
      signal: state.activeController?.signal,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new AppError(payload?.error?.code || 'API_ERROR', payload?.error?.message || 'request failed');
    }
    if (!response.headers.get('Content-Type')?.includes('text/event-stream')) throw new AppError('INVALID_RESPONSE', '스트림 응답이 아닙니다.');
    const data = await readDebateStream(response, (kind, payload) => {
      if (state.pendingOperation?.id !== operationId) throw new AppError('STALE_OPERATION', 'stale response');
      onDraft(kind, payload);
    });
    if (state.pendingOperation?.id !== operationId) throw new AppError('STALE_OPERATION', 'stale response');
    return data;
  } catch (error) {
    if (error?.name === 'AbortError') throw new AppError('TIMEOUT', 'request timed out');
    throw error;
  }
}

async function performOperation(name, message, retry, task) {
  const operationId = beginOperation(name, message, retry);
  if (!operationId) return null;
  try {
    return await task(operationId);
  } catch (error) {
    if (error.code !== 'STALE_OPERATION') showError(name, error);
    return null;
  } finally {
    endOperation(operationId);
  }
}

function sideCard(side, label, persona) {
  const card = element('div', `person ${side === 'B' ? 'b' : ''}`);
  const identity = element('div', 'identity');
  identity.append(element('span', `side-badge ${side === 'B' ? 'side-b' : 'side-a'}`, side), element('span', '', label));
  card.append(identity, element('p', '', PERSONA_DESCRIPTIONS[persona] || '주제에 맞는 관점으로 살펴요.'));
  return card;
}

function updateCount(input, output, limit) {
  const length = codePointLength(input.value);
  output.textContent = `${length} / ${limit}`;
  return length;
}

async function analyzeTopic(event) {
  event.preventDefault();
  const input = $('#topic-input');
  const error = $('#topic-error');
  const topic = input.value.trim();
  const length = codePointLength(topic);
  if (!topic) return setFieldError(input, error, '토론할 이야기를 한 줄 적어주세요.');
  if (length > 2000) return setFieldError(input, error, '2000자까지 적을 수 있어요. 내용을 줄이면 더 적을 수 있어요.');
  setFieldError(input, error, '');
  const retry = () => analyzeTopic(new Event('submit'));
  const data = await performOperation('prepare', '주제를 살펴보고 있어요.', retry, id => api('/api/analyze-topic', {topic}, id));
  if (!data) return;
  state.analysis = data;
  state.confirmedContextAnswers = [];
  state.contextSummary = null;
  if (data.interaction_state === 'CONTEXT_REQUIRED') {
    await requestContextStep();
    return;
  }
  if (data.interaction_state === 'INFORMATIONAL_FIRST') {
    setFieldError(input, error, '이 질문은 먼저 사실이나 설명을 확인해야 해요. 서로 다른 생각을 비교할 수 있는 주제로 바꿔 적어주세요.');
    return;
  }
  await prepareMotion(null, data.interaction_state === 'CONFIRMATION_REQUIRED' ? data.confirmation_reason : null);
}

function renderContextQuestion(data) {
  const question = data.question;
  state.contextQuestion = question;
  $('#context-progress').textContent = `답변한 질문 ${state.confirmedContextAnswers.length}개`;
  $('#context-question').textContent = question.text;
  const options = [...question.options];
  if (question.allow_unknown && !options.includes('잘 모르겠다')) options.push('잘 모르겠다');
  replaceChildren($('#context-options'), options.map((option, index) => {
    const label = element('label', 'option');
    const input = element('input');
    input.type = 'radio'; input.name = 'context-answer'; input.value = option; input.id = `context-option-${index}`;
    label.append(input, document.createTextNode(option));
    return label;
  }));
  $('#context-free-details').hidden = !question.allow_free_text;
  $('#context-free-input').value = '';
  updateCount($('#context-free-input'), $('#context-free-count'), 1000);
  showHomeView('context-view');
}

function renderContextReview(summary) {
  const groups = [
    ['USER_OBSERVATION', '직접 본 일'],
    ['REPORTED_CLAIM', '전해 들은 이야기'],
    ['USER_ASSUMPTION', '내 해석'],
    ['UNKNOWN', '모르는 부분'],
  ];
  replaceChildren($('#context-review-groups'), groups.map(([key, label]) => {
    const section = element('section', 'context-group');
    section.append(element('h2', '', label));
    const items = summary?.[key] || [];
    if (!items.length) section.append(element('p', 'hint', '해당 내용이 없어요.'));
    else {
      const list = element('ul');
      items.forEach(item => list.append(element('li', '', item)));
      section.append(list);
    }
    return section;
  }));
  showHomeView('context-review-view');
}

async function requestContextStep(candidateAnswer = null) {
  const candidateAnswers = candidateAnswer
    ? [...state.confirmedContextAnswers, candidateAnswer]
    : [...state.confirmedContextAnswers];
  const retry = () => requestContextStep(candidateAnswer);
  const data = await performOperation('prepare', '다음에 확인할 내용을 준비하고 있어요.', retry, id => api('/api/context-step', {
    topic: state.analysis.original_topic,
    answers: candidateAnswers,
  }, id));
  if (!data) return;
  state.confirmedContextAnswers = candidateAnswers;
  if (data.debate_ready) {
    state.contextSummary = data.context_summary;
    renderContextReview(data.context_summary);
  } else {
    renderContextQuestion(data);
  }
}

async function submitContext(event) {
  event.preventDefault();
  const selected = $('input[name="context-answer"]:checked');
  const free = $('#context-free-input').value.trim();
  const answer = free || selected?.value || '';
  const length = codePointLength(answer);
  if (!answer) return setFieldError($('#context-free-input'), $('#context-error'), '답변을 하나 고르거나 직접 적어주세요.');
  if (length > 1000) return setFieldError($('#context-free-input'), $('#context-error'), '답변은 1000자까지 적을 수 있어요.');
  setFieldError($('#context-free-input'), $('#context-error'), '');
  await requestContextStep({question_id: state.contextQuestion.id, answer});
}

async function prepareMotion(contextSummary = state.contextSummary, confirmationReason = null) {
  const retry = () => prepareMotion(contextSummary, confirmationReason);
  const data = await performOperation('prepare', '토론할 문장을 정리하고 있어요.', retry, id => api('/api/create-motion', {
    analysis: state.analysis,
    context_summary: contextSummary,
    edit_count: 0,
  }, id));
  if (!data) return;
  state.contextSummary = contextSummary;
  state.motion = data;
  renderMotion(confirmationReason);
}

function renderMotion(confirmationReason = null) {
  $('#motion-title').textContent = state.motion.motion;
  $('#motion-edit-input').value = state.motion.motion;
  updateCount($('#motion-edit-input'), $('#motion-edit-count'), 1200);
  replaceChildren($('#motion-sides'), [
    sideCard('A', state.motion.side_labels[0], state.motion.personas[0]),
    sideCard('B', state.motion.side_labels[1], state.motion.personas[1]),
  ]);
  $('#confirmation-reason').textContent = confirmationReason ? `토론 전에 확인할 점이 있어요. ${confirmationReason}` : '';
  $('#confirmation-reason').hidden = !confirmationReason;
  const edited = state.motion.edit_count >= 1;
  $('#motion-edit-details').hidden = edited;
  $('#motion-edit-used').hidden = !edited;
  showHomeView('motion-view');
}

async function saveMotionEdit(event) {
  event.preventDefault();
  const input = $('#motion-edit-input');
  const value = input.value.trim();
  const length = codePointLength(value);
  if (!value) return setFieldError(input, $('#motion-edit-error'), '토론할 문장을 적어주세요.');
  if (length > 1200) return setFieldError(input, $('#motion-edit-error'), '문장은 1200자까지 적을 수 있어요.');
  setFieldError(input, $('#motion-edit-error'), '');
  const retry = () => saveMotionEdit(new Event('submit'));
  const data = await performOperation('prepare', '수정한 문장을 적용하고 있어요.', retry, id => api('/api/create-motion', {
    analysis: state.analysis,
    context_summary: state.contextSummary,
    edited_motion: value,
    edit_count: state.motion.edit_count,
  }, id));
  if (!data) return;
  state.motion = data;
  renderMotion();
}

function createSession(motion) {
  return {
    motion: motion.motion,
    side_labels: motion.side_labels,
    personas: motion.personas,
    tone: motion.tone,
    context_summary: motion.context_summary,
    fact_anchor: motion.fact_anchor,
    truth_mode: motion.truth_mode,
    next_index: 0,
    transcript: [],
    audience_status: 'PENDING',
    audience_question: null,
    audience_response_index: 0,
    completed: false,
    debater_models: {},
    debug_enabled: false,
    engine_token: null,
  };
}

async function startDebate() {
  if (!state.motion || state.pendingOperation) return;
  state.session = createSession(state.motion);
  state.debugLog = [];
  state.moderatorEvents = [];
  state.summary = null;
  state.choice = null;
  renderDebateShell();
  showRoute('debate');
  showDebateView('debate-arena');
  history.pushState(null, '', '#debate');
  await runStep('NEXT');
}

function phaseInfo(phase) {
  return PHASES.find(item => item.id === phase) || PHASES[0];
}

function renderPhase(phase) {
  const info = phaseInfo(phase);
  const index = Math.max(0, PHASES.findIndex(item => item.id === info.id));
  $('#phase-number').textContent = String(index + 1).padStart(2, '0');
  $('#phase-name').textContent = info.name;
  $('#debate-heading').textContent = info.title;
  $('#stage-description').textContent = info.description;
  const buildSteps = () => PHASES.map((item, itemIndex) => {
    const li = element('li', '', `${itemIndex < index ? '완료 · ' : ''}${item.name}`);
    if (itemIndex === index) li.setAttribute('aria-current', 'step');
    return li;
  });
  replaceChildren($('#rail-steps'), buildSteps());
  replaceChildren($('#mobile-steps'), buildSteps());
}

function renderDebateShell() {
  const {motion, side_labels: labels, personas} = state.session;
  $('#rail-motion').textContent = motion;
  $('#mobile-motion').textContent = motion;
  $('#mobile-motion-detail').textContent = `토론할 문장: ${motion}`;
  replaceChildren($('#rail-sides'), [sideCard('A', labels[0], personas[0]), sideCard('B', labels[1], personas[1])]);
  replaceChildren($('#mobile-sides'), [sideCard('A', labels[0], personas[0]), sideCard('B', labels[1], personas[1])]);
  renderPhase(state.session.transcript.at(-1)?.phase || 'OPENING');
  renderTranscript();
  $('#audience-panel').hidden = true;
  $('#next-turn').hidden = false;
  $('#show-summary').hidden = true;
}

function turnCard(item, isLatest) {
  const li = element('li', `turn ${item.speaker === 'B' ? 'b' : 'a'} ${isLatest ? 'new' : ''}`);
  li.id = `turn-${item.turn}`;
  const article = element('article');
  const headingId = `turn-${item.turn}-heading`;
  article.setAttribute('aria-labelledby', headingId);
  const identity = element('div', 'identity');
  identity.id = headingId;
  identity.setAttribute('tabindex', '-1');
  identity.append(element('span', `side-badge ${item.speaker === 'B' ? 'side-b' : 'side-a'}`, item.speaker));
  const identityText = element('div');
  identityText.append(document.createTextNode(item.side_label), element('div', 'speaker-meta', `발언 ${item.turn} · ${phaseInfo(item.phase).name}`));
  identity.append(identityText);
  article.append(identity);
  const utterance = element('div', 'utterance markdown-body');
  SaiMarkdown.renderBlock(utterance, item.utterance, {references: item.references || []});
  article.append(utterance);
  li.append(article);
  return li;
}

function moderatorCard(item) {
  const li = element('li', `moderator-card moderator-${String(item.kind || '').toLowerCase()}`);
  li.dataset.moderatorKey = item.key || item.kind || '';
  const marker = element('span', 'moderator-mark', '◇');
  marker.setAttribute('aria-hidden', 'true');
  const copy = element('div', 'moderator-copy');
  copy.append(element('p', 'moderator-label', '사회자'), element('h2', '', item.title || '토론 흐름을 정리합니다.'), element('p', '', item.body || ''));
  li.append(marker, copy);
  return li;
}

function recordModeratorEvents(previousSession, data, context = {}) {
  if (!window.SaiModerator?.eventsForStep) return;
  const incoming = SaiModerator.eventsForStep(previousSession, data, context);
  incoming.forEach(item => {
    if (!state.moderatorEvents.some(existing => existing.key === item.key)) state.moderatorEvents.push(item);
  });
}

function renderTranscript() {
  const transcript = state.session?.transcript || [];
  const eventsByTurn = new Map();
  state.moderatorEvents.forEach(item => {
    const key = Number(item.afterTurn || 0);
    if (!eventsByTurn.has(key)) eventsByTurn.set(key, []);
    eventsByTurn.get(key).push(item);
  });
  const children = [];
  (eventsByTurn.get(0) || []).forEach(item => children.push(moderatorCard(item)));
  transcript.forEach((item, index) => {
    children.push(turnCard(item, index === transcript.length - 1));
    (eventsByTurn.get(Number(item.turn)) || []).forEach(event => children.push(moderatorCard(event)));
  });
  replaceChildren($('#debate-log'), children);
}

function nextButtonLabel() {
  if (state.session.audience_status === 'ASKED') {
    return state.session.audience_response_index === 0 ? '첫 번째 답변 보기 →' : '다른 쪽 답변 보기 →';
  }
  return '다음 발언 보기 →';
}

function updateDebateAfterStep(data, wasNearBottom) {
  state.session = data.session;
  const currentPhase = data.completed ? 'COMPLETE' : data.phase;
  renderPhase(currentPhase);
  renderTranscript();
  $('#next-turn').textContent = nextButtonLabel();
  if (data.awaiting_audience_question) {
    $('#audience-panel').hidden = false;
    $('#next-turn').hidden = true;
    $('#audience-panel h2').focus({preventScroll: false});
  } else {
    $('#audience-panel').hidden = true;
    $('#next-turn').hidden = Boolean(data.completed);
  }
  if (data.completed) $('#show-summary').hidden = false;
  if (data.utterance) {
    if (wasNearBottom) $('#debate-log .turn.new .identity')?.focus({preventScroll: false});
    else $('#new-turn-link').hidden = false;
  }
}

async function runStep(command = 'NEXT', audienceQuestion = null) {
  if (!state.session || state.pendingOperation) return false;
  const snapshot = state.session;
  const wasNearBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 180;
  const retry = () => runStep(command, audienceQuestion);
  let draftNode = null;
  let draftMarkdown = '';
  const clearDraft = () => { draftNode?.remove(); draftNode = null; draftMarkdown = ''; };
  const onDraft = (kind, payload) => {
    if (kind === 'debug') {
      state.debugLog.push({...payload, received_at: new Date().toISOString()});
      return;
    }
    if (kind === 'draft_reset') {
      clearDraft();
      const attempt = Number(payload.attempt || 1);
      const maxAttempts = Number(payload.max_attempts || 3);
      if (attempt > 1) {
        const retryText = payload.retry_strategy === 'REPLAN_AND_REGENERATE'
          ? '다른 방식으로 발언을 다시 준비하고 있어요.'
          : '발언을 다시 다듬고 있어요.';
        setStatus(`${retryText} · ${attempt}/${maxAttempts}`);
      }
      draftNode = element('li', `turn draft-turn ${payload.speaker === 'B' ? 'b' : ''}`);
      draftNode.setAttribute('aria-live', 'off');
      const card = element('article');
      const identity = element('div', 'identity');
      identity.append(element('span', `side-badge ${payload.speaker === 'B' ? 'side-b' : 'side-a'}`, payload.speaker));
      identity.append(element('span', '', payload.side_label || '발언자'));
      const draftUtterance = element('div', 'utterance markdown-body');
      const attemptLabel = Number(payload.attempt || 1) > 1
        ? `재작성 중 · ${payload.attempt}/${payload.max_attempts || 3}`
        : '작성 중 · 아직 확정되지 않았어요';
      card.append(identity, element('p', 'draft-label', attemptLabel), draftUtterance);
      draftNode.append(card);
      $('#debate-log').append(draftNode);
      if (wasNearBottom) draftNode.scrollIntoView({block: 'nearest'});
    } else if (kind === 'draft_delta') {
      if (!draftNode || typeof payload.text !== 'string') throw new AppError('INVALID_RESPONSE', '임시 발언 순서가 올바르지 않습니다.');
      draftMarkdown += payload.text;
      SaiMarkdown.renderBlock($('.utterance', draftNode), draftMarkdown, {draft: true});
    }
  };
  const data = await performOperation('debate', command === 'AUDIENCE_QUESTION' ? '질문을 전달하고 있어요.' : '다음 발언을 준비하고 있어요.', retry, async id => {
    try {
      return await apiDebateStream({session: snapshot, command, audience_question: audienceQuestion}, id, onDraft);
    } finally {
      clearDraft();
    }
  });
  if (!data) return false;
  recordModeratorEvents(snapshot, data, {command, audienceQuestion});
  updateDebateAfterStep(data, wasNearBottom);
  return true;
}

async function submitAudience(event) {
  event.preventDefault();
  const input = $('#audience-input');
  const question = input.value.trim();
  const length = codePointLength(question);
  if (!question) return setFieldError(input, $('#audience-error'), '두 AI에게 물어볼 내용을 적어주세요.');
  if (length > 500) return setFieldError(input, $('#audience-error'), '질문은 500자까지 적을 수 있어요.');
  setFieldError(input, $('#audience-error'), '');
  const registered = await runStep('AUDIENCE_QUESTION', question);
  if (registered) await runStep('NEXT');
}

async function skipAudience() {
  const skipped = await runStep('SKIP_AUDIENCE');
  if (skipped) await runStep('NEXT');
}

function listOrEmpty(items) {
  if (!items?.length) return element('p', 'hint', '정리된 항목이 없어요.');
  const list = element('ul', 'summary-list');
  items.forEach(item => {
    const li = element('li', 'markdown-inline');
    SaiMarkdown.renderInline(li, item);
    list.append(li);
  });
  return list;
}

function runtimePersonaCard(side, persona, model) {
  const card = element('article', `runtime-persona ${side === 'B' ? 'b' : 'a'}`);
  const heading = element('div', 'runtime-persona-heading');
  heading.append(
    element('span', `side-badge ${side === 'B' ? 'side-b' : 'side-a'}`, side),
    element('strong', '', PERSONA_LABELS[persona] || persona || '토론자'),
  );
  card.append(
    heading,
    element('p', 'runtime-persona-description', PERSONA_DESCRIPTIONS[persona] || '주제에 맞는 관점으로 살펴요.'),
  );
  if (model) card.append(element('p', 'runtime-model', model));
  return card;
}

function renderRuntimePersonas(node, wrapper) {
  const models = state.session?.debater_models || {};
  const personas = state.session?.personas || [];
  const cards = [];
  if (models.A) cards.push(runtimePersonaCard('A', personas[0], models.A));
  if (models.B) cards.push(runtimePersonaCard('B', personas[1], models.B));
  replaceChildren(node, cards);
  const hidden = cards.length === 0;
  node.hidden = hidden;
  if (wrapper) wrapper.hidden = hidden;
}

function renderFinalMetadata() {
  renderRuntimePersonas($('#final-models'), $('#final-runtime'));
  renderRuntimePersonas($('#summary-models'), $('#summary-runtime'));
  const button = $('#download-debug');
  button.hidden = !(state.session?.debug_enabled && state.debugLog.length);
}

function debugExportPayload() {
  const session = state.session ? {...state.session} : null;
  if (session) delete session.engine_token;
  const retryEvents = state.debugLog.filter(item => item.event === 'draft_reset' && Number(item.attempt) > 1);
  const rejectedChecks = state.debugLog.filter(item => item.event === 'compliance' && item.accepted === false);
  return {
    exported_at: new Date().toISOString(),
    app: '사이',
    debug_summary: {
      event_count: state.debugLog.length,
      draft_retry_count: retryEvents.length,
      compliance_rejection_count: rejectedChecks.length,
    },
    motion: state.session?.motion || null,
    side_labels: state.session?.side_labels || null,
    personas: state.session?.personas || null,
    debater_models: state.session?.debater_models || null,
    transcript: state.session?.transcript || [],
    moderator_events: state.moderatorEvents,
    debug_events: state.debugLog,
    session: session ? {completed: session.completed, audience_status: session.audience_status, debug_enabled: session.debug_enabled} : null,
  };
}

function downloadDebugLog() {
  if (!state.session?.debug_enabled || !state.debugLog.length) return;
  const blob = new Blob([JSON.stringify(debugExportPayload(), null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `sai-debug-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function renderSummary() {
  $('#summary-motion').textContent = state.session.motion;
  renderFinalMetadata();
  replaceChildren($('#summary-clashes'), [listOrEmpty(state.summary.key_clashes)]);
  const makeSide = (side, points) => {
    const section = element('section', `summary-side ${side.toLowerCase()}`);
    const heading = element('h2', 'identity');
    const index = side === 'A' ? 0 : 1;
    heading.append(element('span', `side-badge ${side === 'B' ? 'side-b' : 'side-a'}`, side), element('span', '', state.session.side_labels[index]));
    section.append(heading, element('h3', '', '강한 논점'), listOrEmpty(points));
    return section;
  };
  replaceChildren($('#summary-sides'), [makeSide('A', state.summary.side_a_strong_points), makeSide('B', state.summary.side_b_strong_points)]);
  replaceChildren($('#summary-agreements'), [listOrEmpty(state.summary.agreements)]);
  replaceChildren($('#summary-unresolved'), [listOrEmpty(state.summary.unresolved)]);
  showDebateView('summary-view');
}

async function loadSummary() {
  const retry = loadSummary;
  const data = await performOperation('summary', '토론 정리를 준비하고 있어요.', retry, id => api('/api/neutral-summary', {
    motion: state.session.motion,
    transcript: state.session.transcript,
  }, id));
  if (!data) return;
  state.summary = data;
  renderSummary();
}

function renderChoice() {
  const labels = [
    ['A', `A · ${state.session.side_labels[0]}`],
    ['UNSURE', '아직 모르겠다'],
    ['B', `B · ${state.session.side_labels[1]}`],
  ];
  replaceChildren($('#choice-options'), labels.map(([value, labelText]) => {
    const label = element('label', 'option');
    const input = element('input'); input.type = 'radio'; input.name = 'choice'; input.value = value;
    label.append(input, document.createTextNode(labelText));
    return label;
  }));
  showDebateView('choice-view');
}

function finishChoice(event) {
  event.preventDefault();
  const selected = $('input[name="choice"]:checked');
  if (!selected) {
    setStatus('선택지를 하나 고른 뒤 마쳐주세요.');
    return;
  }
  state.choice = selected.value;
  const display = selected.value === 'A' ? `A · ${state.session.side_labels[0]}` : selected.value === 'B' ? `B · ${state.session.side_labels[1]}` : '아직 모르겠다';
  $('#done-choice').textContent = `‘${display}’.`;
  renderFinalMetadata();
  setStatus('');
  showDebateView('done-view');
}

function resetDebate() {
  state.view = 'topic-view'; state.analysis = null; state.confirmedContextAnswers = []; state.contextQuestion = null;
  state.contextSummary = null; state.motion = null; state.session = null; state.summary = null; state.choice = null; state.lastRetry = null; state.debugLog = []; state.moderatorEvents = [];
  $('#topic-input').value = '';
  updateCount($('#topic-input'), $('#topic-count'), 2000);
  replaceChildren($('#debate-log'), []);
  clearError(); setStatus(''); showHomeView('topic-view');
  history.pushState(null, '', '#home');
  $('#topic-input').focus();
}

function focusStateReference(link) {
  const href = link?.getAttribute?.('href') || '';
  if (!/^#turn-\d+$/.test(href)) return false;
  const target = document.querySelector(href);
  if (!target) return false;
  target.scrollIntoView({behavior: 'smooth', block: 'center'});
  target.classList.remove('state-ref-highlight');
  requestAnimationFrame(() => {
    target.classList.add('state-ref-highlight');
    setTimeout(() => target.classList.remove('state-ref-highlight'), 1400);
    target.querySelector('.identity')?.focus({preventScroll: true});
  });
  return true;
}

function bindEvents() {
  window.addEventListener('hashchange', routeFromHash);
  $('#topic-form').addEventListener('submit', analyzeTopic);
  $('#topic-input').addEventListener('input', event => updateCount(event.target, $('#topic-count'), 2000));
  $$('.suggestion').forEach(button => button.addEventListener('click', () => {
    $('#topic-input').value = button.dataset.topic;
    updateCount($('#topic-input'), $('#topic-count'), 2000);
    $('#topic-input').focus();
  }));
  $('#context-form').addEventListener('submit', submitContext);
  $('#context-free-input').addEventListener('input', event => updateCount(event.target, $('#context-free-count'), 1000));
  $('#context-review-submit').addEventListener('click', () => prepareMotion(state.contextSummary));
  $('#motion-edit-form').addEventListener('submit', saveMotionEdit);
  $('#motion-edit-input').addEventListener('input', event => updateCount(event.target, $('#motion-edit-count'), 1200));
  $('#motion-edit-cancel').addEventListener('click', () => { $('#motion-edit-details').open = false; $('#motion-edit-input').value = state.motion.motion; });
  $('#start-debate').addEventListener('click', startDebate);
  $('#next-turn').addEventListener('click', () => runStep('NEXT'));
  $('#audience-form').addEventListener('submit', submitAudience);
  $('#audience-input').addEventListener('input', event => updateCount(event.target, $('#audience-count'), 500));
  $('#skip-audience').addEventListener('click', skipAudience);
  $('#show-summary').addEventListener('click', loadSummary);
  $('#open-choice').addEventListener('click', renderChoice);
  $('#back-to-debate').addEventListener('click', () => showDebateView('debate-arena'));
  $('#back-to-summary').addEventListener('click', () => showDebateView('summary-view'));
  $('#choice-form').addEventListener('submit', finishChoice);
  $('#restart').addEventListener('click', resetDebate);
  $('#download-debug').addEventListener('click', downloadDebugLog);
  $('#reread-debate').addEventListener('click', () => showDebateView('debate-arena'));
  $('#new-turn-link').addEventListener('click', () => { $('#new-turn-link').hidden = true; });
  $('#debate-log').addEventListener('click', event => {
    const link = event.target.closest?.('a.state-ref');
    if (!link) return;
    if (focusStateReference(link)) event.preventDefault();
  });
  $('#dismiss-error').addEventListener('click', clearError);
  $('#retry-action').addEventListener('click', () => { const retry = state.lastRetry; clearError(); retry?.(); });
  $('#stop-waiting').addEventListener('click', () => {
    const operation = state.pendingOperation;
    if (!operation) return;
    state.pendingOperation = {id: `stopped-${operation.id}`, name: operation.name};
    state.activeController?.abort('stopped');
    clearOperationTimers();
    state.pendingOperation = null;
    state.activeController = null;
    $('#loading-turn').hidden = true;
    $$('button').forEach(button => { button.disabled = false; });
    showError(operation.name, new AppError('STOPPED', 'stopped'));
  });
  window.addEventListener('beforeunload', event => {
    if (state.session && state.view !== 'done-view') { event.preventDefault(); event.returnValue = ''; }
  });
}

bindEvents();
showHomeView('topic-view', false);
routeFromHash();
loadBuildVersion();
