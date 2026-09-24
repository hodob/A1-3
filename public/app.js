const $ = (selector) => document.querySelector(selector);

const state = {
  analysis: null,
  motion: null,
  session: null,
  contextAnswers: [],
  contextSummary: null,
};

const topicInput = $('#topic-input');
const topicForm = $('#topic-form');
const topicSubmit = $('#topic-submit');
const homeStatus = $('#home-status');
const motionCard = $('#motion-card');
const debateLog = $('#debate-log');
const debateEmpty = $('#debate-empty');
const debateStatus = $('#debate-status');
const debateControls = $('#debate-controls');
const nextTurn = $('#next-turn');
const phasePill = $('#phase-pill');
const audiencePanel = $('#audience-panel');
const contextPanel = $('#context-panel');
const summaryPanel = $('#summary-panel');
const choicePanel = $('#choice-panel');

function setStatus(node, message, error = false) {
  node.textContent = message;
  node.classList.toggle('error', error);
}

async function api(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 180000);
  try {
    const response = await fetch(path, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), signal: controller.signal,
    });
    const payload = await response.json().catch(() => ({ok:false,error:{code:'INVALID_RESPONSE',message:'잘못된 응답'}}));
    if (!response.ok || !payload.ok) throw new Error(payload.error?.message || '응답을 생성하지 못했습니다. 다시 시도해주세요.');
    return payload.data;
  } catch (error) {
    if (error?.name === 'AbortError') throw new Error('응답이 지연되고 있습니다. 다시 시도해주세요.');
    throw error;
  } finally { clearTimeout(timer); }
}

