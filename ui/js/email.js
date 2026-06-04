let messages = [];
let allJobs = [];
let expandedId = null;
let syncPollInterval = null;
let processingIds = new Set();
let activeFilter = '';
let pageSize = 25;     // items per page, from settings
let currentPage = 1;

const STATUS_LABELS = {
  rejection: 'Rejection', interview_invite: 'Interview invite',
  offer: 'Offer', application_received: 'Received', other: 'Other',
};
const STATUS_BADGE = {
  rejection: 'badge-rejection', interview_invite: 'badge-interview',
  offer: 'badge-offer', application_received: 'badge-application',
  other: 'badge-other',
};

function showToast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (isError ? ' error' : '');
  t.style.display = 'block';
  clearTimeout(t._tid);
  t._tid = setTimeout(() => { t.style.display = 'none'; }, 3500);
}

async function init() {
  await loadPageSize();
  await Promise.all([loadMessages(), loadStatus(), loadAccounts(), loadAllJobs()]);
}

async function loadPageSize() {
  try {
    const r = await fetch('/api/settings');
    const s = await r.json();
    if (s.page_size) pageSize = s.page_size;
  } catch (_) {}
}

function gotoPage(n) {
  currentPage = n;
  render();
  document.getElementById('messagesList')?.scrollIntoView({ block: 'start' });
}

// Search box changed — jump back to the first page.
function onSearchChange() {
  currentPage = 1;
  render();
}

// Account dropdown changed — reset paging then reload that account's messages.
function onAccountChange() {
  currentPage = 1;
  loadMessages();
}

async function loadAllJobs() {
  try { const r = await fetch('/api/jobs'); allJobs = await r.json(); } catch (_) { allJobs = []; }
}

async function loadMessages() {
  const accountId = document.getElementById('accountFilter').value;
  let url = '/api/email/messages?';
  if (accountId) url += `account_id=${accountId}&`;
  try {
    const r = await fetch(url);
    messages = await r.json();
    render();
  } catch (_) {}
}

async function loadStatus() {
  try {
    const r = await fetch('/api/email/status');
    const s = await r.json();
    const el = document.getElementById('syncInfo');
    if (s.last_sync_at) {
      const d = new Date(s.last_sync_at);
      el.textContent = `Last sync: ${d.toLocaleString()} · ${s.total} total`;
    } else {
      el.textContent = 'Last sync: never';
    }
    const pendEl = document.getElementById('pendingCount');
    pendEl.textContent = s.pending > 0 ? `${s.pending} pending` : '';

    if (s.sync_running) {
      document.getElementById('syncBtn').disabled = true;
      document.getElementById('syncBtn').textContent = '⟳ Syncing…';
      pollSyncStatus();
    }
  } catch (_) {}
}

function pollSyncStatus() {
  if (syncPollInterval) return;
  syncPollInterval = setInterval(async () => {
    try {
      const r = await fetch('/api/email/status');
      const s = await r.json();
      if (!s.sync_running) {
        clearInterval(syncPollInterval);
        syncPollInterval = null;
        document.getElementById('syncBtn').disabled = false;
        document.getElementById('syncBtn').textContent = '↻ Sync';
        await loadMessages();
        await loadStatus();
        showToast('Sync complete');
      }
    } catch (_) {}
  }, 2500);
}

async function loadAccounts() {
  try {
    const r = await fetch('/api/email/accounts');
    const accounts = await r.json();
    const sel = document.getElementById('accountFilter');
    sel.innerHTML = '<option value="">All accounts</option>' +
      accounts.map(a => `<option value="${a.id}">${esc(a.label)}</option>`).join('');
  } catch (_) {}
}


function setFilter(val) {
  activeFilter = val;
  currentPage = 1;
  document.querySelectorAll('#filterPills .filter-pill').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === val);
  });
  render();
}

