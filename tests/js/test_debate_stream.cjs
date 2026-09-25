const assert = require('node:assert/strict');
const {test} = require('node:test');
const {readDebateStream} = require('../../public/debate_stream.js');

function response(parts) {
  const encoder = new TextEncoder();
  return {body: new ReadableStream({
    start(controller) {
      parts.forEach(part => controller.enqueue(encoder.encode(part)));
      controller.close();
    },
  })};
}

test('draft chunks and split frames commit only on commit event', async () => {
  const seen = [];
  const result = await readDebateStream(response([
    'event: draft_reset\ndata: {"speaker":"A"}\n\nevent: draft_delta\ndata: {"text":"안',
    '녕"}\n\nevent: commit\ndata: {"utterance":"안녕","session":{}}\n\n',
  ]), (kind, data) => seen.push([kind, data]));
  assert.equal(result.utterance, '안녕');
  assert.deepEqual(seen.map(item => item[0]), ['draft_reset', 'draft_delta']);
});

test('error after a draft rejects without commit', async () => {
  const seen = [];
  await assert.rejects(
    readDebateStream(response(['event: draft_delta\ndata: {"text":"폐기"}\n\nevent: error\ndata: {"code":"SAFE_FAILURE","message":"실패"}\n\n']), (kind, data) => seen.push([kind, data])),
    error => error.code === 'SAFE_FAILURE',
  );
  assert.equal(seen.length, 1);
});

test('closed stream without commit is rejected', async () => {
  await assert.rejects(readDebateStream(response(['event: draft_delta\ndata: {"text":"미완"}\n\n']), () => {}), error => error.code === 'INCOMPLETE_STREAM');
});


test('debug events are forwarded before commit', async () => {
  const seen = [];
  const result = await readDebateStream(response([
    'event: debug\ndata: {"event":"draft_reset","attempt":2}\n\nevent: commit\ndata: {"utterance":"ok","session":{}}\n\n',
  ]), (kind, data) => seen.push([kind, data]));
  assert.equal(result.utterance, 'ok');
  assert.deepEqual(seen[0], ['debug', {event: 'draft_reset', attempt: 2}]);
});
