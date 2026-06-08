let jobs = [];
let docCounts = {};
let editingId = null;
let expandedId = null;
let pendingSource = { source_url: '', source_text: '' };
let docFilter = null;  // { ids:Set<int>, name:string } when filtering by a document
let pageSize = 25;     // items per page, from settings
let currentPage = 1;

const STATUS_LABELS = {
  open: 'Open',
  applied: 'Applied',
  interview_done: 'Interview done',
  rejected: 'Rejected',
  rejected_after_interview: 'Rejected after interview',
  accepted: 'Accepted',
};

async function loadPageSize() {
  try {
    const r = await fetch('/api/settings');
    const s = await r.json();
    if (s.page_size) pageSize = s.page_size;
  } catch (_) {}
}

async function fetchJobs() {
  const res = await fetch('/api/jobs');
  jobs = await res.json();
  docCounts = {};
  for (const j of jobs) {
    if (j.doc_count > 0) docCounts[j.id] = j.doc_count;
  }
  render();
}

function filtered() {
  const q = document.getElementById('search').value.toLowerCase();
  const s = document.getElementById('statusFilter').value;
  return jobs.filter(j => {
    const matchStatus = !s || j.status === s;
    const matchText = !q || [j.position, j.company, j.city, j.skills].some(f => (f || '').toLowerCase().includes(q));
    const matchDoc = !docFilter || docFilter.ids.has(j.id);
    return matchStatus && matchText && matchDoc;
  });
}

async function applyDocFilterFromUrl() {
  const docId = parseInt(new URLSearchParams(location.search).get('document'), 10);
  if (!docId) return;
  try {
    const r = await fetch(`/api/documents/${docId}/jobs`);
    if (!r.ok) return;
    const data = await r.json();
    docFilter = {
      ids: new Set((data.jobs || []).map(j => j.id)),
      name: (data.document && data.document.filename) || 'document',
    };
  } catch (_) {}
}

function renderDocFilterBanner() {
  const el = document.getElementById('docFilterBanner');
  if (!el) return;
  if (!docFilter) { el.style.display = 'none'; el.innerHTML = ''; return; }
  el.style.display = 'block';
  el.innerHTML = `Showing ${docFilter.ids.size} job(s) that use ` +
    `<strong>${esc(docFilter.name)}</strong> · <a href="/jobs">Show all</a>`;
}

function pill(status) {
  return `<span class="pill pill-${status}">${STATUS_LABELS[status] || status}</span>`;
}

function skillTags(skills) {
  if (!skills) return '';
  return skills.split(',').filter(s => s.trim()).map(s =>
    `<span class="skill-tag">${s.trim()}</span>`
  ).join('');
}

