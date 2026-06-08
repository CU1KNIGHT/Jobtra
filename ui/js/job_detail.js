const BASE = window.JOBTRA_BASE || '';
const JOB_ID = parseInt(location.pathname.split('/').pop(), 10);

let job = null;
let pendingFile = null;
let emailMessages = [];

const STATUS_LABELS = {
  open: 'Open', applied: 'Applied', interview_done: 'Interview done',
  rejected: 'Rejected', rejected_after_interview: 'Rejected after interview', accepted: 'Accepted',
};

const JOB_TYPE_LABELS = {
  'full-time': 'Full-time', 'part-time': 'Part-time', 'mini-job': 'Mini-job',
  contract: 'Contract', internship: 'Internship', freelance: 'Freelance',
};

const WORK_MODE_LABELS = { remote: 'Remote', hybrid: 'Hybrid', 'on-site': 'On-site' };

function fmt(n) {
  if (!n) return '—';
  const b = parseInt(n, 10);
  if (b < 1024) return `${b} B`;
  if (b < 1024*1024) return `${(b/1024).toFixed(1)} KB`;
  return `${(b/1024/1024).toFixed(1)} MB`;
}

function showToast(msg, ms = 2200) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), ms);
}

async function loadJob() {
  const res = await fetch(`${BASE}/api/jobs/${JOB_ID}`);
  if (!res.ok) { document.body.innerHTML = '<p style="padding:32px;color:#dc2626">Job not found.</p>'; return; }
  job = await res.json();
  renderJob();
}

function renderJob() {
  document.title = `${job.position} @ ${job.company}`;
  document.getElementById('hPosition').textContent = job.position;
  document.getElementById('hCompany').textContent = job.company;

  const pill = document.getElementById('hPill');
  pill.textContent = STATUS_LABELS[job.status] || job.status;
  pill.className = `pill pill-${job.status}`;

  document.getElementById('statusSelect').value = job.status;

  document.getElementById('iDate').textContent       = job.date_applied || '—';
  document.getElementById('iCity').textContent       = job.city || '—';
  document.getElementById('iAddress').textContent    = job.address || '—';
  document.getElementById('iHours').textContent      = job.hours_per_week || '—';
  document.getElementById('iJobType').textContent    = JOB_TYPE_LABELS[job.job_type] || job.job_type || '—';
  document.getElementById('iWorkMode').textContent   = WORK_MODE_LABELS[job.work_mode] || job.work_mode || '—';
  document.getElementById('iLanguages').textContent  = job.languages || '—';
  document.getElementById('iHrEmail').textContent    = job.hr_email || '—';
  document.getElementById('iHrPhone').textContent    = job.hr_phone || '—';
  document.getElementById('iDescription').textContent = job.description || '—';

  const contactEl = document.getElementById('iContact');
  const links = [];
  if (job.whatsapp) {
    const href = job.whatsapp.startsWith('http') ? job.whatsapp : `https://wa.me/${job.whatsapp.replace(/[^0-9]/g,'')}`;
    links.push(`<a href="${esc(href)}" target="_blank" rel="noopener" style="color:#15803d;font-weight:600">&#128383; WhatsApp</a>`);
  }
  if (job.telegram) {
    const href = job.telegram.startsWith('http') ? job.telegram : `https://t.me/${job.telegram.replace(/^@/,'')}`;
    links.push(`<a href="${esc(href)}" target="_blank" rel="noopener" style="color:#1d4ed8;font-weight:600">&#9992; Telegram</a>`);
  }
  contactEl.innerHTML = links.length ? links.join(' &nbsp; ') : '—';

  const srcEl = document.getElementById('iSourceUrl');
  if (job.source_url) {
    srcEl.innerHTML = `<a href="${esc(job.source_url)}" target="_blank" rel="noopener" style="color:#2563eb;word-break:break-all">${esc(job.source_url)}</a>`;
  } else {
    srcEl.textContent = '—';
  }

  const skillsEl = document.getElementById('iSkills');
  if (job.skills) {
    skillsEl.innerHTML = job.skills.split(',').filter(s => s.trim()).map(s =>
      `<span class="skill-tag">${esc(s.trim())}</span>`
    ).join('');
  } else {
    skillsEl.textContent = '—';
  }
}

