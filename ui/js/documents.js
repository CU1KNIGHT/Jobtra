const params = new URLSearchParams(location.search);
const jobId = params.get('job') ? parseInt(params.get('job')) : null;

let allDocs = [];
let jobInfo = null;
let allLibraryDocs = [];

const DOC_TYPE_LABELS = {
  cv: 'CV', cover_letter: 'Cover Letter', certificate: 'Certificate',
  portfolio: 'Portfolio', other: 'Other',
};
const TYPE_BADGE_CLASS = {
  cv: 'badge-cv', cover_letter: 'badge-cover', certificate: 'badge-cert',
  portfolio: 'badge-portfolio', other: 'badge-other',
};

function fmtSize(bytes) {
  if (!bytes) return '—';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function showToast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (isError ? ' error' : '');
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 3000);
}

async function init() {
  if (jobId) {
    document.getElementById('jobContext').style.display = 'flex';
    document.getElementById('attachSection').style.display = 'block';
    try {
      const r = await fetch(`/api/jobs/${jobId}`);
      if (r.ok) {
        jobInfo = await r.json();
        document.getElementById('jobContextTitle').textContent =
          `${jobInfo.position} at ${jobInfo.company}`;
      }
    } catch (_) {}
    await loadLibraryForPicker();
  }
  await loadDocs();
}

async function loadDocs() {
  const url = jobId ? `/api/documents?job_id=${jobId}` : '/api/documents';
  const r = await fetch(url);
  allDocs = await r.json();
  render();
}

async function loadLibraryForPicker() {
  const r = await fetch('/api/documents');
  allLibraryDocs = await r.json();
  const sel = document.getElementById('libraryPicker');
  sel.innerHTML = '<option value="">— Select a document —</option>' +
    allLibraryDocs.map(d =>
      `<option value="${d.id}">${esc(d.filename)} (${DOC_TYPE_LABELS[d.doc_type] || d.doc_type})</option>`
    ).join('');
}

function filtered() {
  const q = document.getElementById('search').value.toLowerCase();
  const type = document.getElementById('typeFilter').value;
  return allDocs.filter(d => {
    const matchType = !type || d.doc_type === type;
    const matchQ = !q || (d.filename || '').toLowerCase().includes(q) ||
                        (d.notes || '').toLowerCase().includes(q);
    return matchType && matchQ;
  });
}

function render() {
  const docs = filtered();
  const content = document.getElementById('docsContent');
  if (docs.length === 0) {
    content.innerHTML = `<div class="empty-state">${
      allDocs.length === 0
        ? (jobId ? 'No documents attached to this job yet.' : 'No documents yet. Upload your first document.')
        : 'No documents match your filters.'
    }</div>`;
    return;
  }
  const isJobView = !!jobId;
  const rows = docs.map(d => {
    const badgeClass = TYPE_BADGE_CLASS[d.doc_type] || 'badge-other';
    const usageCount = d.usage_count || 0;
    const usageCell = isJobView
      ? `<span class="usage-zero">—</span>`
      : (usageCount > 0
        ? `<a class="usage-link" href="/jobs?document=${d.id}" title="Show jobs using this document">${usageCount} job${usageCount !== 1 ? 's' : ''}</a>`
        : `<span class="usage-zero">Unused</span>`);
    const deleteDisabled = !isJobView && usageCount > 0 ? 'disabled title="Detach from all jobs first"' : '';
    const actionBtns = isJobView
      ? `<button class="btn-icon" title="Detach from this job" onclick="detachDoc(${d.id})">&#128465;</button>`
      : `<button class="btn-icon" title="Delete from library" ${deleteDisabled} onclick="deleteDoc(${d.id})">&#128465;</button>`;
    return `
      <tr>
        <td><span class="filename">${esc(d.filename)}</span></td>
        <td><span class="badge ${badgeClass}">${DOC_TYPE_LABELS[d.doc_type] || d.doc_type}</span></td>
        <td>${fmtSize(d.file_size)}</td>
        ${isJobView ? '' : `<td>${usageCell}</td>`}
        <td>${d.uploaded_at ? d.uploaded_at.slice(0,10) : '—'}</td>
        <td><div class="actions-cell">${actionBtns}</div></td>
      </tr>`;
  }).join('');

  content.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Filename</th>
          <th>Type</th>
          <th>Size</th>
          ${isJobView ? '' : '<th>Used by</th>'}
          <th>Uploaded</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function openUploadDialog() {
  document.getElementById('uploadFile').value = '';
  document.getElementById('uploadNotes').value = '';
  document.getElementById('uploadError').style.display = 'none';
  document.getElementById('uploadBtn').disabled = false;
  document.getElementById('uploadDialog').showModal();
}

async function uploadDocument() {
  const fileInput = document.getElementById('uploadFile');
  const errEl = document.getElementById('uploadError');
  const btn = document.getElementById('uploadBtn');
  errEl.style.display = 'none';

  if (!fileInput.files.length) {
    errEl.textContent = 'Please select a file.';
    errEl.style.display = 'block';
    return;
  }

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('doc_type', document.getElementById('uploadType').value);
  formData.append('notes', document.getElementById('uploadNotes').value);

  btn.disabled = true;
  btn.textContent = 'Uploading…';

  try {
    const url = jobId ? `/api/jobs/${jobId}/documents` : '/api/documents';
    const r = await fetch(url, { method: 'POST', body: formData });
    const data = await r.json();
    if (!r.ok) {
      errEl.textContent = data.detail || 'Upload failed';
      errEl.style.display = 'block';
      return;
    }
    document.getElementById('uploadDialog').close();
    showToast('Document uploaded');
    await loadDocs();
    if (jobId) await loadLibraryForPicker();
  } catch (e) {
    errEl.textContent = 'Network error: ' + e.message;
    errEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Upload';
  }
}

async function deleteDoc(docId) {
  if (!confirm('Delete this document from the library? This cannot be undone.')) return;
  const r = await fetch(`/api/documents/${docId}`, { method: 'DELETE' });
  if (r.ok || r.status === 204) {
    showToast('Document deleted');
    await loadDocs();
  } else {
    const data = await r.json().catch(() => ({}));
    showToast(data.detail?.error || 'Delete failed', true);
  }
}

async function detachDoc(docId) {
  if (!confirm('Detach this document from the job?')) return;
  const r = await fetch(`/api/jobs/${jobId}/documents/${docId}`, { method: 'DELETE' });
  if (r.ok || r.status === 204) {
    showToast('Document detached');
    await loadDocs();
    await loadLibraryForPicker();
  } else {
    showToast('Detach failed', true);
  }
}

async function attachFromLibrary() {
  const sel = document.getElementById('libraryPicker');
  const errEl = document.getElementById('attachError');
  errEl.style.display = 'none';
  if (!sel.value) {
    errEl.textContent = 'Please select a document.';
    errEl.style.display = 'block';
    return;
  }
  const formData = new FormData();
  formData.append('document_id', sel.value);
  const r = await fetch(`/api/jobs/${jobId}/documents`, { method: 'POST', body: formData });
  if (r.ok || r.status === 201) {
    showToast('Document attached');
    await loadDocs();
    await loadLibraryForPicker();
  } else {
    const data = await r.json().catch(() => ({}));
    errEl.textContent = data.detail || 'Attach failed';
    errEl.style.display = 'block';
  }
}

init();
