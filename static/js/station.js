(() => {
  const $ = id => document.getElementById(id);
  const today = window.ST_TODAY;

  const picker = $('st-picker'), pickerList = $('st-picker-list');
  const empty = $('st-empty'), counter = $('st-counter'), back = $('st-back');
  const planEl = $('st-plan'), opSelect = $('st-op-select'), qtyEl = $('st-qty');
  const plusBtn = $('st-plus'), minusBtn = $('st-minus');

  let ops = [];
  let current = null;
  let currentGroup = [];
  let qty = 0;
  let chain = Promise.resolve();

  const fmt = n => Number(n || 0).toLocaleString('vi-VN');

  function groupByMono() {
    const groups = new Map();
    ops.forEach(op => {
      if (!groups.has(op.NhuCauMe)) groups.set(op.NhuCauMe, []);
      groups.get(op.NhuCauMe).push(op);
    });
    return groups;
  }

  function showQty(n) {
    qtyEl.textContent = fmt(n);
    qtyEl.classList.remove('st-bump');
    void qtyEl.offsetWidth;
    qtyEl.classList.add('st-bump');
  }

  function renderPicker() {
    pickerList.replaceChildren();
    const groups = groupByMono();
    groups.forEach((list, key) => {
      const first = list[0];
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'st-pick-mono-card';
      card.innerHTML = `
        <div class="st-pick-mono-body">
          <div class="st-pick-mono-name">${Admin.escape(first.NhuCauMe)}${first.StyleNo ? ' · ' + Admin.escape(first.StyleNo) : ''}</div>
          <div class="st-pick-mono-info">Tổ ${Admin.escape(String(first.LineNo ?? '?'))} · ${list.length} công đoạn</div>
        </div>
        <span class="material-symbols-outlined st-pick-chevron">chevron_right</span>`;
      card.addEventListener('click', () => selectMono(key));
      pickerList.appendChild(card);
    });
  }

  function selectMono(monoKey) {
    const groups = groupByMono();
    currentGroup = groups.get(monoKey) || [];
    if (!currentGroup.length) return;

    opSelect.replaceChildren();
    currentGroup.forEach((op, i) => {
      const opt = document.createElement('option');
      opt.value = i;
      opt.textContent = op.OperationName;
      opSelect.appendChild(opt);
    });

    select(currentGroup[0]);
  }

  function select(op) {
    current = op;
    qty = Number(op.TodayQty || 0);
    planEl.textContent = `${op.NhuCauMe}${op.StyleNo ? ' · ' + op.StyleNo : ''} · Tổ ${op.LineNo ?? '?'}`;
    const idx = currentGroup.findIndex(o => o.OperationID === op.OperationID);
    if (idx >= 0) opSelect.value = idx;
    showQty(qty);
    picker.hidden = true;
    empty.hidden = true;
    counter.hidden = false;
    back.hidden = groupByMono().size <= 1;
  }

  function showPicker() {
    current = null;
    counter.hidden = true;
    back.hidden = true;
    if (!ops.length) { empty.hidden = false; picker.hidden = true; return; }
    const groups = groupByMono();
    if (groups.size === 1) {
      selectMono(groups.keys().next().value);
      return;
    }
    renderPicker();
    picker.hidden = false;
  }

  async function resync() {
    try {
      const rows = await Admin.fetchJSON('/entry/api/station/my-ops?day=' + encodeURIComponent(today));
      ops = rows;
      if (current) {
        const match = rows.find(o => o.OperationID === current.OperationID);
        if (match) {
          const monoOps = rows.filter(o => o.NhuCauMe === match.NhuCauMe);
          currentGroup = monoOps;
          current = match;
          qty = Number(match.TodayQty || 0);
          showQty(qty);
          opSelect.replaceChildren();
          monoOps.forEach((op, i) => {
            const opt = document.createElement('option');
            opt.value = i;
            opt.textContent = op.OperationName;
            opSelect.appendChild(opt);
          });
          const idx = monoOps.findIndex(o => o.OperationID === match.OperationID);
          if (idx >= 0) opSelect.value = idx;
        }
      }
    } catch (_) { /* giữ số hiện tại */ }
  }

  function tap(kind) {
    if (!current) return;
    if (kind === 'undo' && qty <= 0) return;
    qty = kind === 'undo' ? Math.max(0, qty - 1) : qty + 1;
    showQty(qty);
    if (navigator.vibrate) navigator.vibrate(kind === 'undo' ? 30 : 50);
    const opId = current.OperationID;
    const url = kind === 'undo' ? '/entry/api/station/undo' : '/entry/api/station/pulse';
    chain = chain.then(async () => {
      try {
        await Admin.fetchJSON(url, { method: 'POST', body: JSON.stringify({ operation_id: opId, day: today }) });
      } catch (e) {
        Admin.toast(e.message, 'error');
        await resync();
      }
    });
  }

  opSelect.addEventListener('change', () => {
    const idx = Number(opSelect.value);
    if (currentGroup[idx]) select(currentGroup[idx]);
  });

  plusBtn.addEventListener('click', () => tap('add'));
  minusBtn.addEventListener('click', () => tap('undo'));
  back.addEventListener('click', showPicker);
  $('st-logout').addEventListener('click', () => Admin.logout('/login'));

  Admin.fetchJSON('/entry/api/station/my-ops?day=' + encodeURIComponent(today))
    .then(rows => { ops = rows; showPicker(); })
    .catch(e => Admin.toast(e.message, 'error'));
})();
