let currentProvider = 'ollama';
let currentModel = '';
let keyStatus = {};
// Per-provider base URLs for the local providers (editable on this page).
let providerUrls = {};

const PROVIDER_LABELS = { ollama: 'Ollama', lmstudio: 'LM Studio', anthropic: 'Anthropic Claude', openai: 'OpenAI' };
const KEY_HINTS = { ollama: null, lmstudio: null, anthropic: 'ANTHROPIC_API_KEY', openai: 'OPENAI_API_KEY' };
// Local providers whose endpoint URL can be customized, with their defaults.
const LOCAL_URL_DEFAULTS = { ollama: 'http://localhost:11434', lmstudio: 'http://localhost:1234' };
const isLocal = (p) => Object.prototype.hasOwnProperty.call(LOCAL_URL_DEFAULTS, p);

async function init() {
  const res = await fetch('/api/settings');
  const s = await res.json();
  currentProvider = s.provider;
  currentModel = s.model;
  keyStatus = s.key_status;
  providerUrls = {
    ollama: s.ollama_url || LOCAL_URL_DEFAULTS.ollama,
    lmstudio: s.lmstudio_url || LOCAL_URL_DEFAULTS.lmstudio,
  };
  const ps = document.getElementById('pageSize');
  if (ps && s.page_size) ps.value = s.page_size;
  renderProviders(s.providers);
  updateBaseUrlField();
  await loadModels(currentProvider, currentModel);
  await loadEmailSettings();
}

function updateBaseUrlField() {
  const wrap = document.getElementById('baseUrlField');
  const input = document.getElementById('baseUrl');
  if (!wrap) return;
  if (isLocal(currentProvider)) {
    wrap.style.display = '';
    input.value = providerUrls[currentProvider] || '';
    input.placeholder = LOCAL_URL_DEFAULTS[currentProvider];
    document.getElementById('baseUrlLabel').textContent =
      `${PROVIDER_LABELS[currentProvider]} server URL`;
  } else {
    wrap.style.display = 'none';
  }
}

function onBaseUrlInput() {
  if (isLocal(currentProvider)) {
    providerUrls[currentProvider] = document.getElementById('baseUrl').value.trim();
  }
}

function reloadModels() {
  onBaseUrlInput();
  loadModels(currentProvider, currentModel);
}

async function savePageSize() {
  const pageSize = Math.max(5, Math.min(500, parseInt(document.getElementById('pageSize').value, 10) || 25));
  const toast = document.getElementById('pageSizeToast');
  const res = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: currentProvider, model: currentModel, page_size: pageSize }),
  });
  if (res.ok) {
    const s = await res.json();
    document.getElementById('pageSize').value = s.page_size;  // reflect clamped value
    toast.textContent = 'Saved!';
  } else {
    toast.textContent = 'Save failed';
  }
  toast.style.display = 'inline';
  setTimeout(() => { toast.style.display = 'none'; }, 2500);
}

async function loadEmailSettings() {
  try {
    const r = await fetch('/api/email/settings');
    const s = await r.json();
    const p = document.getElementById('emailProvider');
    const m = document.getElementById('emailModel');
    const iv = document.getElementById('emailSyncInterval');
    const kw = document.getElementById('emailKeywords');
    if (p) p.value = s.email_provider || '';
    if (m) m.value = s.email_ollama_model || '';
    if (iv) iv.value = s.email_sync_interval || 60;
    if (kw) kw.value = (s.email_keywords || []).join(', ');
  } catch (_) {}
}

async function saveEmailSettings() {
  const provider = document.getElementById('emailProvider').value;
  const model = document.getElementById('emailModel').value.trim();
  const interval = Math.max(5, parseInt(document.getElementById('emailSyncInterval').value, 10) || 60);
  const keywords = document.getElementById('emailKeywords').value
    .split(',').map(k => k.trim()).filter(Boolean);
  const toast = document.getElementById('emailToast');
  const r = await fetch('/api/email/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email_provider: provider, email_ollama_model: model,
      email_sync_interval: interval, email_keywords: keywords,
    }),
  });
  toast.textContent = r.ok ? 'Saved!' : 'Save failed';
  toast.style.display = 'inline';
  setTimeout(() => { toast.style.display = 'none'; }, 2500);
}

