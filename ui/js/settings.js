let currentProvider = 'ollama';
let currentModel = '';
let keyStatus = {};

const PROVIDER_LABELS = { ollama: 'Ollama', anthropic: 'Anthropic Claude', openai: 'OpenAI' };
const KEY_HINTS = { ollama: null, anthropic: 'ANTHROPIC_API_KEY', openai: 'OPENAI_API_KEY' };

async function init() {
  const res = await fetch('/api/settings');
  const s = await res.json();
  currentProvider = s.provider;
  currentModel = s.model;
  keyStatus = s.key_status;
  renderProviders(s.providers);
  await loadModels(currentProvider, currentModel);
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

  try {
    const res = await fetch(`/api/models?provider=${encodeURIComponent(provider)}`);
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
  if (!currentModel) { alert('Please select or enter a model.'); return; }
  const res = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: currentProvider, model: currentModel }),
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
  const base = window.JOB_TRACKER_BASE || '';
  const code = "(async()=>{const t=document.body.innerText.slice(0,50000),u=location.href,d=document.createElement('div');d.style.cssText='position:fixed;bottom:20px;right:20px;z-index:999999;background:#222;color:#fff;padding:12px 16px;border-radius:6px;font:14px system-ui,sans-serif;box-shadow:0 4px 12px rgba(0,0,0,.3);max-width:320px;';d.textContent='Saving to tracker...';document.body.appendChild(d);try{const r=await fetch('" + base + "/api/parse-from-bookmarklet',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t,url:u})});const j=await r.json();if(!r.ok){d.textContent='✗ '+(j.error||'Save failed')+(j.hint?' ('+j.hint+')':'');d.style.background='#a00';setTimeout(()=>d.remove(),6000);}else{d.textContent='✓ Saved: '+j.position+' at '+j.company;d.style.background='#060';setTimeout(()=>d.remove(),3000);}}catch(e){d.textContent='✗ '+(e.message||'network error');d.style.background='#a00';setTimeout(()=>d.remove(),6000);}})();";
  document.getElementById('bookmarklet').href = 'javascript:' + encodeURIComponent(code);
})();
