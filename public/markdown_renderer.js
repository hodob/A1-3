/* Safe Markdown rendering for AI-generated conversation text and state references. */
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

  function referenceMarkdown(source, options = {}) {
    const refs = new Map((options.references || []).map(item => [item.id, item]));
    let text = String(source ?? '');
    if (options.draft) {
      text = text.replace(/\[\[[CQ]\d*$/g, '');
    }
    return text.replace(/\[\[([CQ]\d+)\]\]/g, (whole, id) => {
      if (options.draft) return '↖ 이전 발언';
      const ref = refs.get(id);
      if (!ref || !Number.isFinite(Number(ref.turn))) return whole;
      const speaker = ref.speaker === 'B' ? 'B' : 'A';
      const turn = Number(ref.turn);
      return '[↖ ' + speaker + ' · 발언 ' + turn + '](#turn-' + turn + ' "State ' + id + '")';
    });
  }

  function hardenLinks(node) {
    if (!node || typeof node.querySelectorAll !== 'function') return;
    node.querySelectorAll('a').forEach(link => {
      const href = typeof link.getAttribute === 'function' ? (link.getAttribute('href') || '') : '';
      if (/^#turn-\d+$/.test(href)) {
        link.classList?.add?.('state-ref');
        if (typeof link.removeAttribute === 'function') {
          link.removeAttribute('target');
          link.removeAttribute('rel');
        }
        return;
      }
      link.setAttribute?.('target', '_blank');
      link.setAttribute?.('rel', 'noopener noreferrer nofollow');
    });
  }

  function render(node, source, inline, options = {}) {
    if (!node) return;
    const markdown = referenceMarkdown(source, options);
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
    referenceMarkdown,
    renderBlock(node, source, options = {}) { render(node, source, false, options); },
    renderInline(node, source, options = {}) { render(node, source, true, options); },
  };
});
