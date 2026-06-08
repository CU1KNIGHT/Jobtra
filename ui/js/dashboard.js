let dashData = null;
const charts = {};
let dashMap = null;
let mapResizeObserver = null;

const STATUS_ORDER = ['applied', 'interview_done', 'rejected', 'accepted', 'open'];
const STATUS_LABEL = {
  applied: 'Applied', interview_done: 'Interview done',
  rejected: 'Rejected', accepted: 'Accepted', open: 'Open',
};
const STATUS_COLOR = {
  applied: '#3b82f6', interview_done: '#8b5cf6',
  rejected: '#ef4444', accepted: '#22c55e', open: '#9ca3af',
};
const PURPLE_RAMP = ['#6d28d9', '#7c3aed', '#8b5cf6', '#a78bfa', '#c4b5fd', '#ddd6fe'];
const FULL_STATUS_LABEL = {
  open: 'Open', applied: 'Applied', interview_done: 'Interview done',
  rejected: 'Rejected', rejected_after_interview: 'Rejected after interview', accepted: 'Accepted',
};

function isDark() { return document.documentElement.getAttribute('data-theme') === 'dark'; }
function themeColors() {
  return isDark()
    ? { text: '#9ca3af', grid: 'rgba(255,255,255,.08)' }
    : { text: '#555', grid: 'rgba(0,0,0,.07)' };
}

function fmtMonth(ym) {
  const [y, m] = (ym || '').split('-');
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return m ? `${names[parseInt(m, 10) - 1]} ${(y || '').slice(2)}` : ym;
}

async function loadDashboard() {
  const btn = document.getElementById('refreshBtn');
  if (btn) btn.disabled = true;
  try {
    const r = await fetch('/api/dashboard');
    dashData = await r.json();
    render();
  } catch (e) {
    document.getElementById('dashContent').innerHTML =
      `<div class="dash-empty">Could not load dashboard: ${esc(e.message)}</div>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

function destroyVisuals() {
  for (const k of Object.keys(charts)) {
    try { charts[k].destroy(); } catch (_) {}
    delete charts[k];
  }
  if (mapResizeObserver) { mapResizeObserver.disconnect(); mapResizeObserver = null; }
  if (dashMap) { try { dashMap.remove(); } catch (_) {} dashMap = null; }
}

function render() {
  if (!dashData) return;
  destroyVisuals();
  const c = document.getElementById('dashContent');
  const total = dashData.summary.total;

  if (total < 3) {
    c.innerHTML = recentCard() + `<div class="dash-empty">Add more applications to see your dashboard.<br>
      <span style="font-size:13px">(${total} so far — charts appear at 3+.)</span></div>`;
    return;
  }

  const s = dashData.summary;
  const convRate = total ? Math.round((s.interviews / total) * 100) : 0;

  c.innerHTML = `
    <div class="kpi-grid">
      ${kpi('Total applications', total, 'All time')}
      ${kpi('Active / open', s.active, 'Awaiting response')}
      ${kpi('Interviews done', s.interviews, `${convRate}% interview rate`)}
      ${kpi('Rejection rate', `${Math.round(s.rejection_rate * 100)}%`, 'rejected + after interview')}
    </div>
    ${recentCard()}
    <div class="chart-grid">
      ${chartCard('Monthly applications', 'Applications submitted per month', 'monthChart')}
      ${chartCard('Status distribution', 'Where all applications stand', 'statusChart')}
      ${chartCard('Applications by job type', 'Inferred from posting text / hours', 'typeChart')}
      <div class="chart-card">
        <div class="chart-title">Applications by city</div>
        <div class="chart-subtitle">Geographic spread of your search</div>
        <div id="dashMap"></div>
        <div class="map-note" id="mapNote"></div>
      </div>
      <div class="chart-card span-2">
        <div class="chart-title">Roles you're targeting</div>
        <div class="chart-subtitle">Tile size = number of applications for that position</div>
        <div class="treemap" id="treemap"></div>
      </div>
    </div>`;

  renderMonth();
  renderStatus();
  renderType();
  renderMap();
  renderTreemap();
}

function recentCard() {
  const recent = (dashData && dashData.recent) || [];
  if (!recent.length) return '';
  const rows = recent.map(j => {
    const status = `<span class="pill pill-${j.status}">${FULL_STATUS_LABEL[j.status] || j.status}</span>`;
    const date = j.date_applied ? `<span class="recent-date">${esc(j.date_applied)}</span>` : '';
    const city = j.city ? `<span class="recent-city">&#128205; ${esc(j.city)}</span>` : '';
    return `<a class="recent-item" href="/jobs/${j.id}">
      <span class="recent-main">
        <span class="recent-pos">${esc(j.position) || '—'}</span>
        <span class="recent-co">${esc(j.company) || ''}</span>
      </span>
      <span class="recent-meta">${status}${date}${city}</span>
    </a>`;
  }).join('');
  return `<div class="recent-card">
    <div class="recent-head">
      <div>
        <div class="chart-title">Recently applied</div>
        <div class="chart-subtitle">Your latest applications</div>
      </div>
      <a class="recent-all" href="/jobs">View all &#8594;</a>
    </div>
    <div class="recent-list">${rows}</div>
  </div>`;
}