function esc(str) {
  return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderProviders(providers) {
  const list = document.getElementById('providerList');
  list.innerHTML = providers.map(p => {
    const ks = keyStatus[p];
    let badge = '';
    if (ks === null)  badge = '<span class="key-badge key-none">— No key needed</span>';
    else if (ks)      badge = '<span class="key-badge key-ok">&#10003; Key configured</span>';
    else              badge = `<span class="key-badge key-miss">&#9888; Set ${KEY_HINTS[p]} in .env</span>`;
    const checked = p === currentProvider ? 'checked' : '';
    return `
      <div class="provider-row">
        <input type="radio" name="provider" id="p-${p}" value="${p}" ${checked} onchange="onProviderChange('${p}')">
        <label for="p-${p}">${PROVIDER_LABELS[p] || p}</label>
        ${badge}
      </div>`;
  }).join('');
}

async function onProviderChange(provider) {
  currentProvider = provider;
  updateBaseUrlField();
  await loadModels(provider, '');
}

async function loadModels(provider, selectedModel) {
  const sel = document.getElementById('modelSelect');
  const txt = document.getElementById('modelText');
  const err = document.getElementById('modelError');

  sel.innerHTML = '<option disabled>Loading…</option>';
  sel.disabled = true;
  sel.style.display = '';
  txt.style.display = 'none';
  err.style.display = 'none';

  let url = `/api/models?provider=${encodeURIComponent(provider)}`;
  if (isLocal(provider) && providerUrls[provider]) {
    url += `&url=${encodeURIComponent(providerUrls[provider])}`;
  }

  try {
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok) throw new Error((data.error || 'Failed to load models') + (data.hint ? ' — ' + data.hint : ''));
    const models = data.models || [];
    if (models.length === 0) throw new Error('No models found for this provider.');
    sel.innerHTML = models.map(m =>
      `<option value="${esc(m)}" ${m === selectedModel ? 'selected' : ''}>${esc(m)}</option>`
    ).join('');
    sel.disabled = false;
    currentModel = (!selectedModel || !models.includes(selectedModel)) ? models[0] : selectedModel;
  } catch (e) {
    sel.style.display = 'none';
    txt.style.display = '';
    txt.value = selectedModel || '';
    currentModel = txt.value;
    err.textContent = e.message;
    err.style.display = 'block';
  }
}

function onModelInput() {
  const sel = document.getElementById('modelSelect');
  const txt = document.getElementById('modelText');
  currentModel = txt.style.display !== 'none' ? txt.value.trim() : sel.value;
}

async function saveSettings() {
  onModelInput();
  onBaseUrlInput();
  if (!currentModel) { alert('Please select or enter a model.'); return; }
  const body = { provider: currentProvider, model: currentModel };
  // Persist both local URLs so each provider remembers its own endpoint.
  if (providerUrls.ollama !== undefined) body.ollama_url = providerUrls.ollama;
  if (providerUrls.lmstudio !== undefined) body.lmstudio_url = providerUrls.lmstudio;
  const res = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    const toast = document.getElementById('toast');
    toast.style.display = 'inline';
    setTimeout(() => { toast.style.display = 'none'; }, 2500);
  } else {
    const err = await res.json();
    alert('Error: ' + (err.detail || 'Could not save settings'));
  }
}

const TEST_POSTING = `Software Engineer – Backend
Company: Acme Corp
Location: Berlin, Germany
Address: Unter den Linden 10, 10117 Berlin

We are looking for a backend engineer to build scalable APIs using Python and FastAPI.

Requirements: Python, FastAPI, PostgreSQL, Docker, Redis
Contact: hr@acme.de | +49 30 12345678`;

async function testParse() {
  onModelInput();
  const box = document.getElementById('testResult');
  box.className = 'test-result';
  box.style.display = 'block';
  box.textContent = 'Parsing sample posting…';

  await saveSettings();

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

init();

// Bookmarklet href — uses BASE_URL injected inline by the server
(function () {
  const base = window.JOBTRA_BASE || '';
  const code = "(async()=>{const t=document.body.innerText.slice(0,50000),u=location.href,d=document.createElement('div');d.style.cssText='position:fixed;bottom:20px;right:20px;z-index:999999;background:#222;color:#fff;padding:12px 16px;border-radius:6px;font:14px system-ui,sans-serif;box-shadow:0 4px 12px rgba(0,0,0,.3);max-width:320px;';d.textContent='Saving to tracker...';document.body.appendChild(d);try{const r=await fetch('" + base + "/api/parse-from-bookmarklet',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t,url:u})});const j=await r.json();if(!r.ok){d.textContent='✗ '+(j.error||'Save failed')+(j.hint?' ('+j.hint+')':'');d.style.background='#a00';setTimeout(()=>d.remove(),6000);}else{d.textContent='✓ Saved: '+j.position+' at '+j.company;d.style.background='#060';setTimeout(()=>d.remove(),3000);}}catch(e){d.textContent='✗ '+(e.message||'network error');d.style.background='#a00';setTimeout(()=>d.remove(),6000);}})();";
  document.getElementById('bookmarklet').href = 'javascript:' + encodeURIComponent(code);
})();
