// Runs immediately (no defer) to avoid flash of unstyled theme / sidebar
(function () {
  const saved = localStorage.getItem('theme') ||
    (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', saved);
  document.documentElement.setAttribute(
    'data-sidebar', localStorage.getItem('sidebar') || 'expanded');
})();

function toggleSidebar() {
  const next = document.documentElement.getAttribute('data-sidebar') === 'collapsed'
    ? 'expanded' : 'collapsed';
  document.documentElement.setAttribute('data-sidebar', next);
  localStorage.setItem('sidebar', next);
}

function toggleTheme() {
  const curr = document.documentElement.getAttribute('data-theme');
  const next = curr === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = next === 'dark' ? '☀️' : '🌙';
}

document.addEventListener('DOMContentLoaded', function () {
  const btn = document.getElementById('themeToggle');
  if (btn) {
    const theme = document.documentElement.getAttribute('data-theme');
    btn.textContent = theme === 'dark' ? '️☀️' : '🌙';
  }
});

function esc(str) {
  return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