async function changeStatus() {
  const newStatus = document.getElementById('statusSelect').value;
  const full = { ...job, status: newStatus };
  const res = await fetch(`${BASE}/api/jobs/${JOB_ID}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(full),
  });
  if (!res.ok) { showToast('Failed to update status'); return; }
  job = await res.json();
  const pill = document.getElementById('hPill');
  pill.textContent = STATUS_LABELS[job.status] || job.status;
  pill.className = `pill pill-${job.status}`;
  showToast('Status updated');
}

const EDIT_FIELDS = [
  'position', 'company', 'date_applied', 'city', 'address', 'hours_per_week',
  'job_type', 'work_mode', 'languages', 'hr_email', 'hr_phone',
  'whatsapp', 'telegram', 'source_url', 'skills', 'description',
];

function enterEditMode() {
  EDIT_FIELDS.forEach(f => {
    document.getElementById(`e-${f}`).value = job[f] || '';
  });
  document.getElementById('editError').textContent = '';
  document.getElementById('infoGrid').style.display = 'none';
  document.getElementById('editGrid').style.display = 'grid';
  document.getElementById('editBtn').style.display = 'none';
}

function cancelEdit() {
  document.getElementById('editGrid').style.display = 'none';
  document.getElementById('infoGrid').style.display = 'grid';
  document.getElementById('editBtn').style.display = '';
}

async function saveEdit(e) {
  e.preventDefault();
  const errEl = document.getElementById('editError');
  errEl.textContent = '';

  const payload = { ...job };
  EDIT_FIELDS.forEach(f => {
    payload[f] = document.getElementById(`e-${f}`).value.trim();
  });

  let res;
  try {
    res = await fetch(`${BASE}/api/jobs/${JOB_ID}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    errEl.textContent = 'Network error: ' + err.message;
    return;
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    errEl.textContent = Array.isArray(detail)
      ? detail.map(d => d.msg).join('; ')
      : (detail || 'Failed to save');
    return;
  }

  job = await res.json();
  renderJob();
  cancelEdit();
  showToast('Job updated');
}