function renderMotion(data) {
  state.motion = data;
  motionCard.classList.remove('hidden');
  motionCard.innerHTML = `<p class="eyebrow">MOTION PREVIEW</p><h3>${escapeHtml(data.motion)}</h3><p class="versus">${escapeHtml(data.side_labels[0])} VS ${escapeHtml(data.side_labels[1])}</p><div class="motion-actions"><button id="start-debate" type="button">이 논제로 시작</button><button id="edit-motion" class="secondary" type="button">1회 수정</button></div>`;
  $('#start-debate').addEventListener('click', createMotionAndStart);
  $('#edit-motion').addEventListener('click', editMotion);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

async function prepareMotion(contextSummary = null) {
  const data = await api('/api/create-motion', {analysis: state.analysis, context_summary: contextSummary, edit_count: 0});
  state.contextSummary = contextSummary;
  renderMotion(data);
  return data;
}

async function analyzeTopic(event) {
  event.preventDefault();
  const topic = topicInput.value.trim();
  if (!topic) return setStatus(homeStatus, '토론할 주제를 입력해주세요.', true);
  topicSubmit.disabled = true;
  setStatus(homeStatus, '주제를 분석하고 있습니다...');
  try {
    const data = await api('/api/analyze-topic', {topic});
    state.analysis = data;
    if (data.interaction_state === 'CONTEXT_REQUIRED') {
      state.contextAnswers = [];
      await nextContextQuestion();
      document.querySelector('#debate').scrollIntoView({behavior:'smooth'});
    } else if (data.interaction_state === 'INFORMATIONAL_FIRST') {
      setStatus(homeStatus, data.confirmation_reason || '정보 질문은 바로 토론으로 바꾸지 않습니다.', true);
    } else {
      await prepareMotion();
      setStatus(homeStatus, '논제를 확인해주세요.');
    }
  } catch (error) {
    setStatus(homeStatus, error.message || '응답을 생성하지 못했습니다. 다시 시도해주세요.', true);
  } finally { topicSubmit.disabled = false; }
}

function renderContextSummary(summary, completeness) {
  const groups = [
    ['USER_OBSERVATION', '직접 확인'],
    ['REPORTED_CLAIM', '전달된 주장'],
    ['USER_ASSUMPTION', '사용자의 해석'],
    ['UNKNOWN', '확인되지 않은 내용'],
  ];
  const cards = groups.map(([key, label]) => {
    const items = summary?.[key] || [];
    const content = items.length ? `<ul>${items.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : '<p>없음</p>';
    return `<article><h4>${label}</h4>${content}</article>`;
  }).join('');
  contextPanel.innerHTML = `<strong>상황 파악 ${completeness}%</strong><p>토론에 사용할 맥락을 확인해주세요.</p><div class="context-review">${cards}</div>`;
}

async function submitContextAnswer(questionId, answer) {
  const normalized = String(answer || '').trim();
  if (!normalized) return setStatus(debateStatus, '답변을 입력해주세요.', true);
  state.contextAnswers.push({question_id:questionId, answer:normalized});
  await nextContextQuestion();
}

async function nextContextQuestion() {
  setStatus(debateStatus, '상황을 파악하고 있습니다...');
  try {
    const data = await api('/api/context-step', {topic: state.analysis.original_topic, answers: state.contextAnswers});
    contextPanel.classList.remove('hidden');
    if (data.debate_ready) {
      renderContextSummary(data.context_summary, data.context_completeness);
      await prepareMotion(data.context_summary);
      setStatus(debateStatus, '논제를 확인해주세요.');
      return;
    }
    const q = data.question;
    const options = [...q.options];
    if (q.allow_unknown && !options.includes('잘 모르겠다')) options.push('잘 모르겠다');
    const freeText = q.allow_free_text ? `<div class="context-free-text"><textarea id="context-free-input" maxlength="1000" rows="2" placeholder="직접 입력"></textarea><button type="button" id="context-free-submit" class="secondary">직접 입력</button></div>` : '';
    contextPanel.innerHTML = `<strong>상황 파악 ${data.context_completeness}%</strong><p>${escapeHtml(q.text)}</p><div class="motion-actions">${options.map(o=>`<button type="button" class="context-option secondary" data-answer="${escapeHtml(o)}">${escapeHtml(o)}</button>`).join('')}</div>${freeText}`;
    contextPanel.querySelectorAll('.context-option').forEach(btn => btn.addEventListener('click', () => submitContextAnswer(q.id, btn.dataset.answer)));
    const freeSubmit = $('#context-free-submit');
    if (freeSubmit) freeSubmit.addEventListener('click', () => submitContextAnswer(q.id, $('#context-free-input').value));
    setStatus(debateStatus, '');
  } catch (error) { setStatus(debateStatus, error.message || '응답을 생성하지 못했습니다. 다시 시도해주세요.', true); }
}

async function editMotion() {
  if (state.motion?.edit_count >= 1) return setStatus(homeStatus, '논제 수정은 한 번만 가능합니다.', true);
  const edited = window.prompt('수정할 논제를 입력하세요.', state.motion.motion);
  if (!edited?.trim()) return;
  try {
    const data = await api('/api/create-motion', {analysis:state.analysis, context_summary:state.contextSummary, edited_motion:edited.trim(), edit_count:state.motion?.edit_count || 0});
    state.motion = data;
    motionCard.querySelector('h3').textContent = data.motion;
    motionCard.querySelector('#edit-motion').disabled = true;
  } catch (error) { setStatus(homeStatus, error.message || '응답을 생성하지 못했습니다. 다시 시도해주세요.', true); }
}

async function createMotionAndStart() {
  try {
    const motion = state.motion;
    if (!motion?.motion) throw new Error('논제가 준비되지 않았습니다.');
    state.session = {motion:motion.motion, side_labels:motion.side_labels, personas:motion.personas, tone:motion.tone, context_summary:motion.context_summary, fact_anchor:motion.fact_anchor, truth_mode:motion.truth_mode, next_index:0, transcript:[], audience_status:'PENDING', audience_question:null, audience_response_index:0, completed:false, engine_token:null};
    debateEmpty.classList.add('hidden');
    debateControls.classList.remove('hidden');
    motionCard.classList.add('hidden');
    document.querySelector('#debate').scrollIntoView({behavior:'smooth'});
    setStatus(debateStatus, '준비되었습니다. 다음 발언을 눌러 토론을 진행하세요.');
  } catch (error) { setStatus(homeStatus, error.message || '응답을 생성하지 못했습니다. 다시 시도해주세요.', true); }
}

function appendTurn(data) {
  if (!data.utterance) return;
  const article = document.createElement('article');
  article.className = `turn ${data.speaker === 'B' ? 'b' : 'a'}`;
  article.innerHTML = `<div class="turn-head"><span class="side">${escapeHtml(data.side_label)}</span><span>${escapeHtml(data.phase)}</span></div><div>${escapeHtml(data.utterance)}</div>`;
  debateLog.appendChild(article);
  article.scrollIntoView({behavior:'smooth', block:'nearest'});
}

function renderAudiencePrompt() {
  audiencePanel.classList.remove('hidden');
  audiencePanel.innerHTML = `<strong>관객 질문이 있나요?</strong><p>같은 질문을 양측 모두에게 던집니다.</p><textarea id="audience-input" maxlength="500" rows="2" placeholder="질문을 입력하세요"></textarea><div class="motion-actions"><button id="send-audience" type="button">질문하기</button><button id="skip-audience" class="secondary" type="button">계속 보기</button></div>`;
  $('#send-audience').addEventListener('click', async () => {
    const value = $('#audience-input').value.trim();
    if (!value) return setStatus(debateStatus, '관객 질문을 입력해주세요.', true);
    await runStep('AUDIENCE_QUESTION', value);
    audiencePanel.classList.add('hidden');
  });
  $('#skip-audience').addEventListener('click', async () => {
    await runStep('SKIP_AUDIENCE');
    audiencePanel.classList.add('hidden');
  });
}

async function runStep(command='NEXT', audienceQuestion=null) {
  if (!state.session) return;
  nextTurn.disabled = true;
  setStatus(debateStatus, '토론자가 생각하고 있습니다...');
  try {
    const data = await api('/api/debate-step', {session:state.session, command, audience_question:audienceQuestion});
    state.session = data.session;
    phasePill.textContent = data.phase;
    appendTurn(data);
    if (data.awaiting_audience_question) renderAudiencePrompt();
    if (data.completed) await finishDebate();
    else setStatus(debateStatus, '');
  } catch (error) {
    setStatus(debateStatus, error.message || '응답을 생성하지 못했습니다. 다시 시도해주세요.', true);
  } finally { nextTurn.disabled = false; }
}

async function finishDebate() {
  debateControls.classList.add('hidden');
  setStatus(debateStatus, '토론을 정리하고 있습니다...');
  try {
    const data = await api('/api/neutral-summary', {motion:state.session.motion, transcript:state.session.transcript});
    summaryPanel.classList.remove('hidden');
    summaryPanel.innerHTML = `<p class="eyebrow">NEUTRAL SUMMARY</p><div class="summary-grid"><article><h3>핵심 쟁점</h3><ul>${data.key_clashes.map(x=>`<li>${escapeHtml(x)}</li>`).join('')}</ul></article><article><h3>A의 강한 논점</h3><ul>${data.side_a_strong_points.map(x=>`<li>${escapeHtml(x)}</li>`).join('')}</ul></article><article><h3>B의 강한 논점</h3><ul>${data.side_b_strong_points.map(x=>`<li>${escapeHtml(x)}</li>`).join('')}</ul></article><article><h3>합의한 부분</h3><ul>${data.agreements.map(x=>`<li>${escapeHtml(x)}</li>`).join('')}</ul></article><article><h3>남은 쟁점</h3><ul>${data.unresolved.map(x=>`<li>${escapeHtml(x)}</li>`).join('')}</ul></article></div>`;
    choicePanel.classList.remove('hidden');
    choicePanel.innerHTML = `<h3>어느 쪽이 더 설득력 있었나요?</h3><div class="choice-buttons"><button data-choice="A">${escapeHtml(state.session.side_labels[0])}</button><button data-choice="UNSURE">아직 모르겠다</button><button data-choice="B">${escapeHtml(state.session.side_labels[1])}</button></div><p id="choice-result"></p>`;
    choicePanel.querySelectorAll('button').forEach(btn => btn.addEventListener('click', () => { $('#choice-result').textContent = `선택: ${btn.textContent}`; }));
    setStatus(debateStatus, '토론이 끝났습니다.');
  } catch (error) { setStatus(debateStatus, error.message || '응답을 생성하지 못했습니다. 다시 시도해주세요.', true); }
}

topicInput.addEventListener('input', () => { $('#topic-count').textContent = `${topicInput.value.length} / 2000`; });
topicForm.addEventListener('submit', analyzeTopic);
nextTurn.addEventListener('click', () => runStep('NEXT'));
