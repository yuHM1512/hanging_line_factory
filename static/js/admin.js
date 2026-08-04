// Shared admin helpers
window.Admin = (() => {
  async function fetchJSON(url, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    const resp = await fetch(url, { ...opts, headers });
    let data;
    try {
      data = await resp.json();
    } catch (_) {
      throw new Error(`HTTP ${resp.status} (không phải JSON)`);
    }
    if (!resp.ok) {
      const msg = data && data.detail ? data.detail : `HTTP ${resp.status}`;
      throw new Error(msg);
    }
    return data;
  }

  function toast(msg, type = '') {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.className = `toast show ${type}`;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove('show'), 3000);
  }

  function escape(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  async function logout(nextUrl = '/login') {
    await fetchJSON('/auth/api/logout', { method: 'POST' });
    window.location.href = nextUrl;
  }

  function confirmDelete(msg) {
    return new Promise((resolve) => {
      const modal = document.getElementById('confirm-modal');
      if (!modal) { resolve(window.confirm(msg)); return; }
      document.getElementById('confirm-msg').textContent = msg;
      modal.hidden = false;
      const yes = document.getElementById('confirm-yes');
      const no  = document.getElementById('confirm-no');
      function cleanup(result) {
        modal.hidden = true;
        yes.removeEventListener('click', onYes);
        no.removeEventListener('click', onNo);
        resolve(result);
      }
      function onYes() { cleanup(true); }
      function onNo()  { cleanup(false); }
      yes.addEventListener('click', onYes);
      no.addEventListener('click', onNo);
      // Close on backdrop click
      modal.addEventListener('click', function handler(e) {
        if (e.target === modal) { modal.removeEventListener('click', handler); cleanup(false); }
      });
    });
  }

  /** Validate a form and show inline errors. Returns true if valid. */
  function validateForm(form) {
    // Clear previous errors
    form.querySelectorAll('.field.has-error').forEach(f => f.classList.remove('has-error'));
    form.querySelectorAll('.field-error').forEach(e => e.textContent = '');
    if (form.checkValidity()) return true;
    // Show errors on invalid fields
    for (const el of form.elements) {
      if (!el.validity || el.validity.valid) continue;
      const field = el.closest('.field');
      if (!field) continue;
      field.classList.add('has-error');
      let errEl = field.querySelector('.field-error');
      if (!errEl) {
        errEl = document.createElement('span');
        errEl.className = 'field-error';
        field.appendChild(errEl);
      }
      // Vietnamese messages
      if (el.validity.valueMissing) errEl.textContent = 'Bắt buộc nhập';
      else if (el.validity.rangeUnderflow) errEl.textContent = `Tối thiểu ${el.min}`;
      else if (el.validity.stepMismatch) errEl.textContent = 'Giá trị không hợp lệ';
      else if (el.validity.typeMismatch) errEl.textContent = 'Sai định dạng';
      else errEl.textContent = el.validationMessage || 'Không hợp lệ';
      // Clear error on input
      el.addEventListener('input', function handler() {
        field.classList.remove('has-error');
        errEl.textContent = '';
        el.removeEventListener('input', handler);
      }, { once: true });
    }
    // Focus first invalid
    const first = form.querySelector('.field.has-error input, .field.has-error select');
    if (first) first.focus();
    return false;
  }

  return { fetchJSON, toast, escape, logout, confirmDelete, validateForm };
})();