function updatePillCounts() {
  const counts = {};
  for (const m of messages) {
    counts[m.relevance] = (counts[m.relevance] || 0) + 1;
  }
  document.querySelectorAll('#filterPills .filter-pill').forEach(btn => {
    const f = btn.dataset.filter;
    const n = f === '' ? messages.length : (counts[f] || 0);
    const existing = btn.querySelector('.pill-count');
    if (existing) existing.remove();
    if (n > 0) {
      const span = document.createElement('span');
      span.className = 'pill-count';
      span.textContent = n;
      btn.appendChild(span);
    }
  });
}

function filtered() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  return messages.filter(m => {
    if (activeFilter && m.relevance !== activeFilter) return false;
    if (q) {
      const inSubject = (m.subject || '').toLowerCase().includes(q);
      const inSender  = (m.sender  || '').toLowerCase().includes(q);
      if (!inSubject && !inSender) return false;
    }
    return true;
  });
}

function render() {
  updatePillCounts();
  const list = filtered();
  const container = document.getElementById('messagesList');

  if (list.length === 0) {
    container.innerHTML = `<div class="empty-state">${
      messages.length > 0
        ? 'No messages match your filters.'
        : 'No messages synced yet. Add an email account and click Sync.'
    }</div>`;
    return;
  }

  currentPage = clampPage(currentPage, list.length, pageSize);
  const start = (currentPage - 1) * pageSize;
  const pageItems = list.slice(start, start + pageSize);

  container.innerHTML = pageItems.map(m => {
    const isExpanded = m.id === expandedId;
    const isProcessing = processingIds.has(m.id);
    const dot = `<div class="relevance-dot dot-${m.relevance}"></div>`;

    let badge = '';
    if (m.relevance === 'pending')    badge = '<span class="status-badge badge-pending">pending</span>';
    else if (m.relevance === 'irrelevant') badge = '<span class="status-badge badge-irrelevant">irrelevant</span>';
    else if (m.relevance === 'error') badge = '<span class="status-badge badge-error">error</span>';
    else if (m.llm_status) {
      const cls = STATUS_BADGE[m.llm_status] || 'badge-other';
      badge = `<span class="status-badge ${cls}">${STATUS_LABELS[m.llm_status] || esc(m.llm_status)}</span>`;
    }

    const linkedJob = allJobs.find(j => j.id === m.linked_job_id);
    const linkedBadge = linkedJob
      ? `<a href="/jobs/${linkedJob.id}" class="status-badge" style="background:#dcfce7;color:#15803d;text-decoration:none;font-size:11px;font-weight:700;padding:2px 8px;border-radius:10px;white-space:nowrap" title="Linked job">&#10003; ${esc(linkedJob.company)}</a>`
      : '';

    const isProcessed = m.relevance === 'relevant' || m.relevance === 'irrelevant';
    const processBtn = `<button class="btn btn-secondary btn-sm" onclick="processSingle(${m.id},event)"
           ${isProcessing ? 'disabled' : ''} title="${isProcessed ? 'Re-process with LLM' : 'Process with LLM'}">
           ${isProcessing
             ? '<span class="spinner">&#9696;</span>'
             : (isProcessed ? '&#8635;' : '&#9654;')} ${isProcessed ? 'Re-process' : 'Process'}
         </button>`;

    const date = m.received_at ? new Date(m.received_at).toLocaleDateString() : '';

    return `
      <div class="msg-row ${isExpanded ? 'expanded' : ''}" id="row-${m.id}">
        <div class="msg-summary" onclick="toggleExpand(${m.id})">
          ${dot}
          <div class="msg-meta">
            <div class="msg-subject">${esc(m.subject || '(no subject)')}</div>
            <div class="msg-from-date">${esc(m.sender)} &middot; ${date}</div>
          </div>
          <div class="msg-actions" onclick="event.stopPropagation()">
            ${linkedBadge}
            ${badge}
            ${processBtn}
            <button class="btn-icon" title="${isExpanded ? 'Collapse' : 'Expand'}" onclick="toggleExpand(${m.id})">
              ${isExpanded ? '&#8963;' : '&#8964;'}
            </button>
          </div>
        </div>
        ${isExpanded ? renderDetail(m) : ''}
      </div>`;
  }).join('') + renderPager(list.length, currentPage, pageSize, 'gotoPage');
}

