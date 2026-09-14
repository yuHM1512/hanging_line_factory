(() => {
  const $ = id => document.getElementById(id);
  const demand = $('demand'), day = $('day');
  const opsSection = $('ops-section'), opsContainer = $('operations');
  const prompt = $('prompt'), demandInfo = $('demand-info');
  const summary = $('summary'), summaryTotal = $('summary-total'), summaryCount = $('summary-count');
  const saveBtn = $('save'), logsEl = $('logs'), logCount = $('log-count');
  const dateLabel = $('date-label');

  const sheet = $('sheet'), backdrop = $('sheet-backdrop');
  let editID = null, editOldQty = 0, version = 0, selectedDemand = null;

  const apiUrl = () => '/entry/api/flat-line?key=' + encodeURIComponent(demand.value) + '&day=' + day.value;

  function updateDateLabel() {
    const today = new Date().toISOString().slice(0, 10);
    dateLabel.textContent = day.value === today ? 'Hôm nay' : '';
    dateLabel.hidden = day.value === today ? false : true;
  }

  function updateSummary() {
    const inputs = opsContainer.querySelectorAll('.fl-op-input');
    let total = 0, count = 0;
    inputs.forEach(inp => {
      const v = parseInt(inp.value);
      if (v > 0) { total += v; count++; }
    });
    summaryTotal.textContent = total.toLocaleString('vi-VN');
    summaryCount.textContent = count;
    summary.hidden = total === 0;
    saveBtn.disabled = total === 0;
    saveBtn.innerHTML = total > 0
      ? `<span class="material-symbols-outlined">save</span> LƯU LẦN BÁO (${total.toLocaleString('vi-VN')} SP)`
      : `<span class="material-symbols-outlined">save</span> LƯU LẦN BÁO`;
  }

  function buildOpCard(op) {
    const card = document.createElement('div');
    card.className = 'fl-op-card' + (op.IsActive ? '' : ' fl-op-inactive');

    const hasValue = false;
    card.innerHTML = `
      <div class="fl-op-head">
        <span class="fl-op-name">${Admin.escape(op.Name)}</span>
        <span class="fl-op-status ${hasValue ? 'fl-op-status-filled' : 'fl-op-status-waiting'}">${op.IsActive ? 'Chờ nhập' : 'Ngừng'}</span>
      </div>
      <div class="fl-op-cumulative">Lũy kế ngày: <strong>${op.DayQty.toLocaleString('vi-VN')}</strong> sp</div>
      ${op.IsActive ? `
        <div class="fl-op-input-label">Lần báo này</div>
        <div class="fl-op-input-row">
          <input type="number" class="fl-op-input" data-id="${op.ID}" min="1" max="2147483647" step="1" inputmode="numeric" placeholder="Nhập số lượng">
          <button type="button" class="fl-quick-btn" data-add="10">+10</button>
          <button type="button" class="fl-quick-btn" data-add="50">+50</button>
        </div>
      ` : ''}
    `;

    if (op.IsActive) {
      const input = card.querySelector('.fl-op-input');
      const statusEl = card.querySelector('.fl-op-status');

      input.addEventListener('input', () => {
        const v = parseInt(input.value);
        if (v > 0) {
          statusEl.textContent = 'Đã điền: ' + v;
          statusEl.className = 'fl-op-status fl-op-status-filled';
        } else {
          statusEl.textContent = 'Chờ nhập';
          statusEl.className = 'fl-op-status fl-op-status-waiting';
        }
        updateSummary();
      });

      card.querySelectorAll('.fl-quick-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const add = parseInt(btn.dataset.add);
          const cur = parseInt(input.value) || 0;
          input.value = cur + add;
          input.dispatchEvent(new Event('input'));
        });
      });
    }
    return card;
  }

  function buildLogCard(r) {
    const time = r.CreatedAt ? r.CreatedAt.slice(11, 16) : '--:--';
    const card = document.createElement('div');
    card.className = 'fl-log-card';
    card.innerHTML = `
      <div class="fl-log-time">
        <div class="fl-log-hour">${Admin.escape(time)}</div>
        <div class="fl-log-dot"></div>
      </div>
      <div class="fl-log-body">
        <div class="fl-log-name">${Admin.escape(r.Name)}</div>
        <div class="fl-log-who">${Admin.escape(r.CreatedBy)}</div>
      </div>
      <div class="fl-log-qty">+${r.Qty.toLocaleString('vi-VN')} sp</div>
    `;
    if (r.CanEdit) {
      const btn = document.createElement('button');
      btn.className = 'fl-log-edit';
      btn.type = 'button';
      btn.textContent = 'Sửa';
      btn.addEventListener('click', () => openEdit(r));
      card.appendChild(btn);
    }
    return card;
  }

  async function load() {
    const v = ++version;
    opsSection.hidden = true;
    summary.hidden = true;
    logsEl.innerHTML = '';

    if (!demand.value || !day.value) {
      prompt.hidden = false;
      demandInfo.hidden = true;
      return;
    }

    updateDateLabel();
    prompt.hidden = true;

    try {
      const data = await Admin.fetchJSON(apiUrl());
      if (v !== version) return;

      // Demand info
      if (selectedDemand) {
        $('info-ncm').textContent = selectedDemand.NhuCauMe + (selectedDemand.StyleNo ? ' · ' + selectedDemand.StyleNo : '');
        $('info-line').textContent = 'Tổ ' + selectedDemand.LineNo;
        $('info-operations').innerHTML = data.operations.map(op => `
          <div class="fl-demand-op ${op.IsActive ? '' : 'is-inactive'}">
            <span class="fl-demand-op-name">${Admin.escape(op.Name)}</span>
            <strong class="fl-demand-op-qty">${Number(op.DayQty || 0).toLocaleString('vi-VN')}</strong>
            <span class="fl-demand-op-unit">sản phẩm</span>
          </div>
        `).join('');
        demandInfo.hidden = false;
      }

      // Operations
      opsContainer.replaceChildren();
      data.operations.forEach(op => opsContainer.appendChild(buildOpCard(op)));
      opsSection.hidden = false;
      saveBtn.disabled = true;
      updateSummary();

      // Logs
      if (data.reports.length) {
        data.reports.forEach(r => logsEl.appendChild(buildLogCard(r)));
      } else {
        logsEl.innerHTML = `<div class="fl-empty">
          <span class="material-symbols-outlined">edit_note</span>
          <strong>Chưa có lần báo nào</strong>
          <p>Dữ liệu các lần lưu sản lượng sẽ hiển thị tại đây.</p>
        </div>`;
      }
      logCount.textContent = data.reports.length + ' lần';
    } catch (e) {
      Admin.toast(e.message, 'error');
    }
  }

  // Save
  saveBtn.addEventListener('click', async () => {
    const items = [...opsContainer.querySelectorAll('.fl-op-input')]
      .filter(i => i.value !== '' && parseInt(i.value) > 0)
      .map(i => ({ operation_id: Number(i.dataset.id), qty: Number(i.value) }));
    if (!items.length) return;

    saveBtn.disabled = true;
    demand.disabled = day.disabled = true;
    try {
      await Admin.fetchJSON(apiUrl(), {
        method: 'POST',
        body: JSON.stringify({ day: day.value, items })
      });
      Admin.toast('Đã lưu lần báo thành công!');
      await load();
    } catch (e) {
      Admin.toast(e.message, 'error');
    } finally {
      demand.disabled = day.disabled = false;
    }
  });

  // Edit bottom sheet
  function openEdit(r) {
    editID = r.ID;
    editOldQty = r.Qty;
    $('edit-meta').innerHTML = `
      <div class="fl-sheet-meta-row"><span class="fl-sheet-meta-label">Công đoạn</span><span class="fl-sheet-meta-val">${Admin.escape(r.Name)}</span></div>
      <div class="fl-sheet-meta-row"><span class="fl-sheet-meta-label">Người tạo</span><span class="fl-sheet-meta-val">${Admin.escape(r.CreatedBy)}</span></div>
      <div class="fl-sheet-meta-row"><span class="fl-sheet-meta-label">Thời gian gốc</span><span class="fl-sheet-meta-val">${Admin.escape(r.CreatedAt)}</span></div>
    `;
    $('edit-day').value = day.value;
    $('edit-qty').value = r.Qty;
    $('edit-old').textContent = 'Cũ: ' + r.Qty + ' sp';
    updateEditDiff();
    backdrop.hidden = false;
    sheet.hidden = false;
    setTimeout(() => {
      backdrop.classList.add('show');
      sheet.classList.add('show');
    }, 20);
  }

  function closeEdit() {
    backdrop.classList.remove('show');
    sheet.classList.remove('show');
    setTimeout(() => { backdrop.hidden = true; sheet.hidden = true; }, 300);
  }

  function updateEditDiff() {
    const newQty = parseInt($('edit-qty').value) || 0;
    const diff = newQty - editOldQty;
    const diffEl = $('edit-diff');
    if (diff === 0) { diffEl.textContent = ''; return; }
    diffEl.textContent = 'Chênh lệch điều chỉnh: ' + (diff > 0 ? '+' : '') + diff + ' sản phẩm';
  }

  $('edit-qty').addEventListener('input', updateEditDiff);
  $('edit-minus').addEventListener('click', () => {
    const inp = $('edit-qty');
    const v = Math.max(0, (parseInt(inp.value) || 0) - 1);
    inp.value = v;
    updateEditDiff();
  });
  $('edit-plus').addEventListener('click', () => {
    const inp = $('edit-qty');
    inp.value = (parseInt(inp.value) || 0) + 1;
    updateEditDiff();
  });

  $('sheet-close').addEventListener('click', closeEdit);
  backdrop.addEventListener('click', closeEdit);

  $('edit-save').addEventListener('click', async () => {
    const btn = $('edit-save');
    btn.disabled = true;
    try {
      await Admin.fetchJSON('/entry/api/flat-line/' + editID, {
        method: 'PUT',
        body: JSON.stringify({
          day: $('edit-day').value,
          qty: Number($('edit-qty').value)
        })
      });
      Admin.toast('Đã cập nhật lần báo.');
      closeEdit();
      await load();
    } catch (e) {
      Admin.toast(e.message, 'error');
    } finally {
      btn.disabled = false;
    }
  });

  // Listeners
  demand.addEventListener('change', () => {
    const opt = demand.options[demand.selectedIndex];
    if (demand.value) {
      selectedDemand = { NhuCauMe: demand.value, StyleNo: opt?.textContent?.split('·')[1]?.trim() || '', LineNo: '' };
    } else {
      selectedDemand = null;
    }
    load();
  });
  day.addEventListener('change', load);

  $('logout').addEventListener('click', () => Admin.logout('/login'));

  // Boot
  Admin.fetchJSON('/entry/api/flat-line/demands').then(rows => {
    demand.replaceChildren();
    demand.add(new Option(rows.length ? '-- Chọn nhu cầu mẹ --' : 'Tổ chưa có nhu cầu theo dõi', ''));
    rows.forEach(r => {
      const opt = new Option(`${r.NhuCauMe} · ${r.StyleNo}`, r.NhuCauMe);
      opt.dataset.line = r.LineNo;
      demand.add(opt);
    });
    if (rows.length === 1) {
      demand.value = rows[0].NhuCauMe;
      selectedDemand = rows[0];
      load();
    }
  }).catch(e => Admin.toast(e.message, 'error'));

  updateDateLabel();
})();
