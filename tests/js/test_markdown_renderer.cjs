const assert = require('node:assert/strict');
const {test, beforeEach, afterEach} = require('node:test');

const rendererPath = require.resolve('../../public/markdown_renderer.js');

function fakeNode() {
  return {
    textContent: '',
    innerHTML: '',
    links: [],
    classList: {add() {}, remove() {}},
    querySelectorAll(selector) { return selector === 'a' ? this.links : []; },
  };
}

function fakeLink(href = '') {
  return {
    attrs: {href},
    classes: [],
    setAttribute(name, value) { this.attrs[name] = value; },
    getAttribute(name) { return this.attrs[name] || null; },
    removeAttribute(name) { delete this.attrs[name]; },
    classList: {add() {}},
  };
}

beforeEach(() => {
  delete require.cache[rendererPath];
  delete global.marked;
  delete global.DOMPurify;
  delete global.SaiMarkdown;
});

afterEach(() => {
  delete require.cache[rendererPath];
  delete global.marked;
  delete global.DOMPurify;
  delete global.SaiMarkdown;
});

test('falls back to textContent when markdown dependencies are unavailable', () => {
  const api = require(rendererPath);
  const node = fakeNode();
  api.renderBlock(node, '**safe** <script>alert(1)</script>');
  assert.equal(node.textContent, '**safe** <script>alert(1)</script>');
  assert.equal(node.innerHTML, '');
});

test('parses then sanitizes block markdown before assigning HTML', () => {
  const calls = [];
  global.marked = {
    parse(source, options) { calls.push(['parse', source, options]); return '<p><strong>hello</strong></p>'; },
    parseInline(source, options) { calls.push(['inline', source, options]); return '<strong>hello</strong>'; },
  };
  global.DOMPurify = {sanitize(html, options) { calls.push(['sanitize', html, options]); return html; }};
  const api = require(rendererPath);
  const node = fakeNode();
  api.renderBlock(node, '**hello**');
  assert.equal(node.innerHTML, '<p><strong>hello</strong></p>');
  assert.equal(calls[0][0], 'parse');
  assert.equal(calls[1][0], 'sanitize');
});

test('renders external links in hardened new tabs', () => {
  global.marked = {parse() { return ''; }, parseInline() { return '<a href="https://example.com">source</a>'; }};
  global.DOMPurify = {sanitize(html) { return html; }};
  const link = fakeLink('https://example.com');
  const node = fakeNode(); node.links = [link];
  const api = require(rendererPath);
  api.renderInline(node, '[source](https://example.com)');
  assert.equal(link.attrs.target, '_blank');
  assert.equal(link.attrs.rel, 'noopener noreferrer nofollow');
});

test('turn reference markers become same-page turn links', () => {
  const api = require(rendererPath);
  const rendered = api.referenceMarkdown(
    '앞서 [[C24]]의 기준과 [[Q3]]을 봅니다.',
    {references: [
      {id: 'C24', speaker: 'A', turn: 11},
      {id: 'Q3', speaker: 'B', turn: 8},
    ]}
  );
  assert.match(rendered, /\[↖ A · 발언 11\]\(#turn-11/);
  assert.match(rendered, /\[↖ B · 발언 8\]\(#turn-8/);
  assert.doesNotMatch(rendered, /\[\[C24\]\]/);
});

test('draft rendering hides incomplete reference marker tails', () => {
  const api = require(rendererPath);
  assert.equal(api.referenceMarkdown('문장 [[C2', {draft: true}), '문장 ');
  assert.equal(api.referenceMarkdown('문장 [[C24]]', {draft: true}), '문장 ↖ 이전 발언');
});

test('state reference links stay in the current page', () => {
  global.marked = {parse() { return ''; }, parseInline() { return ''; }};
  global.DOMPurify = {sanitize(html) { return html; }};
  const link = fakeLink('#turn-11');
  let stateClass = null;
  link.classList = {add(value) { stateClass = value; }};
  const node = fakeNode(); node.links = [link];
  const api = require(rendererPath);
  api.renderBlock(node, '[[C24]]', {references: [{id: 'C24', speaker: 'A', turn: 11}]});
  assert.equal(stateClass, 'state-ref');
  assert.equal(link.attrs.target, undefined);
  assert.equal(link.attrs.rel, undefined);
});