function render() {
  const list = filtered();
  const container = document.getElementById('tableContainer');

  if (list.length === 0) {
    container.innerHTML = `<div class="empty-state">${
      jobs.length === 0
        ? 'No applications yet. Click <strong>+ Add job</strong> to start.'
        : 'No jobs match your filters.'
    }</div>`;
    return;
  }

  currentPage = clampPage(currentPage, list.length, pageSize);
  const start = (currentPage - 1) * pageSize;
  const pageItems = list.slice(start, start + pageSize);

  const rows = pageItems.map(j => {
    const isExpanded = j.id === expandedId;
    const mainRow = `
      <tr class="${isExpanded ? 'expanded' : ''}" onclick="toggleExpand(${j.id}, event)">
        <td>${j.date_applied}</td>
        <td>${esc(j.position)}</td>
        <td>${esc(j.company)}</td>
        <td class="col-city">${esc(j.city)}</td>
        <td>${pill(j.status)}</td>
        <td class="col-actions actions" onclick="event.stopPropagation()">
          ${docCounts[j.id] ? `<a class="doc-badge" href="/documents?job=${j.id}" title="${docCounts[j.id]} document(s) attached">&#128196; ${docCounts[j.id]}</a>` : ''}
          <a class="btn-icon" href="/jobs/${j.id}" title="View details" style="text-decoration:none">&#128269;</a>
          <button class="btn-icon" title="Edit" onclick="openEditDialog(${j.id})">&#9998;</button>
          <button class="btn-icon" title="Delete" onclick="deleteJob(${j.id})">&#128465;</button>
        </td>
      </tr>`;

    if (!isExpanded) return mainRow;

    const hasSource = j.source_url || j.source_text;
    const reparseBtn = hasSource
      ? `<button class="reparse-btn" id="reparseBtn-${j.id}" onclick="reparseJob(${j.id})">&#8634; Re-parse</button><div id="reparseError-${j.id}" class="reparse-inline-error" style="display:none"></div>`
      : '';

    const waLink = waHref(j.whatsapp);
    const tgLink = tgHref(j.telegram);
    const contactIcons = (waLink ? `<a class="contact-icon contact-icon-wa" href="${waLink}" target="_blank" rel="noopener">&#128383; WhatsApp</a>` : '')
                       + (tgLink ? `<a class="contact-icon contact-icon-tg" href="${tgLink}" target="_blank" rel="noopener">&#9992; Telegram</a>` : '');

    const detailRow = `
      <tr class="detail-row">
        <td colspan="6">
          <div class="detail-inner">
            <div class="field" style="grid-column:1/-1"><label>Description</label><span style="white-space:pre-wrap">${esc(j.description) || '—'}</span></div>
            <div class="field"><label>Address</label><span>${esc(j.address) || '—'}</span></div>
            <div class="field"><label>City</label><span>${esc(j.city) || '—'}</span></div>
            <div class="field"><label>Hours / week</label><span>${esc(j.hours_per_week) || '—'}</span></div>
            <div class="field"><label>Languages</label><span>${esc(j.languages) || '—'}</span></div>
            <div class="field"><label>HR Email</label><span>${esc(j.hr_email) || '—'}</span></div>
            <div class="field"><label>HR Phone</label><span>${esc(j.hr_phone) || '—'}</span></div>
            ${(j.whatsapp || j.telegram) ? `<div class="field"><label>Contact via</label><span>${contactIcons}</span></div>` : ''}
            <div class="field"><label>Skills</label><div class="skills-list">${skillTags(j.skills) || '—'}</div></div>
            <div class="field"><label>Created</label><span>${j.created_at}</span></div>
            <div class="field"><label>Updated</label><span>${j.updated_at}</span></div>
            ${hasSource ? `<div class="field"><label>Source URL</label><span>${j.source_url ? `<a href="${esc(j.source_url)}" target="_blank" rel="noopener" style="color:#2563eb;word-break:break-all">${esc(j.source_url)}</a>` : '—'}</span></div>` : ''}
            ${hasSource ? `<div class="field" style="align-self:end">${reparseBtn}</div>` : ''}
          </div>
        </td>
      </tr>`;

    return mainRow + detailRow;
  }).join('');

  container.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Date applied</th>
          <th>Position</th>
          <th>Company</th>
          <th class="col-city col-actions-header">City</th>
          <th>Status</th>
          <th class="col-actions-header">Actions</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>` + renderPager(list.length, currentPage, pageSize, 'gotoPage');
}

function gotoPage(n) {
  currentPage = n;
  render();
  document.getElementById('tableContainer')?.scrollIntoView({ block: 'start' });
}

// Filter/search changed — jump back to the first page so results aren't hidden.
function onFilterChange() {
  currentPage = 1;
  render();
}

function toggleExpand(id, e) {
  expandedId = expandedId === id ? null : id;
  render();
}

function waHref(val) {
  if (!val) return '';
  val = val.trim();
  if (val.startsWith('http')) return val;
  const digits = val.replace(/\D/g, '');
  return digits ? `https://wa.me/${digits}` : '';
}

