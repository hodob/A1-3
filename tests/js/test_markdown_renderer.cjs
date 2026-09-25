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

test('renders inline markdown and hardens generated links', () => {
  global.marked = {parse() { return ''; }, parseInline() { return '<a href="https://example.com">source</a>'; }};
  global.DOMPurify = {sanitize(html) { return html; }};
  const link = {attrs: {}, setAttribute(name, value) { this.attrs[name] = value; }};
  const node = fakeNode(); node.links = [link];
  const api = require(rendererPath);
  api.renderInline(node, '[source](https://example.com)');
  assert.equal(link.attrs.target, '_blank');
  assert.equal(link.attrs.rel, 'noopener noreferrer nofollow');
});