function renderDetail(m) {
  let llmBlock = '';
  if (m.relevance === 'relevant' && m.llm_status) {
    let llmData = {};
    try { llmData = JSON.parse(m.llm_raw || '{}'); } catch (_) {}
    const conf = llmData.confidence != null ? llmData.confidence : null;
    const confBar = conf != null
      ? `<div class="confidence-bar"><div class="confidence-fill" style="width:${Math.round(conf*100)}%"></div></div> ${Math.round(conf*100)}%`
      : '';
    llmBlock = `<div class="detail-grid">
      ${llmData.company  ? `<div class="detail-field"><label>Company</label><span>${esc(llmData.company)}</span></div>` : ''}
      ${llmData.position ? `<div class="detail-field"><label>Position</label><span>${esc(llmData.position)}</span></div>` : ''}
      ${conf != null     ? `<div class="detail-field"><label>Confidence</label><span>${confBar}</span></div>` : ''}
      ${llmData.notes    ? `<div class="detail-field" style="grid-column:1/-1"><label>LLM Notes</label><span>${esc(llmData.notes)}</span></div>` : ''}
    </div>`;
  }

  const body = (m.body_text || '').slice(0, 800);
  const linkedJob = allJobs.find(j => j.id === m.linked_job_id);

  const jobOptions = allJobs.map(j =>
    `<option value="${j.id}" ${m.linked_job_id === j.id ? 'selected' : ''}>
      ${esc(j.position)} @ ${esc(j.company)}
    </option>`
  ).join('');

  const linkSection = `
    <div class="link-section">
      <div class="link-section-label">Linked job</div>
      ${linkedJob
        ? `<div class="linked-job-display">
             <a href="/jobs/${linkedJob.id}" class="linked-job-link">&#10003; ${esc(linkedJob.position)} at ${esc(linkedJob.company)}</a>
             <button class="btn btn-secondary btn-sm" onclick="unlinkEmail(${m.id})">Unlink</button>
           </div>`
        : `<div style="color:var(--empty-fg);font-size:12px;margin-bottom:6px">Not linked to any job</div>`
      }
      <div class="link-job-row" style="margin-top:${linkedJob ? '8px' : '0'}">
        <input class="link-job-search" type="text" placeholder="Search jobs…"
          id="jobSearch-${m.id}" oninput="filterJobSelect(${m.id})" style="max-width:200px">
        <select id="linkSel-${m.id}" size="1">
          <option value="">— Select job —</option>
          ${jobOptions}
        </select>
        <button class="btn btn-primary btn-sm" onclick="linkEmail(${m.id})">
          ${linkedJob ? 'Change' : 'Link'}
        </button>
      </div>
    </div>`;

  return `<div class="msg-detail">
    ${llmBlock}
    ${body ? `<div class="body-excerpt">${esc(body)}</div>` : ''}
    ${linkSection}
  </div>`;
}

function filterJobSelect(msgId) {
  const q = (document.getElementById(`jobSearch-${msgId}`)?.value || '').toLowerCase();
  const sel = document.getElementById(`linkSel-${msgId}`);
  if (!sel) return;
  sel.innerHTML = '<option value="">— Select job —</option>' +
    allJobs
      .filter(j => !q || `${j.position} ${j.company}`.toLowerCase().includes(q))
      .map(j => {
        const m = messages.find(x => x.id === expandedId);
        const selected = m && m.linked_job_id === j.id ? 'selected' : '';
        return `<option value="${j.id}" ${selected}>${esc(j.position)} @ ${esc(j.company)}</option>`;
      }).join('');
}

function toggleExpand(id) {
  expandedId = expandedId === id ? null : id;
  render();
}

async function syncNow() {
  const btn = document.getElementById('syncBtn');
  btn.disabled = true;
  btn.textContent = '⟳ Syncing…';
  try {
    const r = await fetch('/api/email/sync', { method: 'POST' });
    const data = await r.json();
    if (data.status === 'already_running') {
      showToast('Sync already in progress');
      btn.disabled = false;
      btn.textContent = '↻ Sync';
      return;
    }
    pollSyncStatus();
  } catch (e) {
    showToast('Sync failed: ' + e.message, true);
    btn.disabled = false;
    btn.textContent = '↻ Sync';
  }
}

