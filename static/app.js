/**
 * app.js — shared utilities for vm-builder-dashboard
 */

async function apiFetch(url, method = 'GET', body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== null) {
    opts.body = JSON.stringify(body);
  }

  const resp = await fetch(url, opts);

  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`;
    try {
      const data = await resp.json();
      const detail = data.detail ?? data.error;
      if (detail) {
        msg = typeof detail === 'string'
          ? detail
          : JSON.stringify(detail);
      }
    } catch (_) {
      // ignore parse errors
    }
    throw new Error(msg);
  }

  const text = await resp.text();
  return text ? JSON.parse(text) : null;
}

function showInlineAlert(el, type, msg) {
  if (!el) {
    return;
  }
  if (el._alertTimeoutId) {
    window.clearTimeout(el._alertTimeoutId);
  }
  el.className = `flash flash-${type}`;
  el.innerHTML = `<i class="bi bi-info-circle me-1"></i>${escapeHtml(msg)}`;
  el._alertTimeoutId = window.setTimeout(() => {
    el.className = 'flash hidden';
    el.innerHTML = '';
    el._alertTimeoutId = null;
  }, 3000);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function openDialog(id) {
  const dialog = document.getElementById(id);
  if (dialog && typeof dialog.showModal === 'function') {
    dialog.showModal();
  }
}

function closeDialog(id) {
  const dialog = document.getElementById(id);
  if (dialog && dialog.open) {
    dialog.close();
  }
}

function setupTabs() {
  const buttons = document.querySelectorAll('[data-tab-target]');
  if (!buttons.length) {
    return;
  }

  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      const targetId = button.getAttribute('data-tab-target');
      const allPanels = document.querySelectorAll('.tab-panel');

      buttons.forEach((item) => item.classList.remove('active'));
      allPanels.forEach((panel) => {
        panel.hidden = panel.id !== targetId;
      });

      button.classList.add('active');
    });
  });
}