function tgHref(val) {
  if (!val) return '';
  val = val.trim();
  if (val.startsWith('http')) return val;
  const handle = val.startsWith('@') ? val.slice(1) : val;
  return handle ? `https://t.me/${handle}` : '';
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function openAddDialog() {
  editingId = null;
  pendingSource = { source_url: '', source_text: '' };
  document.getElementById('dialogTitle').textContent = 'Add Job';
  document.getElementById('f-position').value = '';
  document.getElementById('f-company').value = '';
  document.getElementById('f-date_applied').value = today();
  document.getElementById('f-status').value = 'open';
  document.getElementById('f-description').value = '';
  document.getElementById('f-address').value = '';
  document.getElementById('f-city').value = '';
  document.getElementById('f-hr_email').value = '';
  document.getElementById('f-hr_phone').value = '';
  document.getElementById('f-whatsapp').value = '';
  document.getElementById('f-telegram').value = '';
  document.getElementById('f-hours_per_week').value = '';
  document.getElementById('f-job_type').value = '';
  document.getElementById('f-work_mode').value = '';
  document.getElementById('f-languages').value = '';
  document.getElementById('f-skills').value = '';
  hideError();
  document.getElementById('jobDialog').showModal();
}

function openEditDialog(id) {
  const j = jobs.find(x => x.id === id);
  if (!j) return;
  editingId = id;
  pendingSource = { source_url: j.source_url || '', source_text: j.source_text || '' };
  document.getElementById('dialogTitle').textContent = 'Edit Job';
  document.getElementById('f-position').value = j.position;
  document.getElementById('f-company').value = j.company;
  document.getElementById('f-date_applied').value = j.date_applied;
  document.getElementById('f-status').value = j.status;
  document.getElementById('f-description').value = j.description;
  document.getElementById('f-address').value = j.address;
  document.getElementById('f-city').value = j.city;
  document.getElementById('f-hr_email').value = j.hr_email;
  document.getElementById('f-hr_phone').value = j.hr_phone;
  document.getElementById('f-whatsapp').value = j.whatsapp || '';
  document.getElementById('f-telegram').value = j.telegram || '';
  document.getElementById('f-hours_per_week').value = j.hours_per_week || '';
  document.getElementById('f-job_type').value = j.job_type || '';
  document.getElementById('f-work_mode').value = j.work_mode || '';
  document.getElementById('f-languages').value = j.languages || '';
  document.getElementById('f-skills').value = j.skills;
  hideError();
  document.getElementById('jobDialog').showModal();
}

function closeDialog() {
  document.getElementById('jobDialog').close();
}

function hideError() {
  const el = document.getElementById('dialogError');
  el.style.display = 'none';
  el.textContent = '';
}

function showError(msg) {
  const el = document.getElementById('dialogError');
  el.textContent = msg;
  el.style.display = 'block';
}

async function saveJob() {
  hideError();
  const payload = {
    position: document.getElementById('f-position').value.trim(),
    company: document.getElementById('f-company').value.trim(),
    date_applied: document.getElementById('f-date_applied').value,
    status: document.getElementById('f-status').value,
    description: document.getElementById('f-description').value.trim(),
    address: document.getElementById('f-address').value.trim(),
    city: document.getElementById('f-city').value.trim(),
    hr_email: document.getElementById('f-hr_email').value.trim(),
    hr_phone: document.getElementById('f-hr_phone').value.trim(),
    whatsapp: document.getElementById('f-whatsapp').value.trim(),
    telegram: document.getElementById('f-telegram').value.trim(),
    hours_per_week: document.getElementById('f-hours_per_week').value.trim(),
    job_type: document.getElementById('f-job_type').value,
    work_mode: document.getElementById('f-work_mode').value,
    languages: document.getElementById('f-languages').value.trim(),
    skills: document.getElementById('f-skills').value.trim(),
    source_url: pendingSource.source_url,
    source_text: pendingSource.source_text,
  };

  const url = editingId ? `/api/jobs/${editingId}` : '/api/jobs';
  const method = editingId ? 'PUT' : 'POST';

  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json();
      const detail = err.detail;
      const msg = Array.isArray(detail)
        ? detail.map(d => d.msg).join('; ')
        : (detail || 'Unknown error');
      showError(msg);
      return;
    }
  } catch (e) {
    showError('Network error: ' + e.message);
    return;
  }

  closeDialog();
  await fetchJobs();
}

async function deleteJob(id) {
  if (!confirm('Delete this application?')) return;
  await fetch(`/api/jobs/${id}`, { method: 'DELETE' });
  if (expandedId === id) expandedId = null;
  await fetchJobs();
}

