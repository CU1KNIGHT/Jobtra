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

// ── About dialog ─────────────────────────────────────────────────────────────
// Injected once per page so the sidebar "About" link works everywhere.
document.addEventListener('DOMContentLoaded', function () {
  if (document.getElementById('aboutDialog')) return;
  const dlg = document.createElement('dialog');
  dlg.id = 'aboutDialog';
  dlg.innerHTML = `
    <div class="dialog-header">About Jobtra</div>
    <div class="dialog-body">
      <div class="about-brand">
        <img src="/static/favicon.svg" alt="Jobtra logo" width="40" height="40">
        <div>
          <div class="about-name">Jobtra</div>
          <div class="about-version" id="aboutVersion">v—</div>
        </div>
      </div>
      <p class="about-desc">
        A self-hosted app for tracking your job hunt end to end — applications,
        documents, and recruiter emails — in one place. It runs locally on a single
        SQLite file and uses an LLM (local or hosted) to parse postings and classify
        incoming email. No accounts, no cloud, no telemetry.
      </p>
      <ul class="about-features">
        <li><strong>Application tracking</strong> — a six-stage pipeline with rich fields for company, role, location, contacts, skills, and more.</li>
        <li><strong>AI job parsing</strong> — paste a posting or a URL and the LLM fills in the fields; re-parse any saved job to refresh it.</li>
        <li><strong>One-click bookmarklet</strong> — save the job you're viewing straight to the tracker.</li>
        <li><strong>Dashboard analytics</strong> — totals, pipeline, interview and rejection rates, recent applications, and breakdowns by month, status, type, city, and role.</li>
        <li><strong>Document manager</strong> — upload résumés and cover letters, attach them to applications, de-duplicated by content hash.</li>
        <li><strong>Email sync &amp; classification</strong> — connect IMAP mailboxes; the LLM flags job-related mail, auto-links it to the matching application, and can advance its status. Passwords encrypted at rest.</li>
        <li><strong>Import / export</strong> — bulk-import from CSV/JSON with duplicate detection, export back to CSV.</li>
        <li><strong>Local &amp; cloud LLMs</strong> — Ollama and LM Studio (local), or Anthropic and OpenAI.</li>
        <li><strong>Dark / light theme</strong> and a responsive, dependency-free UI.</li>
      </ul>
      <dl class="about-meta">
        <dt>Author</dt><dd>Mahmoud Kiki</dd>
        <dt>License</dt><dd>MIT License</dd>
        <dt>Copyright</dt><dd>© 2026 Mahmoud Kiki </dd>
      </dl>
      <p class="about-license">
        Permission is hereby granted, free of charge, to any person obtaining a copy of
        this software and associated documentation files (the &ldquo;Software&rdquo;), to deal
        in the Software without restriction. The Software is provided &ldquo;as is&rdquo;,
        without warranty of any kind. See the
        <a href="https://opensource.org/licenses/MIT" target="_blank" rel="noopener"><code>LICENSE</code></a>
        file for the full text.
      </p>
    </div>
    <div class="dialog-footer">
      <button class="btn btn-primary" onclick="closeAbout()">Close</button>
    </div>`;
  document.body.appendChild(dlg);
  // Close when clicking the backdrop.
  dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
});

async function openAbout() {
  const dlg = document.getElementById('aboutDialog');
  if (!dlg) return;
  const ver = document.getElementById('aboutVersion');
  try {
    const cfg = await fetch('/api/config').then(r => r.json());
    if (cfg && cfg.version) ver.textContent = 'v' + cfg.version;
  } catch { /* leave version placeholder if config can't be loaded */ }
  dlg.showModal();
}

function closeAbout() {
  const dlg = document.getElementById('aboutDialog');
  if (dlg) dlg.close();
}

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
