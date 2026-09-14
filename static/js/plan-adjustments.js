document.addEventListener('DOMContentLoaded', () => {
  const modal = document.createElement('dialog');
  modal.style.cssText = 'width:min(680px,calc(100% - 24px));max-height:85vh;overflow:auto;border:1px solid #dbe5f1;border-radius:16px;padding:24px;color:#10244a';
  modal.innerHTML = `<button type="button" class="btn btn-soft" data-close style="float:right">Đóng</button>
    <h3>Lịch sử tăng / giảm sản lượng</h3><p data-status role="status"></p><div data-list></div>
    <form hidden style="margin-top:20px;gap:12px">
      <label class="field">Số lượng tăng / giảm<input name="qty" type="number" step="1" required></label>
      <label class="field">Lý do<input name="reason" maxlength="100" required></label>
      <label class="field">Ghi chú<textarea name="notes" maxlength="500"></textarea></label>
      <button class="btn btn-primary" type="submit">Lưu chỉnh sửa</button>
    </form>`;
  document.body.append(modal);
  const form = modal.querySelector('form'), list = modal.querySelector('[data-list]');
  const status = modal.querySelector('[data-status]');
  let planID, editingID, version = 0;
  modal.querySelector('[data-close]').onclick = () => modal.close();
  async function load() {
    const request = ++version;
    list.replaceChildren(); form.hidden = true; form.style.display = 'none'; status.textContent = 'Đang tải lịch sử…';
    try {
      const rows = await Admin.fetchJSON(`/admin/api/plan/${encodeURIComponent(planID)}/adjustments`);
      if (request !== version) return;
      status.textContent = rows.length ? 'Chọn lần điều chỉnh cần sửa hoặc xoá.' : 'Chưa có lần điều chỉnh nào.';
      rows.forEach(row => {
        const card = document.createElement('div');
        card.style.cssText = 'padding:12px 0;border-bottom:1px solid #e2e8f0';
        const detail = document.createElement('p');
        detail.textContent = `${row.CreatedAt} · ${row.DeltaQty > 0 ? '+' : ''}${Number(row.DeltaQty).toLocaleString('vi-VN')} sp · ${row.Reason}`;
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'btn btn-soft'; button.textContent = 'Sửa';
        button.onclick = () => {
          editingID = row.Adjustment_guid;
          form.elements.qty.value = row.DeltaQty;
          form.elements.reason.value = row.Reason;
          form.elements.notes.value = row.Notes || '';
          form.hidden = false; form.style.display = 'grid'; form.elements.qty.focus();
        };
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'btn btn-soft'; remove.textContent = 'Xoá';
        remove.style.cssText = 'margin-left:8px;color:#b42318';
        remove.onclick = async () => {
          const qty = `${row.DeltaQty > 0 ? '+' : ''}${Number(row.DeltaQty).toLocaleString('vi-VN')}`;
          if (!window.confirm(`Xoá lần điều chỉnh ${qty} sp (${row.Reason})? Tổng sản lượng sẽ được tính lại khi bỏ lần này.`)) return;
          remove.disabled = true; button.disabled = true;
          status.textContent = 'Đang xoá lần điều chỉnh…';
          try {
            await Admin.fetchJSON(`/admin/api/plan-adjustments/${encodeURIComponent(row.Adjustment_guid)}`, {method:'DELETE'});
            await load(); await loadPlans();
            Admin.toast('Đã xoá lần điều chỉnh và cập nhật tổng sản lượng.', 'ok');
          } catch (error) { status.textContent = error.message; }
          finally { remove.disabled = false; button.disabled = false; }
        };
        card.append(detail, button, remove); list.append(card);
      });
    } catch (error) { if (request === version) status.textContent = error.message; }
  }
  document.querySelector('#tbl-plans').addEventListener('click', e => {
    const button = e.target.closest('[data-adjust-history]');
    if (!button) return;
    planID = button.dataset.adjustHistory;
    document.querySelectorAll('[data-row-menu]').forEach(el => el.style.display = 'none');
    modal.showModal(); load();
  });
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const qty = Number(form.elements.qty.value), reason = form.elements.reason.value.trim();
    if (!Number.isInteger(qty) || qty === 0 || !reason) {
      status.textContent = 'Nhập số nguyên khác 0 và lý do.'; return;
    }
    const save = form.querySelector('[type=submit]'); save.disabled = true;
    try {
      await Admin.fetchJSON(`/admin/api/plan-adjustments/${encodeURIComponent(editingID)}`, {
        method: 'PUT', body: JSON.stringify({DeltaQty:qty, Reason:reason, Notes:form.elements.notes.value.trim() || null}),
      });
      await load(); await loadPlans(); Admin.toast('Đã sửa lần điều chỉnh sản lượng.', 'ok');
    } catch (error) { status.textContent = error.message; }
    finally { save.disabled = false; }
  });
});
