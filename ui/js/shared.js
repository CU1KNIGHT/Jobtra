// Shared sidebar behavior across all pages.
// Fetch app config once and show the version at the bottom of the sidebar.
document.addEventListener('DOMContentLoaded', function () {
  const el = document.getElementById('app-version');
  if (!el) return;
  fetch('/api/config')
    .then(r => r.json())
    .then(cfg => {
      if (cfg && cfg.version) el.textContent = 'v' + cfg.version;
    })
    .catch(() => { /* leave version blank if config can't be loaded */ });
});

// ── Pagination ───────────────────────────────────────────────────────────────
// Clamp a (possibly stale) page number to the valid range for a list length.
function clampPage(page, total, pageSize) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return Math.min(Math.max(1, page), pages);
}

// Build pager controls for a client-side paged list. Returns '' (no pager) when
// the list fits on a single page. Buttons call the global `fn`(pageNumber).
function renderPager(total, page, pageSize, fn) {
  const pages = Math.ceil(total / pageSize);
  if (pages <= 1) return '';
  page = clampPage(page, total, pageSize);
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  const btn = (label, n, { disabled = false, active = false } = {}) =>
    `<button class="pager-btn${active ? ' pager-active' : ''}" ${disabled ? 'disabled' : ''} onclick="${fn}(${n})">${label}</button>`;

  // Windowed page numbers: first, last and ±1 around the current page.
  const want = new Set([1, pages, page, page - 1, page + 1]);
  const nums = [];
  let prev = 0;
  for (let n = 1; n <= pages; n++) {
    if (!want.has(n)) continue;
    if (n - prev > 1) nums.push('<span class="pager-gap">…</span>');
    nums.push(btn(String(n), n, { active: n === page }));
    prev = n;
  }

  return `<div class="pager">
    <span class="pager-info">${from}–${to} of ${total}</span>
    <div class="pager-controls">
      ${btn('‹ Prev', page - 1, { disabled: page <= 1 })}
      ${nums.join('')}
      ${btn('Next ›', page + 1, { disabled: page >= pages })}
    </div>
  </div>`;
}