async function processAll() {
  const btn = document.getElementById('processAllBtn');
  const progress = document.getElementById('processProgress');
  const progressText = document.getElementById('progressText');
  btn.disabled = true;
  progress.style.display = 'flex';
  progress.classList.remove('error');

  let processed = 0, errors = 0;

  try {
    const r = await fetch('/api/email/process', { method: 'POST' });
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      progress.classList.add('error');
      progressText.textContent = data.hint || data.error || 'Processing failed';
      progress.innerHTML = progressText.outerHTML;
      return;
    }

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const ev = JSON.parse(line);
          if (ev.error) {
            errors++;
            if (ev.error.toLowerCase().includes('ollama') || ev.error.toLowerCase().includes('not running')) {
              progress.classList.add('error');
              progressText.textContent = ev.error;
              await loadMessages(); await loadStatus();
              return;
            }
          } else {
            processed++;
            const subj = messages.find(x => x.id === ev.id)?.subject || `#${ev.id}`;
            progressText.textContent = `Processed ${processed}… "${subj.slice(0,50)}"`;
            const idx = messages.findIndex(x => x.id === ev.id);
            if (idx >= 0) {
              messages[idx] = { ...messages[idx], ...ev };
              if (ev.relevance) messages[idx].relevance = ev.relevance;
              if (ev.llm_status) messages[idx].llm_status = ev.llm_status;
              if (ev.linked_job_id) messages[idx].linked_job_id = ev.linked_job_id;
            }
            render();
          }
        } catch (_) {}
      }
    }

    progressText.textContent = `Done — ${processed} processed${errors ? `, ${errors} error(s)` : ''}`;
    await loadMessages(); await loadStatus(); await loadAllJobs();
    render();
  } catch (e) {
    progress.classList.add('error');
    progressText.textContent = 'Error: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

async function processSingle(msgId, e) {
  e.stopPropagation();
  processingIds.add(msgId);
  render();
  try {
    const r = await fetch(`/api/email/messages/${msgId}/process`, { method: 'POST' });
    const data = await r.json();
    if (!r.ok) {
      showToast(data.hint || data.error || 'Process failed', true);
    } else {
      const idx = messages.findIndex(x => x.id === msgId);
      if (idx >= 0) {
        messages[idx] = { ...messages[idx], ...data };
        if (data.relevance)     messages[idx].relevance     = data.relevance;
        if (data.llm_status)    messages[idx].llm_status    = data.llm_status;
        if (data.linked_job_id) messages[idx].linked_job_id = data.linked_job_id;
        try {
          const llmRaw = { company: data.company, position: data.position, confidence: data.confidence, notes: data.notes };
          messages[idx].llm_raw = JSON.stringify(llmRaw);
        } catch (_) {}
      }
      expandedId = msgId;
      await loadAllJobs();
      await loadStatus();
      await loadMessages();
      showToast(data.relevance === 'relevant'
        ? `Relevant — ${STATUS_LABELS[data.llm_status] || data.llm_status || 'classified'}`
        : 'Not relevant to job applications');
    }
  } catch (err) {
    showToast('Error: ' + err.message, true);
  } finally {
    processingIds.delete(msgId);
    render();
  }
}

async function linkEmail(msgId) {
  const sel = document.getElementById(`linkSel-${msgId}`);
  if (!sel || !sel.value) { showToast('Select a job first', true); return; }
  const r = await fetch(`/api/email/messages/${msgId}/link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: parseInt(sel.value) }),
  });
  if (r.ok) {
    const idx = messages.findIndex(x => x.id === msgId);
    if (idx >= 0) messages[idx].linked_job_id = parseInt(sel.value);
    showToast('Linked to job');
    render();
  } else {
    showToast('Link failed', true);
  }
}

async function unlinkEmail(msgId) {
  const r = await fetch(`/api/email/messages/${msgId}/link`, { method: 'DELETE' });
  if (r.ok || r.status === 204) {
    const idx = messages.findIndex(x => x.id === msgId);
    if (idx >= 0) messages[idx].linked_job_id = null;
    showToast('Unlinked');
    render();
  } else {
    showToast('Unlink failed', true);
  }
}

async function openAccountsDialog() {
  await renderAccounts();
  document.getElementById('accountsDialog').showModal();
}

async function renderAccounts() {
  const r = await fetch('/api/email/accounts');
  const accounts = await r.json();
  const container = document.getElementById('accountsList');
  if (accounts.length === 0) {
    container.innerHTML = '<div style="color:var(--empty-fg);font-size:13px;padding:8px 0">No accounts configured.</div>';
    return;
  }
  container.innerHTML = accounts.map(a => `
    <div class="account-item">
      <div class="account-info">
        <div class="account-label">${esc(a.label)}</div>
        <div class="account-detail">${esc(a.username)} &middot; ${esc(a.imap_host)}:${a.imap_port}</div>
        ${a.last_sync_at ? `<div class="account-detail">Last sync: ${new Date(a.last_sync_at).toLocaleString()}</div>` : ''}
      </div>
      <span class="account-status ${a.active ? 'status-active' : 'status-inactive'}">${a.active ? 'Active' : 'Inactive'}</span>
      <button class="btn btn-secondary btn-sm" title="Clear sync history — next sync will fetch all emails" onclick="resetAccountSync(${a.id})">Full re-sync</button>
      <button class="btn-icon" title="Delete" onclick="deleteAccount(${a.id})">&#128465;</button>
    </div>`).join('');
}

function toggleAddAccountForm() {
  const form = document.getElementById('addAccountForm');
  const visible = form.style.display !== 'none';
  form.style.display = visible ? 'none' : 'block';
  if (!visible) {
    ['acc-label','acc-host','acc-username','acc-password'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('acc-port').value = '993';
    document.getElementById('addAccountError').style.display = 'none';
  }
}

async function saveAccount() {
  const errEl = document.getElementById('addAccountError');
  const btn = document.getElementById('saveAccountBtn');
  errEl.style.display = 'none';
  const label    = document.getElementById('acc-label').value.trim();
  const host     = document.getElementById('acc-host').value.trim();
  const port     = parseInt(document.getElementById('acc-port').value) || 993;
  const username = document.getElementById('acc-username').value.trim();
  const password = document.getElementById('acc-password').value;
  if (!label || !host || !username || !password) {
    errEl.textContent = 'All fields are required.';
    errEl.style.display = 'block';
    return;
  }
  btn.disabled = true;
  try {
    const r = await fetch('/api/email/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label, imap_host: host, imap_port: port, username, password }),
    });
    const data = await r.json();
    if (!r.ok) { errEl.textContent = data.detail || 'Failed'; errEl.style.display = 'block'; return; }
    toggleAddAccountForm();
    await renderAccounts();
    await loadAccounts();
    showToast('Account saved');
  } catch (e) {
    errEl.textContent = 'Error: ' + e.message;
    errEl.style.display = 'block';
  } finally {
    btn.disabled = false;
  }
}

async function resetAccountSync(accountId) {
  if (!confirm('Reset sync history for this account? The next sync will re-fetch all emails from the server.')) return;
  const r = await fetch(`/api/email/accounts/${accountId}/reset-sync`, { method: 'POST' });
  if (r.ok || r.status === 204) {
    showToast('Sync history cleared — click Sync to re-fetch all emails');
    await renderAccounts();
  } else {
    showToast('Reset failed', true);
  }
}

async function deleteAccount(accountId) {
  if (!confirm('Delete this email account? Synced messages will also be removed.')) return;
  const r = await fetch(`/api/email/accounts/${accountId}`, { method: 'DELETE' });
  if (r.ok || r.status === 204) {
    await renderAccounts();
    await loadAccounts();
    await loadMessages();
    showToast('Account removed');
  } else {
    showToast('Delete failed', true);
  }
}


init();
