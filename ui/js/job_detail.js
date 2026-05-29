const BASE = window.JOB_TRACKER_BASE || '';
const JOB_ID = parseInt(location.pathname.split('/').pop(), 10);

let job = null;
let pendingFile = null;

const STATUS_LABELS = {
  open: 'Open', applied: 'Applied', interview_done: 'Interview done',
  rejected: 'Rejected', rejected_after_interview: 'Rejected after interview', accepted: 'Accepted',
};

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

  document.title = `${job.position} @ ${job.company}`;
  document.getElementById('hPosition').textContent = job.position;
  document.getElementById('hCompany').textContent = job.company;

  const pill = document.getElementById('hPill');
  pill.textContent = STATUS_LABELS[job.status] || job.status;
  pill.className = `pill pill-${job.status}`;

  document.getElementById('statusSelect').value = job.status;
  document.getElementById('editLink').href = `/?edit=${JOB_ID}`;

  document.getElementById('iDate').textContent       = job.date_applied || '—';
  document.getElementById('iCity').textContent       = job.city || '—';
  document.getElementById('iAddress').textContent    = job.address || '—';
  document.getElementById('iHours').textContent      = job.hours_per_week || '—';
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

async function loadEmails() {
  const res = await fetch(`${BASE}/api/email/messages?job_id=${JOB_ID}`);
  const msgs = res.ok ? await res.json() : [];
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
    const relClass = `relevance-${m.relevance}`;
    const status = m.llm_status ? `<span class="pill pill-${m.llm_status}" style="font-size:11px;padding:1px 8px">${esc(m.llm_status)}</span>` : '';
    return `<tr>
      <td>
        <div class="email-subject">${esc(m.subject) || '(no subject)'}</div>
        <div class="email-sender">${esc(m.sender)}</div>
        ${preview ? `<div class="email-preview">${esc(preview)}…</div>` : ''}
      </td>
      <td style="white-space:nowrap">${(m.received_at || '').slice(0,10)}</td>
      <td><span class="${relClass}">${m.relevance}</span>${status ? ' ' + status : ''}</td>
      <td style="white-space:nowrap">
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
