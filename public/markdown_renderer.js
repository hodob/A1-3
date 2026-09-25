/* Safe Markdown rendering for AI-generated conversation text. */
(function (root, factory) {
  const api = factory(root);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.SaiMarkdown = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';

  const SANITIZE_OPTIONS = {
    ALLOWED_TAGS: [
      'p', 'br', 'strong', 'em', 'del', 'code', 'pre', 'blockquote',
      'ul', 'ol', 'li', 'a', 'hr', 'h1', 'h2', 'h3', 'h4',
      'table', 'thead', 'tbody', 'tr', 'th', 'td'
    ],
    ALLOWED_ATTR: ['href', 'title'],
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
  };

  function dependenciesReady() {
    return Boolean(
      root.marked &&
      typeof root.marked.parse === 'function' &&
      typeof root.marked.parseInline === 'function' &&
      root.DOMPurify &&
      typeof root.DOMPurify.sanitize === 'function'
    );
  }

  function hardenLinks(node) {
    if (!node || typeof node.querySelectorAll !== 'function') return;
    node.querySelectorAll('a').forEach(link => {
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener noreferrer nofollow');
    });
  }

  function render(node, source, inline) {
    if (!node) return;
    const markdown = String(source ?? '');
    if (!dependenciesReady()) {
      node.textContent = markdown;
      node.classList?.remove?.('markdown-rendered');
      node.classList?.add?.('markdown-fallback');
      return;
    }

    try {
      const parserOptions = {gfm: true, breaks: true, async: false};
      const rawHtml = inline
        ? root.marked.parseInline(markdown, parserOptions)
        : root.marked.parse(markdown, parserOptions);
      const cleanHtml = root.DOMPurify.sanitize(rawHtml, SANITIZE_OPTIONS);
      node.innerHTML = cleanHtml;
      node.classList?.remove?.('markdown-fallback');
      node.classList?.add?.('markdown-rendered');
      hardenLinks(node);
    } catch (_) {
      node.textContent = markdown;
      node.classList?.remove?.('markdown-rendered');
      node.classList?.add?.('markdown-fallback');
    }
  }

  return {
    renderBlock(node, source) { render(node, source, false); },
    renderInline(node, source) { render(node, source, true); },
  };
});