function kpi(label, value, sub) {
  return `<div class="kpi-card">
    <div class="kpi-label">${label}</div>
    <div class="kpi-value">${value}</div>
    <div class="kpi-sub">${sub}</div>
  </div>`;
}
function chartCard(title, subtitle, canvasId) {
  return `<div class="chart-card">
    <div class="chart-title">${title}</div>
    <div class="chart-subtitle">${subtitle}</div>
    <div class="chart-canvas-wrap"><canvas id="${canvasId}"></canvas></div>
    <div class="chart-legend" id="${canvasId}-legend"></div>
  </div>`;
}
function legendHTML(items) {
  return items.map(i =>
    `<span class="legend-item"><span class="legend-swatch" style="background:${i.color}"></span>${i.text}</span>`
  ).join('');
}

function renderMonth() {
  if (typeof Chart === 'undefined') return;
  const t = themeColors();
  const labels = dashData.by_month.map(m => fmtMonth(m.month));
  const data = dashData.by_month.map(m => m.count);
  charts.month = new Chart(document.getElementById('monthChart'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data, fill: true, tension: .3,
        borderColor: '#7c3aed',
        backgroundColor: 'rgba(124,58,237,.15)',
        pointBackgroundColor: '#7c3aed', pointRadius: 3,
      }],
    },
    options: baseOpts(t, { yInteger: true }),
  });
  document.getElementById('monthChart-legend').innerHTML =
    legendHTML([{ color: '#7c3aed', text: 'Applications per month' }]);
}

function renderStatus() {
  if (typeof Chart === 'undefined') return;
  const sc = {};
  for (const r of dashData.by_status) {
    const k = r.status === 'rejected_after_interview' ? 'rejected' : r.status;
    sc[k] = (sc[k] || 0) + r.count;
  }
  const segs = STATUS_ORDER.filter(k => sc[k] > 0)
    .map(k => ({ k, label: STATUS_LABEL[k], color: STATUS_COLOR[k], count: sc[k] }));
  const sum = segs.reduce((a, b) => a + b.count, 0);

  charts.status = new Chart(document.getElementById('statusChart'), {
    type: 'doughnut',
    data: {
      labels: segs.map(s => s.label),
      datasets: [{ data: segs.map(s => s.count), backgroundColor: segs.map(s => s.color), borderWidth: 0 }],
    },
    options: { responsive: true, maintainAspectRatio: false, cutout: '62%', plugins: { legend: { display: false } } },
  });
  document.getElementById('statusChart-legend').innerHTML = legendHTML(segs.map(s => ({
    color: s.color,
    text: `${s.label} — ${s.count} (${Math.round((s.count / sum) * 100)}%)`,
  })));
}

function renderType() {
  if (typeof Chart === 'undefined') return;
  const t = themeColors();
  const labels = dashData.by_type.map(x => x.type);
  const data = dashData.by_type.map(x => x.count);
  const colors = labels.map((_, i) => PURPLE_RAMP[i % PURPLE_RAMP.length]);
  charts.type = new Chart(document.getElementById('typeChart'), {
    type: 'bar',
    data: { labels, datasets: [{ data, backgroundColor: colors, borderRadius: 5 }] },
    options: baseOpts(t, { yInteger: true }),
  });
  document.getElementById('typeChart-legend').innerHTML =
    legendHTML(labels.map((l, i) => ({ color: colors[i], text: `${l} — ${data[i]}` })));
}

function baseOpts(t, { yInteger } = {}) {
  return {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip: { enabled: true } },
    scales: {
      x: { ticks: { color: t.text }, grid: { color: t.grid } },
      y: {
        beginAtZero: true,
        ticks: { color: t.text, precision: 0, stepSize: yInteger ? 1 : undefined },
        grid: { color: t.grid },
      },
    },
  };
}