function exportCSV() {
  const list = filtered();
  const headers = ['id','position','company','date_applied','status','city','address','hr_email','hr_phone','skills','description','created_at','updated_at'];
  const escape = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const lines = [headers.join(','), ...list.map(j => headers.map(h => escape(j[h])).join(','))];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `job-applications-${today()}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function openImportDialog() {
  document.getElementById('importFile').value = '';
  const err = document.getElementById('importError');
  err.style.display = 'none';
  err.textContent = '';
  const res = document.getElementById('importResult');
  res.style.display = 'none';
  res.textContent = '';
  res.classList.remove('error');
  document.getElementById('importBtn').disabled = false;
  document.getElementById('importDialog').showModal();
}

async function runImport() {
  const fileInput = document.getElementById('importFile');
  const err = document.getElementById('importError');
  const res = document.getElementById('importResult');
  const btn = document.getElementById('importBtn');
  err.style.display = 'none';

  if (!fileInput.files.length) {
    err.textContent = 'Please choose a CSV or JSON file.';
    err.style.display = 'block';
    return;
  }

  const fd = new FormData();
  fd.append('file', fileInput.files[0]);
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = 'Importing…';

  try {
    const r = await fetch('/api/jobs/import', { method: 'POST', body: fd });
    const data = await r.json();
    if (!r.ok) {
      err.textContent = data.detail || 'Import failed';
      err.style.display = 'block';
      return;
    }
    let msg = `Imported ${data.imported} of ${data.total} row(s).`;
    if (data.skipped) msg += ` Skipped ${data.skipped} duplicate(s).`;
    if (data.errors && data.errors.length) {
      msg += `\n\n${data.errors.length} row(s) skipped with errors:\n` +
        data.errors.slice(0, 20).map(e => `  row ${e.row}: ${e.error}`).join('\n');
      if (data.errors.length > 20) msg += `\n  …and ${data.errors.length - 20} more`;
      res.classList.add('error');
    } else {
      res.classList.remove('error');
    }
    res.textContent = msg;
    res.style.display = 'block';
    await fetchJobs();
  } catch (e) {
    err.textContent = 'Network error: ' + e.message;
    err.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

let parseTab = 'url';

function switchParseTab(tab) {
  parseTab = tab;
  document.getElementById('parseUrlPanel').style.display = tab === 'url' ? '' : 'none';
  document.getElementById('parseTextPanel').style.display = tab === 'text' ? '' : 'none';
  document.getElementById('tabUrl').className = 'parse-tab' + (tab === 'url' ? ' parse-tab-active' : '');
  document.getElementById('tabText').className = 'parse-tab' + (tab === 'text' ? ' parse-tab-active' : '');
  document.getElementById('parseBtn').textContent = tab === 'url' ? 'Fetch & parse' : 'Parse';
}

async function openParseDialog() {
  document.getElementById('parseUrl').value = '';
  document.getElementById('parseText').value = '';
  const err = document.getElementById('parseError');
  err.style.display = 'none';
  err.textContent = '';
  const btn = document.getElementById('parseBtn');
  btn.disabled = false;
  switchParseTab('url');

  const info = document.getElementById('parseProviderInfo');
  info.textContent = 'Loading provider…';
  try {
    const res = await fetch('/api/settings');
    const s = await res.json();
    const providerLabel = { ollama: 'Ollama', lmstudio: 'LM Studio', anthropic: 'Anthropic', openai: 'OpenAI' }[s.provider] || s.provider;
    info.innerHTML = `Using: <strong>${providerLabel} / ${esc(s.model)}</strong> &nbsp;<a href="#" style="color:#2563eb;font-size:12px" onclick="document.getElementById('parseDialog').close();openSettingsDialog();return false">Change…</a>`;
  } catch (_) {
    info.textContent = '';
  }

  document.getElementById('parseDialog').showModal();
}

async function runParse() {
  const err = document.getElementById('parseError');
  err.style.display = 'none';
  err.textContent = '';
  const btn = document.getElementById('parseBtn');

  let body;
  if (parseTab === 'url') {
    const url = document.getElementById('parseUrl').value.trim();
    if (!url) { err.textContent = 'Please enter a URL first.'; err.style.display = 'block'; return; }
    body = { url };
  } else {
    const text = document.getElementById('parseText').value.trim();
    if (!text) { err.textContent = 'Please paste a job posting first.'; err.style.display = 'block'; return; }
    body = { text };
  }

  btn.disabled = true;
  btn.textContent = 'Working…';

  try {
    const res = await fetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      err.textContent = data.error + (data.hint ? ' — ' + data.hint : '');
      err.style.display = 'block';
      btn.disabled = false;
      btn.textContent = parseTab === 'url' ? 'Fetch & parse' : 'Parse';
      if (parseTab === 'url' && data.hint && data.hint.includes('copy-pasting')) switchParseTab('text');
      return;
    }
    document.getElementById('parseDialog').close();
    openAddDialogPrefilled(data);
  } catch (e) {
    err.textContent = 'Network error: ' + e.message;
    err.style.display = 'block';
    btn.disabled = false;
    btn.textContent = parseTab === 'url' ? 'Fetch & parse' : 'Parse';
  }
}

async function reparseJob(id) {
  if (!confirm('Re-parse this job? Description and contact fields may change. Status and date will be kept.')) return;

  const btn = document.getElementById(`reparseBtn-${id}`);
  const errEl = document.getElementById(`reparseError-${id}`);
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  if (errEl) errEl.style.display = 'none';

  try {
    const res = await fetch(`/api/jobs/${id}/reparse`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) {
      const msg = data.detail || data.error || 'Re-parse failed';
      if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
      if (btn) { btn.disabled = false; btn.textContent = '↻ Re-parse'; }
      return;
    }
    await fetchJobs();
    const newBtn = document.getElementById(`reparseBtn-${id}`);
    if (newBtn) {
      newBtn.textContent = 'Updated ✓';
      setTimeout(() => { if (newBtn) newBtn.textContent = '↻ Re-parse'; }, 2000);
    }
  } catch (e) {
    if (errEl) { errEl.textContent = 'Network error: ' + e.message; errEl.style.display = 'block'; }
    if (btn) { btn.disabled = false; btn.textContent = '↻ Re-parse'; }
  }
}

function openAddDialogPrefilled(data) {
  editingId = null;
  pendingSource = { source_url: data.source_url || '', source_text: data.source_text || '' };
  document.getElementById('dialogTitle').textContent = 'Add Job';
  document.getElementById('f-position').value = data.position || '';
  document.getElementById('f-company').value = data.company || '';
  document.getElementById('f-date_applied').value = data.date_applied || today();
  document.getElementById('f-status').value = data.status || 'open';
  document.getElementById('f-description').value = data.description || '';
  document.getElementById('f-address').value = data.address || '';
  document.getElementById('f-city').value = data.city || '';
  document.getElementById('f-hr_email').value = data.hr_email || '';
  document.getElementById('f-hr_phone').value = data.hr_phone || '';
  document.getElementById('f-whatsapp').value = data.whatsapp || '';
  document.getElementById('f-telegram').value = data.telegram || '';
  document.getElementById('f-hours_per_week').value = data.hours_per_week || '';
  document.getElementById('f-job_type').value = data.job_type || '';
  document.getElementById('f-work_mode').value = data.work_mode || '';
  document.getElementById('f-languages').value = data.languages || '';
  document.getElementById('f-skills').value = data.skills || '';
  hideError();
  document.getElementById('jobDialog').showModal();
}

// ── Settings dialog ──────────────────────────────────────────────────────────
let settingsProvider = 'ollama';
let settingsModel = '';

const PROVIDER_LABELS = { ollama: 'Ollama', lmstudio: 'LM Studio', anthropic: 'Anthropic Claude', openai: 'OpenAI' };
const KEY_HINTS = { anthropic: 'ANTHROPIC_API_KEY', openai: 'OPENAI_API_KEY' };

async function openSettingsDialog() {
  document.getElementById('settingsProviderList').textContent = 'Loading…';
  document.getElementById('settingsModelSelect').innerHTML = '<option>Loading…</option>';
  document.getElementById('settingsTestResult').style.display = 'none';
  document.getElementById('settingsToast').style.display = 'none';
  document.getElementById('settingsDialog').showModal();

  const res = await fetch('/api/settings');
  const s = await res.json();
  settingsProvider = s.provider;
  settingsModel = s.model;
  renderSettingsProviders(s.providers, s.key_status);
  await loadSettingsModels(settingsProvider, settingsModel);
}

function renderSettingsProviders(providers, keyStatus) {
  const list = document.getElementById('settingsProviderList');
  list.innerHTML = providers.map(p => {
    const ks = keyStatus[p];
    let badge = '';
    if (ks === null) badge = '<span class="key-badge key-none">No key needed</span>';
    else if (ks)     badge = '<span class="key-badge key-ok">&#10003; Key configured</span>';
    else             badge = `<span class="key-badge key-miss">&#9888; Set ${KEY_HINTS[p]} in .env</span>`;
    const checked = p === settingsProvider ? 'checked' : '';
    return `<div class="provider-row">
      <input type="radio" name="settingsProvider" id="sp-${p}" value="${p}" ${checked} onchange="onSettingsProviderChange('${p}')">
      <label for="sp-${p}">${PROVIDER_LABELS[p] || p}</label>
      ${badge}
    </div>`;
  }).join('');
}

