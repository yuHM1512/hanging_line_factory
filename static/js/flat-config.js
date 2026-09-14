window.FlatConfig = (() => {
  const enabled = document.getElementById('flat-enabled');
  const fields = document.getElementById('flat-fields');
  const ops = document.getElementById('flat-ops');
  function toggle() {
    fields.hidden = !enabled.checked;
    ops.querySelectorAll('input').forEach(input => input.required = enabled.checked);
  }
  function add(op = {}) {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:8px;margin:10px 0;align-items:end';
    const label = document.createElement('label'); label.className = 'field'; label.style.flex = '1';
    label.textContent = 'Tên công đoạn';
    const input = document.createElement('input'); input.maxLength = 200;
    input.value = op.name || ''; input.required = enabled.checked;
    label.append(input); row.dataset.id = op.id || '';
    const remove = document.createElement('button'); remove.type = 'button';
    remove.className = 'btn btn-soft'; remove.textContent = 'Bỏ'; remove.onclick = () => row.remove();
    row.append(label, remove); ops.append(row);
  }
  enabled.onchange = () => { if (enabled.checked && !ops.children.length) add(); toggle(); };
  document.getElementById('flat-add').onclick = () => add();
  function reset() { ops.replaceChildren(); enabled.checked = false; toggle(); }
  return {
    reset,
    async load(key) {
      reset();
      const data = await Admin.fetchJSON('/admin/api/flat-line?key=' + encodeURIComponent(key));
      enabled.checked = data.enabled; data.operations.forEach(add); toggle();
    },
    value() {
      return {enabled:enabled.checked, operations:[...ops.children].map(row => ({
        id:row.dataset.id ? Number(row.dataset.id) : null, name:row.querySelector('input').value.trim(),
      }))};
    },
  };
})();