async function loadEmails() {
  const res = await fetch(`${BASE}/api/email/messages?job_id=${JOB_ID}`);
  const msgs = res.ok ? await res.json() : [];
  emailMessages = msgs;
  const section = document.getElementById('emailSection');
  const countEl = document.getElementById('emailCount');

  if (msgs.length === 0) {
    countEl.textContent = '';
    section.innerHTML = '<div class="empty-msg">No emails linked to this job yet.</div>';
    return;
  }

  countEl.textContent = `(${msgs.length})`;

  const rows = msgs.map(m => {
    const preview = (m.body_text || '').slice(0, 120).replace(/\s+/g, ' ');
    const isOutgoing = m.direction === 'outgoing';
    const who = isOutgoing ? `To: ${esc(m.sender)}` : esc(m.sender);
    const status = m.llm_status ? `<span class="pill pill-${m.llm_status}" style="font-size:11px;padding:1px 8px">${esc(m.llm_status)}</span>` : '';
    const statusCell = isOutgoing
      ? '<span class="email-tag-sent">↗ Sent</span>'
      : `<span class="relevance-${m.relevance}">${m.relevance}</span>${status ? ' ' + status : ''}`;
    return `<tr>
      <td>
        <div class="email-subject email-open" onclick="openEmail(${m.id})" title="Open email">${esc(m.subject) || '(no subject)'}</div>
        <div class="email-sender">${who}</div>
        ${preview ? `<div class="email-preview">${esc(preview)}…</div>` : ''}
      </td>
      <td style="white-space:nowrap">${(m.received_at || '').slice(0,10)}</td>
      <td>${statusCell}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-secondary btn-sm" onclick="openEmail(${m.id})">Open</button>
        <button class="btn btn-secondary btn-sm" onclick="unlinkEmail(${m.id})">Unlink</button>
      </td>
    </tr>`;
  }).join('');

  section.innerHTML = `<table>
    <thead><tr>
      <th>Email</th><th>Date</th><th>Status</th><th></th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

async function unlinkEmail(msgId) {
  const res = await fetch(`${BASE}/api/email/messages/${msgId}/link`, { method: 'DELETE' });
  if (!res.ok) { showToast('Failed to unlink email'); return; }
  showToast('Email unlinked');
  loadEmails();
}

function openEmail(msgId) {
  const m = emailMessages.find(x => x.id === msgId);
  if (!m) return;
  const date = m.received_at ? new Date(m.received_at).toLocaleString() : '—';
  document.getElementById('emailDialogSubject').textContent = m.subject || '(no subject)';
  document.getElementById('emailDialogFromLabel').textContent = m.direction === 'outgoing' ? 'To' : 'From';
  document.getElementById('emailDialogFrom').textContent = m.sender || '—';
  document.getElementById('emailDialogDate').textContent = date;
  document.getElementById('emailDialogBody').textContent = m.body_text || '(no content)';
  document.getElementById('emailDialog').showModal();
}

function closeEmail() {
  document.getElementById('emailDialog').close();
}

async function loadDocuments() {
  const res = await fetch(`${BASE}/api/jobs/${JOB_ID}/documents`);
  const docs = res.ok ? await res.json() : [];
  const list = document.getElementById('docList');
  const countEl = document.getElementById('docsCount');

  if (docs.length === 0) {
    countEl.textContent = '';
    list.innerHTML = '<div class="empty-msg">No files attached yet.</div>';
    return;
  }

  countEl.textContent = `(${docs.length})`;

  const DOC_ICONS = { cv: '📄', cover_letter: '✉️', portfolio: '🗂️', certificate: '🏅', other: '📎' };

  list.innerHTML = docs.map(d => {
    const icon = DOC_ICONS[d.doc_type] || '📎';
    const downloadUrl = `${BASE}/api/documents/${d.id}/download`;
    return `<div class="doc-item">
      <div class="doc-icon">${icon}</div>
      <div class="doc-info">
        <div class="doc-name">
          <a href="${downloadUrl}" style="color:var(--fg);text-decoration:none" download="${esc(d.filename)}">${esc(d.filename)}</a>
        </div>
        <div class="doc-meta">${fmt(d.file_size)} &nbsp;·&nbsp; ${(d.attached_at || d.uploaded_at || '').slice(0,10)}${d.notes ? ' &nbsp;·&nbsp; ' + esc(d.notes) : ''}</div>
      </div>
      <span class="doc-type-badge">${esc(d.doc_type)}</span>
      <button class="btn btn-danger btn-sm" onclick="detachDoc(${d.id})" title="Detach">&#215;</button>
    </div>`;
  }).join('');
}

async function detachDoc(docId) {
  const res = await fetch(`${BASE}/api/jobs/${JOB_ID}/documents/${docId}`, { method: 'DELETE' });
  if (!res.ok) { showToast('Failed to detach file'); return; }
  showToast('File detached');
  loadDocuments();
}

function onDragOver(e) { e.preventDefault(); document.getElementById('uploadZone').classList.add('drag-over'); }
function onDragLeave(e) { document.getElementById('uploadZone').classList.remove('drag-over'); }
function onDrop(e) {
  e.preventDefault();
  document.getElementById('uploadZone').classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) setUploadFile(file);
}
function handleFileSelect(e) {
  const file = e.target.files[0];
  if (file) setUploadFile(file);
}
function setUploadFile(file) {
  pendingFile = file;
  document.getElementById('uploadFileName').textContent = file.name;
  document.getElementById('uploadControls').style.display = 'flex';
  document.getElementById('uploadError').style.display = 'none';
}
function cancelUpload() {
  pendingFile = null;
  document.getElementById('fileInput').value = '';
  document.getElementById('uploadControls').style.display = 'none';
  document.getElementById('uploadError').style.display = 'none';
}

async function uploadFile() {
  if (!pendingFile) return;
  const formData = new FormData();
  formData.append('file', pendingFile);
  formData.append('doc_type', document.getElementById('uploadDocType').value);
  formData.append('notes', document.getElementById('uploadNotes').value);

  const errEl = document.getElementById('uploadError');
  errEl.style.display = 'none';

  const res = await fetch(`${BASE}/api/jobs/${JOB_ID}/documents`, { method: 'POST', body: formData });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    errEl.textContent = err.detail || 'Upload failed';
    errEl.style.display = 'block';
    return;
  }
  showToast('File uploaded');
  cancelUpload();
  loadDocuments();
}

async function init() {
  await loadJob();
  loadEmails();
  loadDocuments();
}

init();