async function onSettingsProviderChange(provider) {
  settingsProvider = provider;
  await loadSettingsModels(provider, '');
}

async function loadSettingsModels(provider, selectedModel) {
  const sel = document.getElementById('settingsModelSelect');
  const txt = document.getElementById('settingsModelText');
  const err = document.getElementById('settingsModelError');
  sel.innerHTML = '<option disabled>Loading…</option>';
  sel.disabled = true;
  sel.style.display = '';
  txt.style.display = 'none';
  err.style.display = 'none';
  try {
    const res = await fetch(`/api/models?provider=${encodeURIComponent(provider)}`);
    const data = await res.json();
    if (!res.ok) throw new Error((data.error || 'Failed') + (data.hint ? ' — ' + data.hint : ''));
    const models = data.models || [];
    if (!models.length) throw new Error('No models found.');
    sel.innerHTML = models.map(m =>
      `<option value="${esc(m)}" ${m === selectedModel ? 'selected' : ''}>${esc(m)}</option>`
    ).join('');
    sel.disabled = false;
    settingsModel = models.includes(selectedModel) ? selectedModel : models[0];
  } catch (e) {
    sel.style.display = 'none';
    txt.style.display = '';
    txt.value = selectedModel || '';
    settingsModel = txt.value;
    err.textContent = e.message;
    err.style.display = 'block';
  }
}

