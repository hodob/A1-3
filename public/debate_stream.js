/* Parse the debate SSE protocol without treating provisional text as a committed turn. */
function streamError(code, message) {
  const error = new Error(message || code);
  error.code = code;
  return error;
}

async function readDebateStream(response, onDraft) {
  if (!response.body) throw streamError('INCOMPLETE_STREAM', '스트림을 읽을 수 없습니다.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  let commit = null;

  function consume(block) {
    let kind = '';
    const dataLines = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith('event:')) kind = line.slice(6).trim();
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
    }
    if (!kind) return;
    let data;
    try { data = JSON.parse(dataLines.join('\n')); }
    catch (_) { throw streamError('INVALID_RESPONSE', '스트림 응답 형식이 올바르지 않습니다.'); }
    if (kind === 'error') throw streamError(data.code || 'API_ERROR', data.message || '발언을 확정하지 못했습니다.');
    if (kind === 'commit') {
      if (commit !== null) throw streamError('INVALID_RESPONSE', '확정 발언이 중복되었습니다.');
      commit = data;
    } else if (kind === 'draft_reset' || kind === 'draft_delta' || kind === 'debug') {
      if (commit !== null) throw streamError('INVALID_RESPONSE', '확정 뒤 임시 발언이 도착했습니다.');
      onDraft(kind, data);
    }
  }

  try {
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      pending += decoder.decode(value, {stream: true});
      let separator;
      while ((separator = /\r?\n\r?\n/.exec(pending))) {
        const block = pending.slice(0, separator.index);
        pending = pending.slice(separator.index + separator[0].length);
        consume(block);
      }
    }
    if (pending.trim()) throw streamError('INCOMPLETE_STREAM', '스트림이 도중에 끊겼습니다.');
    if (commit === null) throw streamError('INCOMPLETE_STREAM', '확정 발언을 받지 못했습니다.');
    return commit;
  } finally {
    reader.releaseLock();
  }
}

if (typeof module !== 'undefined' && module.exports) module.exports = {readDebateStream};
