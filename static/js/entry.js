(() => {
  const boot = window.ENTRY_BOOTSTRAP || {};
  const state = {
    user: boot.user || null,
    isAdmin: Boolean(boot.isAdmin),
    plans: [],
    plan: null,
    date: '',
    slot: null,
    stations: [],
    defectCatalog: [],
    machines: [],
    defectRows: [],
    machineRows: [],
    reinspect: { DefectTotal: 0, FixedQty: 0, Remaining: 0 },
  };

  async function api(url, opts = {}) {
    return Admin.fetchJSON(url, opts);
  }

  function setUserText() {
    const el = document.getElementById('user-text');
    if (!el || !state.user) return;
    el.textContent = state.user.DisplayName || state.user.UserID;
  }

  function ensureDefectRow() {
    if (!state.defectRows.length) {
      state.defectRows.push({ DefectCode: '', StationPick: '', Stations: [] });
    }
  }

  function ensureMachineRow() {
    if (!state.machineRows.length) {
      state.machineRows.push({ MachineID: 0, DownMinutes: '', Reason: '' });
    }
  }

  function currentSlot() {
    const d = new Date();
    const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    if (hm >= '07:30' && hm < '09:30') return 1;
    if (hm >= '09:30' && hm < '11:30') return 2;
    if (hm >= '12:30' && hm < '14:30') return 3;
    if (hm >= '14:30' && hm < '16:30') return 4;
    if (hm >= '16:30') return 5;
    return null;
  }

  function selectSlot(slot) {
    state.slot = slot;
    document.querySelectorAll('#slot-pills button').forEach((button) => {
      button.classList.toggle('active', Number(button.dataset.slot) === slot);
    });
    updateButtonsEnabled();
  }

  function renderPlanSelector() {
    const sel = document.getElementById('sel-plan');
    if (!state.plans.length) {
      sel.innerHTML = '<option value="">Không có kế hoạch cho tài khoản này</option>';
      return;
    }
    sel.innerHTML = '<option value="">Chọn kế hoạch</option>' + state.plans.map((plan) => {
      return `<option value="${plan.MONo}">${Admin.escape(plan.SoDonHang)} · Style ${Admin.escape(plan.StyleNo || '')}</option>`;
    }).join('');
    if (state.plans.length === 1) {
      sel.value = state.plans[0].MONo;
    }
  }

  async function applyPlanSelection(mono) {
    state.plan = state.plans.find((plan) => plan.MONo === mono) || null;
    state.stations = [];
    const info = document.getElementById('plan-info');
    if (!state.plan) {
      info.textContent = 'Chọn kế hoạch để bắt đầu nhập liệu.';
      renderDefectRows();
      refreshAllPanes();
      updateButtonsEnabled();
      return;
    }
    try {
      state.stations = await api(`/entry/api/stations?mono=${encodeURIComponent(state.plan.MONo)}`);
    } catch (err) {
      Admin.toast(err.message, 'error');
    }
    info.innerHTML = `
      <strong>${Admin.escape(state.plan.SoDonHang)}</strong>
      · KH ${(state.plan.SLKH || 0).toLocaleString()} pcs
      · Rải chuyền ${Admin.escape(state.plan.FirstHangDate || '—')}
      · Style ${Admin.escape(state.plan.StyleNo || '')}
    `;
    renderDefectRows();
    refreshAllPanes();
    updateButtonsEnabled();
  }

  function defectCatalogOptions(selected) {
    let html = '<option value="">Chọn dạng lỗi</option>';
    const groups = {};
    for (const defect of state.defectCatalog) {
      (groups[defect.DefectGroup] = groups[defect.DefectGroup] || []).push(defect);
    }
    const labels = {
      C: 'C · Lỗi chung',
      S: 'S · Đường may',
      F: 'F · Vải / phụ liệu',
      M: 'M · Máy',
      T: 'T · Tape / seam',
    };
    for (const key of Object.keys(labels)) {
      const list = groups[key];
      if (!list) continue;
      html += `<optgroup label="${labels[key]}">`;
      for (const defect of list) {
        const sel = defect.DefectCode === selected ? 'selected' : '';
        html += `<option value="${defect.DefectCode}" ${sel}>${defect.DefectCode}. ${Admin.escape(defect.DefectName)}</option>`;
      }
      html += '</optgroup>';
    }
    return html;
  }

  function stationOptions(selected) {
    if (!state.stations.length) {
      return '<option value="">Kế hoạch chưa có danh sách công đoạn</option>';
    }
    let html = '<option value="">Chọn công đoạn / vị trí lỗi</option>';
    for (const station of state.stations) {
      const value = station.StationKey || station.StationGuid || '';
      const sel = value === selected ? 'selected' : '';
      const guid = station.StationGuid || '';
      html += `<option value="${Admin.escape(value)}" data-guid="${Admin.escape(guid)}" data-label="${Admin.escape(station.StationLabel)}" ${sel}>${Admin.escape(station.StationLabel)}</option>`;
    }
    return html;
  }

  function stationPairsHTML(stations) {
    if (!stations.length) {
      return '<div class="muted small">Chưa có cặp Công đoạn – Số lượng nào.</div>';
    }
    return stations.map((station) => `
      <div class="station-pair" data-station-key="${Admin.escape(station.StationKey)}">
        <div class="station-pair-label">${Admin.escape(station.StationLabel)}</div>
        <input type="number" min="1" class="erow-station-qty" data-station-key="${Admin.escape(station.StationKey)}" value="${station.Qty || ''}" placeholder="SL" inputmode="numeric" />
        <button class="btn btn-danger btn-sm erow-station-del" type="button" data-station-key="${Admin.escape(station.StationKey)}">X</button>
      </div>
    `).join('');
  }

  function renderDefectRows() {
    const wrap = document.getElementById('defect-rows');
    if (!state.defectRows.length) {
      wrap.innerHTML = '<div class="muted">Bấm "+ Thêm dòng" để bắt đầu.</div>';
      updateButtonsEnabled();
      return;
    }
    wrap.innerHTML = state.defectRows.map((row, idx) => `
      <div class="erow erow-defect-block" data-idx="${idx}">
        <div class="erow-defect-head">
          <select class="erow-defect">${defectCatalogOptions(row.DefectCode)}</select>
          <select class="erow-station-pick">${stationOptions(row.StationPick || '')}</select>
          <button class="btn btn-soft btn-sm erow-station-add" type="button">+ Thêm trạm</button>
          <button class="btn btn-danger btn-sm erow-del" type="button">X</button>
        </div>
        <div class="erow-station-list">${stationPairsHTML(row.Stations || [])}</div>
      </div>
    `).join('');
    updateButtonsEnabled();
  }

  function machineOptions(selected) {
    let html = '<option value="">Chọn loại máy</option>';
    for (const machine of state.machines) {
      const sel = machine.MachineID === selected ? 'selected' : '';
      html += `<option value="${machine.MachineID}" ${sel}>${Admin.escape(machine.MachineName)}</option>`;
    }
    return html;
  }

  function renderMachineRows() {
    const wrap = document.getElementById('machine-rows');
    if (!state.machineRows.length) {
      wrap.innerHTML = '<div class="muted">Bấm "+ Thêm dòng" để bắt đầu.</div>';
      updateButtonsEnabled();
      return;
    }
    wrap.innerHTML = state.machineRows.map((row, idx) => `
      <div class="erow" data-idx="${idx}">
        <select class="mrow-machine">${machineOptions(row.MachineID)}</select>
        <input type="number" min="1" class="mrow-min" value="${row.DownMinutes || ''}" placeholder="Phút dừng" inputmode="numeric" />
        <input type="text" class="mrow-reason" value="${Admin.escape(row.Reason || '')}" placeholder="Mô tả vấn đề" maxlength="500" />
        <button class="btn btn-danger btn-sm erow-del" type="button">X</button>
      </div>
    `).join('');
    updateButtonsEnabled();
  }

  function renderReinspect() {
    const current = state.reinspect;
    document.getElementById('ri-total').textContent = current.DefectTotal.toLocaleString();
    document.getElementById('ri-fixed').textContent = current.FixedQty.toLocaleString();
    document.getElementById('ri-remain').textContent = current.Remaining.toLocaleString();
    document.getElementById('inp-fixed').value = current.FixedQty;
    document.getElementById('ri-meta').textContent =
      current.UpdatedAt ? `Cập nhật ${current.UpdatedAt} bởi ${current.UpdatedBy || '—'}` : 'Chưa lưu lần nào.';
    updateButtonsEnabled();
  }

  async function loadDefectLog() {
    const tbody = document.querySelector('#tbl-defect-log tbody');
    if (!state.plan || !state.date) {
      tbody.innerHTML = '<tr><td colspan="8" class="muted">Chọn kế hoạch và ngày.</td></tr>';
      return;
    }
    try {
      const rows = await api(`/entry/api/defect-log?mono=${encodeURIComponent(state.plan.MONo)}&date=${state.date}`);
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="muted">Chưa có dòng lỗi nào.</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map((row) => `
        <tr>
          <td>${row.Slot}</td>
          <td><strong>${Admin.escape(row.DefectCode)}</strong></td>
          <td>${Admin.escape(row.DefectName)}</td>
          <td>${Admin.escape(row.StationLabel)}</td>
          <td><strong>${row.Qty}</strong></td>
          <td>${Admin.escape(row.CreatedBy || '')}</td>
          <td class="muted">${row.LoggedAt}</td>
          <td class="col-action"><button class="btn btn-danger btn-sm" data-del-defect="${row.DefectLog_guid}">Xoá</button></td>
        </tr>
      `).join('');
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="8" class="muted">Lỗi: ${Admin.escape(err.message)}</td></tr>`;
    }
  }

  async function loadMachineLog() {
    const tbody = document.querySelector('#tbl-machine-log tbody');
    if (!state.plan || !state.date) {
      tbody.innerHTML = '<tr><td colspan="7" class="muted">Chọn kế hoạch và ngày.</td></tr>';
      return;
    }
    try {
      const rows = await api(`/entry/api/breakdown-log?mono=${encodeURIComponent(state.plan.MONo)}&date=${state.date}`);
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="muted">Chưa có sự cố nào.</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map((row) => `
        <tr>
          <td>${row.Slot ?? '—'}</td>
          <td>${Admin.escape(row.MachineName)}</td>
          <td><strong>${row.DownMinutes}'</strong></td>
          <td>${Admin.escape(row.Reason || '')}</td>
          <td>${Admin.escape(row.CreatedBy || '')}</td>
          <td class="muted">${row.LoggedAt}</td>
          <td class="col-action"><button class="btn btn-danger btn-sm" data-del-brk="${row.Breakdown_guid}">Xoá</button></td>
        </tr>
      `).join('');
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="7" class="muted">Lỗi: ${Admin.escape(err.message)}</td></tr>`;
    }
  }

  async function loadReinspect() {
    if (!state.plan || !state.date) {
      state.reinspect = { DefectTotal: 0, FixedQty: 0, Remaining: 0 };
      renderReinspect();
      return;
    }
    try {
      state.reinspect = await api(`/entry/api/reinspect?mono=${encodeURIComponent(state.plan.MONo)}&date=${state.date}`);
      renderReinspect();
    } catch (err) {
      Admin.toast(err.message, 'error');
    }
  }

  function updateButtonsEnabled() {
    const ctxOk = Boolean(state.plan && state.date && state.slot);
    document.getElementById('btn-save-defect').disabled = !ctxOk || state.defectRows.length === 0;
    document.getElementById('btn-save-machine').disabled = !ctxOk || state.machineRows.length === 0;
    document.getElementById('btn-save-reinspect').disabled = !(state.plan && state.date);
    document.getElementById('defect-hint').textContent = ctxOk ? '' : 'Cần chọn Kế hoạch + Ngày + Mốc giờ';
    document.getElementById('machine-hint').textContent = ctxOk ? '' : 'Cần chọn Kế hoạch + Ngày + Mốc giờ';
  }

  function refreshAllPanes() {
    loadDefectLog();
    loadMachineLog();
    loadReinspect();
  }

  function validateContext() {
    if (!state.plan) {
      Admin.toast('Chọn kế hoạch', 'error');
      return false;
    }
    if (!state.date) {
      Admin.toast('Chọn ngày', 'error');
      return false;
    }
    if (!state.slot) {
      Admin.toast('Chọn mốc giờ', 'error');
      return false;
    }
    return true;
  }

  async function bootstrap() {
    setUserText();
    ensureDefectRow();
    ensureMachineRow();
    renderDefectRows();
    renderMachineRows();

    const [plans, catalog, machines] = await Promise.all([
      api('/entry/api/plans'),
      api('/entry/api/defect-catalog'),
      api('/entry/api/machines'),
    ]);
    state.plans = plans;
    state.defectCatalog = catalog;
    state.machines = machines;
    renderPlanSelector();
    renderMachineRows();
    renderDefectRows();

    const today = new Date().toISOString().slice(0, 10);
    document.getElementById('inp-date').value = today;
    state.date = today;

    const slot = currentSlot();
    if (slot) {
      selectSlot(slot);
    }

    if (state.plans.length) {
      const firstMono = document.getElementById('sel-plan').value || state.plans[0].MONo;
      document.getElementById('sel-plan').value = firstMono;
      await applyPlanSelection(firstMono);
    } else {
      updateButtonsEnabled();
    }
  }

  document.getElementById('btn-logout').addEventListener('click', async () => {
    try {
      await Admin.logout('/login');
    } catch (err) {
      Admin.toast(err.message, 'error');
    }
  });

  document.getElementById('slot-pills').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-slot]');
    if (!button) return;
    selectSlot(Number(button.dataset.slot));
  });

  document.getElementById('sel-plan').addEventListener('change', async (event) => {
    await applyPlanSelection(event.target.value);
  });

  document.getElementById('inp-date').addEventListener('change', (event) => {
    state.date = event.target.value;
    refreshAllPanes();
    updateButtonsEnabled();
  });

  document.querySelectorAll('.tabs .tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tabs .tab').forEach((el) => el.classList.remove('active'));
      tab.classList.add('active');
      const id = tab.dataset.tab;
      document.querySelectorAll('.tab-pane').forEach((pane) => { pane.style.display = 'none'; });
      document.getElementById(`pane-${id}`).style.display = '';
    });
  });

  document.getElementById('btn-add-defect').addEventListener('click', () => {
    state.defectRows.push({ DefectCode: '', StationPick: '', Stations: [] });
    renderDefectRows();
  });

  document.getElementById('defect-rows').addEventListener('click', (event) => {
    const del = event.target.closest('.erow-del');
    if (del) {
      const idx = Number(del.closest('.erow').dataset.idx);
      state.defectRows.splice(idx, 1);
      renderDefectRows();
      return;
    }
    const addBtn = event.target.closest('.erow-station-add');
    if (addBtn) {
      const row = addBtn.closest('.erow');
      const idx = Number(row.dataset.idx);
      const current = state.defectRows[idx];
      const sel = row.querySelector('.erow-station-pick');
      const stationKey = sel.value;
      if (!stationKey) {
        Admin.toast('Chọn công đoạn trước khi thêm.', 'error');
        return;
      }
      if (current.Stations.some((item) => item.StationKey === stationKey)) {
        Admin.toast('Công đoạn này đã được thêm rồi.', 'error');
        return;
      }
      const option = sel.options[sel.selectedIndex];
      current.Stations.push({
        StationKey: stationKey,
        StationGuid: option ? option.dataset.guid || '' : '',
        StationLabel: option ? option.dataset.label || option.text : '',
        Qty: '',
      });
      current.StationPick = '';
      renderDefectRows();
      return;
    }
    const delPair = event.target.closest('.erow-station-del');
    if (delPair) {
      const row = delPair.closest('.erow');
      const idx = Number(row.dataset.idx);
      const current = state.defectRows[idx];
      current.Stations = current.Stations.filter((item) => item.StationKey !== delPair.dataset.stationKey);
      renderDefectRows();
    }
  });

  document.getElementById('defect-rows').addEventListener('change', (event) => {
    const row = event.target.closest('.erow');
    if (!row) return;
    const idx = Number(row.dataset.idx);
    const current = state.defectRows[idx];
    if (event.target.classList.contains('erow-defect')) {
      current.DefectCode = event.target.value;
    } else if (event.target.classList.contains('erow-station-pick')) {
      current.StationPick = event.target.value;
    } else if (event.target.classList.contains('erow-station-qty')) {
      const pair = current.Stations.find((item) => item.StationKey === event.target.dataset.stationKey);
      if (pair) pair.Qty = Number(event.target.value) || '';
    }
    updateButtonsEnabled();
  });

  document.getElementById('btn-save-defect').addEventListener('click', async () => {
    if (!validateContext()) return;
    const items = state.defectRows.flatMap((row) => (row.Stations || [])
      .filter((station) => row.DefectCode && station.StationKey && station.Qty > 0)
      .map((station) => ({
        DefectCode: row.DefectCode,
        StationGuid: station.StationGuid || null,
        StationLabel: station.StationLabel,
        Qty: station.Qty,
      })));
    if (!items.length) {
      Admin.toast('Chưa có dòng lỗi hợp lệ', 'error');
      return;
    }
    try {
      await api('/entry/api/defect-batch', {
        method: 'POST',
        body: JSON.stringify({
          MONo: state.plan.MONo,
          ShtDate: state.date,
          Slot: state.slot,
          Items: items,
        }),
      });
      Admin.toast(`Đã lưu ${items.length} dòng lỗi.`, 'ok');
      state.defectRows = [];
      ensureDefectRow();
      renderDefectRows();
      loadDefectLog();
    } catch (err) {
      Admin.toast(err.message, 'error');
    }
  });

  document.getElementById('tbl-defect-log').addEventListener('click', async (event) => {
    const btn = event.target.closest('[data-del-defect]');
    if (!btn) return;
    if (!window.confirm('Xoá dòng lỗi này?')) return;
    try {
      await api(`/entry/api/defect-log/${btn.dataset.delDefect}`, { method: 'DELETE' });
      Admin.toast('Đã xoá.', 'ok');
      loadDefectLog();
    } catch (err) {
      Admin.toast(err.message, 'error');
    }
  });

  document.getElementById('btn-add-machine').addEventListener('click', () => {
    state.machineRows.push({ MachineID: 0, DownMinutes: '', Reason: '' });
    renderMachineRows();
  });

  document.getElementById('machine-rows').addEventListener('click', (event) => {
    const del = event.target.closest('.erow-del');
    if (!del) return;
    const idx = Number(del.closest('.erow').dataset.idx);
    state.machineRows.splice(idx, 1);
    renderMachineRows();
  });

  document.getElementById('machine-rows').addEventListener('input', (event) => {
    const row = event.target.closest('.erow');
    if (!row) return;
    const idx = Number(row.dataset.idx);
    const current = state.machineRows[idx];
    if (event.target.classList.contains('mrow-machine')) current.MachineID = Number(event.target.value) || 0;
    else if (event.target.classList.contains('mrow-min')) current.DownMinutes = Number(event.target.value) || '';
    else if (event.target.classList.contains('mrow-reason')) current.Reason = event.target.value;
    updateButtonsEnabled();
  });

  document.getElementById('btn-save-machine').addEventListener('click', async () => {
    if (!validateContext()) return;
    const items = state.machineRows
      .filter((row) => row.MachineID > 0 && row.DownMinutes > 0)
      .map((row) => ({ MachineID: row.MachineID, DownMinutes: row.DownMinutes, Reason: row.Reason || null }));
    if (!items.length) {
      Admin.toast('Chưa có dòng máy hợp lệ', 'error');
      return;
    }
    try {
      await api('/entry/api/breakdown-batch', {
        method: 'POST',
        body: JSON.stringify({
          MONo: state.plan.MONo,
          ShtDate: state.date,
          Slot: state.slot,
          Items: items,
        }),
      });
      Admin.toast(`Đã lưu ${items.length} sự cố.`, 'ok');
      state.machineRows = [];
      ensureMachineRow();
      renderMachineRows();
      loadMachineLog();
    } catch (err) {
      Admin.toast(err.message, 'error');
    }
  });

  document.getElementById('tbl-machine-log').addEventListener('click', async (event) => {
    const btn = event.target.closest('[data-del-brk]');
    if (!btn) return;
    if (!window.confirm('Xoá sự cố này?')) return;
    try {
      await api(`/entry/api/breakdown-log/${btn.dataset.delBrk}`, { method: 'DELETE' });
      Admin.toast('Đã xoá.', 'ok');
      loadMachineLog();
    } catch (err) {
      Admin.toast(err.message, 'error');
    }
  });

  document.getElementById('btn-fix-plus').addEventListener('click', () => {
    state.reinspect.FixedQty = Math.max(0, Number(state.reinspect.FixedQty) + 1);
    state.reinspect.Remaining = Math.max(0, state.reinspect.DefectTotal - state.reinspect.FixedQty);
    renderReinspect();
  });

  document.getElementById('btn-fix-minus').addEventListener('click', () => {
    state.reinspect.FixedQty = Math.max(0, Number(state.reinspect.FixedQty) - 1);
    state.reinspect.Remaining = Math.max(0, state.reinspect.DefectTotal - state.reinspect.FixedQty);
    renderReinspect();
  });

  document.getElementById('inp-fixed').addEventListener('input', (event) => {
    const value = Math.max(0, Number(event.target.value) || 0);
    state.reinspect.FixedQty = value;
    state.reinspect.Remaining = Math.max(0, state.reinspect.DefectTotal - value);
    renderReinspect();
  });

  document.getElementById('btn-save-reinspect').addEventListener('click', async () => {
    if (!state.plan || !state.date) {
      Admin.toast('Chọn kế hoạch và ngày', 'error');
      return;
    }
    try {
      const data = await api('/entry/api/reinspect', {
        method: 'POST',
        body: JSON.stringify({
          MONo: state.plan.MONo,
          ShtDate: state.date,
          FixedQty: state.reinspect.FixedQty,
        }),
      });
      Admin.toast('Đã lưu.', 'ok');
      state.reinspect = {
        ...state.reinspect,
        DefectTotal: data.DefectTotal,
        FixedQty: data.FixedQty,
        Remaining: data.Remaining,
        UpdatedAt: new Date().toISOString().slice(0, 19).replace('T', ' '),
        UpdatedBy: state.user.UserID,
      };
      renderReinspect();
    } catch (err) {
      Admin.toast(err.message, 'error');
    }
  });

  bootstrap().catch((err) => {
    Admin.toast(err.message || 'Không tải được dữ liệu khởi tạo', 'error');
  });
})();