function renderMap() {
  if (typeof L === 'undefined') return;
  const mapped = dashData.by_city.filter(c => c.lat != null && c.lng != null);
  const unmapped = dashData.by_city.filter(c => c.lat == null);

  dashMap = L.map('dashMap', { scrollWheelZoom: false });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(dashMap);

  if (mapped.length) {
    const markers = [];
    for (const c of mapped) {
      const m = L.circleMarker([c.lat, c.lng], {
        radius: 6 + Math.sqrt(c.count) * 4,
        color: '#6d28d9', fillColor: '#8b5cf6', fillOpacity: .6, weight: 2,
      }).addTo(dashMap);
      m.bindPopup(`<strong>${esc(c.city)}</strong><br>${c.count} application${c.count !== 1 ? 's' : ''}`);
      markers.push([c.lat, c.lng]);
    }
    dashMap.fitBounds(markers, { padding: [30, 30], maxZoom: 10 });
  } else {
    dashMap.setView([51.1, 10.4], 6);
  }

  const note = document.getElementById('mapNote');
  if (unmapped.length) {
    note.textContent = 'Not on map (unknown coordinates): ' +
      unmapped.map(c => `${c.city} (${c.count})`).join(', ');
  }

  // Leaflet needs a re-measure when the sidebar collapses/expands or layout shifts.
  mapResizeObserver = new ResizeObserver(() => dashMap && dashMap.invalidateSize());
  mapResizeObserver.observe(document.getElementById('dashMap'));
  setTimeout(() => dashMap && dashMap.invalidateSize(), 0);
}

function renderTreemap() {
  const el = document.getElementById('treemap');
  if (!el) return;
  const W = el.clientWidth, H = el.clientHeight;
  const items = dashData.by_position.map(p => ({ value: p.count, label: p.position, count: p.count }));
  const tiles = squarify(items, 0, 0, W, H);
  el.innerHTML = tiles.map((tl, i) => {
    const color = PURPLE_RAMP[i % PURPLE_RAMP.length];
    const showText = tl.w > 46 && tl.h > 26;
    const inner = showText
      ? `<div class="tt-pos">${esc(tl.label)}</div><div class="tt-count">${tl.count}</div>`
      : '';
    return `<div class="treemap-tile" title="${esc(tl.label)} — ${tl.count}"
      style="left:${tl.x}px;top:${tl.y}px;width:${tl.w}px;height:${tl.h}px;background:${color}">${inner}</div>`;
  }).join('');
}

// ── Squarified treemap layout ─────────────────────────────────────────────
function squarify(data, x, y, w, h) {
  const nodes = data.map(d => ({ ...d }));
  const total = nodes.reduce((s, n) => s + n.value, 0);
  if (total <= 0 || w <= 0 || h <= 0) return [];
  const area = w * h;
  nodes.forEach(n => { n._a = (n.value / total) * area; });

  const out = [];
  let rx = x, ry = y, rw = w, rh = h, i = 0;
  while (i < nodes.length) {
    const vertical = rw < rh;          // lay the row along the shorter side
    const side = vertical ? rw : rh;
    const row = [nodes[i]];
    let j = i + 1;
    while (j < nodes.length) {
      if (worstRatio(row.concat(nodes[j]), side) <= worstRatio(row, side)) {
        row.push(nodes[j]); j++;
      } else break;
    }
    const rowArea = row.reduce((s, n) => s + n._a, 0);
    const thick = rowArea / side;
    let off = 0;
    for (const n of row) {
      const len = n._a / thick;
      if (vertical) out.push({ ...n, x: rx + off, y: ry, w: len, h: thick });
      else out.push({ ...n, x: rx, y: ry + off, w: thick, h: len });
      off += len;
    }
    if (vertical) { ry += thick; rh -= thick; } else { rx += thick; rw -= thick; }
    i = j;
  }
  return out;
}
function worstRatio(row, side) {
  const sum = row.reduce((s, n) => s + n._a, 0);
  const max = Math.max(...row.map(n => n._a));
  const min = Math.min(...row.map(n => n._a));
  return Math.max((side * side * max) / (sum * sum), (sum * sum) / (side * side * min));
}

// Re-render charts/map when the theme flips so colors stay legible.
new MutationObserver(() => render())
  .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

loadDashboard();
