document.addEventListener('DOMContentLoaded', () => {
  const DIALOG_CSS = 'width:min(680px,calc(100% - 24px));max-height:85vh;overflow:auto;border:1px solid #dbe5f1;border-radius:16px;padding:24px;color:#10244a';
  const fmtQty = q => `${q > 0 ? '+' : ''}${Number(q).toLocaleString('vi-VN')}`;
  const today = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  const closeMenus = () => document.querySelectorAll('[data-row-menu]').forEach(el => el.style.display = 'none');

  /* ── Thêm nhu cầu con ─────────────────────────────────────────── */
  const childModal = document.createElement('dialog');
  childModal.style.cssText = DIALOG_CSS;
  childModal.innerHTML = `<button type="button" class="btn btn-soft" data-close style="float:right">Đóng</button>
    <h3>Thêm nhu cầu con</h3>
    <p class="muted small" data-child-sub></p>
    <p class="muted small">Sản lượng được cộng vào SLKH. TV-1 hiện nhu cầu con này ở ô "Nhu cầu mới nhất" từ ngày sản xuất trở đi; trước ngày đó vẫn hiện nhu cầu cũ.</p>
    <p data-status role="status" style="color:#b42318"></p>
    <form style="display:grid;gap:12px;margin-top:8px">
      <label class="field">Tên nhu cầu con<input name="demand" maxlength="100" required placeholder="VD: PL-26-351265-SS27-013-KH7-T4"></label>
      <label class="field">Sản lượng (sp)<input name="qty" type="number" min="1" step="1" required></label>
      <label class="field">Ngày sản xuất (áp dụng trên TV từ ngày này)<input name="prodDate" type="date" required></label>
      <label class="field">Ghi chú<textarea name="notes" maxlength="500"></textarea></label>
      <button class="btn btn-primary" type="submit">Lưu nhu cầu con</button>
    </form>`;
  document.body.append(childModal);
  const childForm = childModal.querySelector('form');
  const childStatus = childModal.querySelector('[data-status]');
  let childPlanID = null;
  childModal.querySelector('[data-close]').onclick = () => childModal.close();

  childForm.addEventListener('submit', async e => {
    e.preventDefault();
    const demand = childForm.elements.demand.value.trim();
    const qty = Number(childForm.elements.qty.value);
    const prodDate = childForm.elements.prodDate.value;
    if (!demand || !Number.isInteger(qty) || qty <= 0 || !prodDate) {
      childStatus.textContent = 'Cần nhập tên nhu cầu, sản lượng (> 0) và ngày sản xuất.';
      return;
    }
    const save = childForm.querySelector('[type=submit]'); save.disabled = true;
    childStatus.textContent = '';
    try {
      await Admin.fetchJSON(`/admin/api/plan/${encodeURIComponent(childPlanID)}/child-demands`, {
        method: 'POST',
        body: JSON.stringify({ DemandNo: demand, Qty: qty, ProdDate: prodDate,
                               Notes: childForm.elements.notes.value.trim() || null }),
      });
      childModal.close();
      await loadPlans();
      Admin.toast(`Đã thêm nhu cầu con ${demand} (+${qty.toLocaleString('vi-VN')} sp).`, 'ok');
    } catch (error) { childStatus.textContent = error.message; }
    finally { save.disabled = false; }
  });

  /* ── Lịch sử nhu cầu con / tăng giảm ──────────────────────────── */
  const modal = document.createElement('dialog');
  modal.style.cssText = DIALOG_CSS;
  modal.innerHTML = `<button type="button" class="btn btn-soft" data-close style="float:right">Đóng</button>
    <h3>Lịch sử nhu cầu con / tăng giảm sản lượng</h3><p data-status role="status"></p><div data-list></div>
    <form hidden style="margin-top:20px;gap:12px">
      <label class="field" data-child-only>Tên nhu cầu con<input name="demand" maxlength="100"></label>
      <label class="field" data-qty-label>Số lượng tăng / giảm<input name="qty" type="number" step="1" required></label>
      <label class="field" data-child-only>Ngày sản xuất<input name="prodDate" type="date"></label>
      <label class="field" data-reason-only>Lý do<input name="reason" maxlength="100"></label>
      <label class="field">Ghi chú<textarea name="notes" maxlength="500"></textarea></label>
      <button class="btn btn-primary" type="submit">Lưu chỉnh sửa</button>
    </form>`;
  document.body.append(modal);
  const form = modal.querySelector('form'), list = modal.querySelector('[data-list]');
  const status = modal.querySelector('[data-status]');
  let planID, editing = null, version = 0;
  modal.querySelector('[data-close]').onclick = () => modal.close();

  function showForm(row) {
    editing = row;
    const isChild = !!row.DemandNo;
    form.querySelectorAll('[data-child-only]').forEach(el => el.hidden = !isChild);
    form.querySelectorAll('[data-reason-only]').forEach(el => el.hidden = isChild);
    form.querySelector('[data-qty-label]').firstChild.textContent = isChild ? 'Sản lượng (sp)' : 'Số lượng tăng / giảm';
    form.elements.demand.value = row.DemandNo || '';
    form.elements.prodDate.value = row.ProdDate || '';
    form.elements.qty.value = row.DeltaQty;
    form.elements.reason.value = row.Reason;
    form.elements.notes.value = row.Notes || '';
    form.hidden = false; form.style.display = 'grid'; form.elements.qty.focus();
  }

  async function load() {
    const request = ++version;
    list.replaceChildren(); form.hidden = true; form.style.display = 'none'; status.textContent = 'Đang tải lịch sử…';
    try {
      const rows = await Admin.fetchJSON(`/admin/api/plan/${encodeURIComponent(planID)}/adjustments`);
      if (request !== version) return;
      status.textContent = rows.length ? 'Chọn dòng cần sửa hoặc xoá.' : 'Chưa có nhu cầu con hay lần điều chỉnh nào.';
      rows.forEach(row => {
        const card = document.createElement('div');
        card.style.cssText = 'padding:12px 0;border-bottom:1px solid #e2e8f0';
        const detail = document.createElement('p');
        detail.textContent = row.DemandNo
          ? `${row.CreatedAt} · Nhu cầu con ${row.DemandNo} · ${fmtQty(row.DeltaQty)} sp · SX từ ${row.ProdDate}`
          : `${row.CreatedAt} · Tăng/giảm ${fmtQty(row.DeltaQty)} sp · ${row.Reason}`;
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'btn btn-soft'; button.textContent = 'Sửa';
        button.onclick = () => showForm(row);
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'btn btn-soft'; remove.textContent = 'Xoá';
        remove.style.cssText = 'margin-left:8px;color:#b42318';
        remove.onclick = async () => {
          const what = row.DemandNo ? `nhu cầu con ${row.DemandNo} (${fmtQty(row.DeltaQty)} sp)` : `lần điều chỉnh ${fmtQty(row.DeltaQty)} sp (${row.Reason})`;
          if (!window.confirm(`Xoá ${what}? Tổng sản lượng sẽ được tính lại.`)) return;
          remove.disabled = true; button.disabled = true;
          status.textContent = 'Đang xoá…';
          try {
            await Admin.fetchJSON(`/admin/api/plan-adjustments/${encodeURIComponent(row.Adjustment_guid)}`, {method:'DELETE'});
            await load(); await loadPlans();
            Admin.toast('Đã xoá và cập nhật tổng sản lượng.', 'ok');
          } catch (error) { status.textContent = error.message; }
          finally { remove.disabled = false; button.disabled = false; }
        };
        card.append(detail, button, remove); list.append(card);
      });
    } catch (error) { if (request === version) status.textContent = error.message; }
  }

  document.querySelector('#tbl-plans').addEventListener('click', e => {
    const childBtn = e.target.closest('[data-child-demand]');
    if (childBtn) {
      closeMenus();
      childPlanID = childBtn.dataset.childDemand;
      childForm.reset();
      childForm.elements.prodDate.value = today();
      childStatus.textContent = '';
      childModal.querySelector('[data-child-sub]').textContent = `Nhu cầu mẹ: ${childBtn.dataset.childLabel || ''}`;
      childModal.showModal();
      childForm.elements.demand.focus();
      return;
    }
    const button = e.target.closest('[data-adjust-history]');
    if (!button) return;
    planID = button.dataset.adjustHistory;
    closeMenus();
    modal.showModal(); load();
  });

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const isChild = !!editing.DemandNo;
    const qty = Number(form.elements.qty.value);
    const demand = form.elements.demand.value.trim();
    const prodDate = form.elements.prodDate.value;
    const reason = isChild ? (editing.Reason || 'Nhu cầu con') : form.elements.reason.value.trim();
    if (isChild ? (!demand || !prodDate || !Number.isInteger(qty) || qty <= 0)
                : (!Number.isInteger(qty) || qty === 0 || !reason)) {
      status.textContent = isChild
        ? 'Nhu cầu con cần tên, sản lượng (> 0) và ngày sản xuất.'
        : 'Nhập số nguyên khác 0 và lý do.';
      return;
    }
    const save = form.querySelector('[type=submit]'); save.disabled = true;
    try {
      await Admin.fetchJSON(`/admin/api/plan-adjustments/${encodeURIComponent(editing.Adjustment_guid)}`, {
        method: 'PUT',
        body: JSON.stringify({
          DeltaQty: qty, Reason: reason, Notes: form.elements.notes.value.trim() || null,
          DemandNo: isChild ? demand : null, ProdDate: isChild ? prodDate : null,
        }),
      });
      await load(); await loadPlans(); Admin.toast('Đã lưu chỉnh sửa.', 'ok');
    } catch (error) { status.textContent = error.message; }
    finally { save.disabled = false; }
  });
});