function onSettingsModelInput() {
  const sel = document.getElementById('settingsModelSelect');
  const txt = document.getElementById('settingsModelText');
  settingsModel = txt.style.display !== 'none' ? txt.value.trim() : sel.value;
}

async function saveSettingsDialog() {
  onSettingsModelInput();
  if (!settingsModel) { alert('Please select or enter a model.'); return; }
  const res = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: settingsProvider, model: settingsModel }),
  });
  if (res.ok) {
    const toast = document.getElementById('settingsToast');
    toast.style.display = 'inline';
    setTimeout(() => { toast.style.display = 'none'; }, 2500);
  } else {
    const err = await res.json();
    alert('Error: ' + (err.detail || 'Could not save settings'));
  }
}

const TEST_POSTING = `Software Engineer – Backend\nCompany: Acme Corp\nLocation: Berlin, Germany\nAddress: Unter den Linden 10, 10117 Berlin\n\nWe are looking for a backend engineer.\n\nRequirements: Python, FastAPI, PostgreSQL, Docker\nContact: hr@acme.de | +49 30 12345678`;

async function testSettingsParse() {
  await saveSettingsDialog();
  const box = document.getElementById('settingsTestResult');
  box.className = 'test-result';
  box.style.display = 'block';
  box.textContent = 'Parsing sample posting…';
  try {
    const res = await fetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: TEST_POSTING }),
    });
    const data = await res.json();
    if (!res.ok) {
      box.className = 'test-result error';
      box.textContent = (data.error || 'Error') + (data.hint ? '\n' + data.hint : '');
    } else {
      box.textContent = JSON.stringify(data, null, 2);
    }
  } catch (e) {
    box.className = 'test-result error';
    box.textContent = 'Network error: ' + e.message;
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────
(async function init() {
  await loadPageSize();
  await applyDocFilterFromUrl();
  await fetchJobs();
  renderDocFilterBanner();
  const editId = parseInt(new URLSearchParams(location.search).get('edit'), 10);
  if (editId) openEditDialog(editId);
})();

// Bookmarklet — uses BASE_URL injected inline by the server
(function () {
  const base = window.JOBTRA_BASE || '';
  const code = "(async()=>{const t=document.body.innerText.slice(0,50000),u=location.href,d=document.createElement('div');d.style.cssText='position:fixed;bottom:20px;right:20px;z-index:999999;background:#222;color:#fff;padding:12px 16px;border-radius:6px;font:14px system-ui,sans-serif;box-shadow:0 4px 12px rgba(0,0,0,.3);max-width:320px;';d.textContent='Saving to tracker...';document.body.appendChild(d);try{const r=await fetch('" + base + "/api/parse-from-bookmarklet',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t,url:u})});const j=await r.json();if(!r.ok){d.textContent='✗ '+(j.error||'Save failed')+(j.hint?' ('+j.hint+')':'');d.style.background='#a00';setTimeout(()=>d.remove(),6000);}else{d.textContent='✓ Saved: '+j.position+' at '+j.company;d.style.background='#060';setTimeout(()=>d.remove(),3000);}}catch(e){d.textContent='✗ '+(e.message||'network error');d.style.background='#a00';setTimeout(()=>d.remove(),6000);}})();";
  const el = document.getElementById('settingsBmLink');
  if (el) el.href = 'javascript:' + encodeURIComponent(code);
})();
