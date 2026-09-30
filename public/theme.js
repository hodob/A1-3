(() => {
  const KEY = 'sai-theme';
  const root = document.documentElement;
  const media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  const stored = () => {
    try {
      const value = localStorage.getItem(KEY);
      return value === 'dark' || value === 'light' ? value : null;
    } catch {
      return null;
    }
  };
  const systemTheme = () => (media && media.matches ? 'dark' : 'light');

  // 첫 화면이 그려지기 전에 적용해 깜빡임을 막는다.
  root.dataset.theme = stored() || systemTheme();

  const sync = (button) => {
    const dark = root.dataset.theme === 'dark';
    button.setAttribute('aria-pressed', String(dark));
    button.querySelector('.theme-toggle-icon').textContent = dark ? '☀' : '☾';
    button.querySelector('.theme-toggle-label').textContent = dark ? '라이트 모드' : '다크 모드';
  };

  document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('theme-toggle');
    if (!button) return;
    sync(button);
    button.addEventListener('click', () => {
      const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem(KEY, next); } catch { /* 저장이 막혀도 현재 화면에는 적용된다 */ }
      sync(button);
    });
    // 직접 고른 적이 없으면 기기 설정 변경을 따라간다.
    if (media) {
      media.addEventListener('change', () => {
        if (stored()) return;
        root.dataset.theme = systemTheme();
        sync(button);
      });
    }
  });
})();
