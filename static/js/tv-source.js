/* Source metadata for the shared TV templates. Layout remains source-independent. */
window.TVSource = {
  apply(d) {
    if (d.source !== 'flat_line_sheet') return;
    const el = id => document.getElementById(id);
    const text = (id, value) => { if (el(id)) el(id).textContent = value; };
    const neutral = (id, value, cls = 'chip neu') => {
      text(id, value);
      if (el(id)) { el(id).className = cls; el(id).style.color = 'var(--ink-2)'; }
    };
    text('h-line', `${d.header.To} (B)`);
    let note = el('source-note');
    if (!note) {
      note = document.createElement('span');
      note.id = 'source-note';
      const footer = el('ftr-time')?.parentElement;
      if (footer) footer.appendChild(note);
    }
    const day = d.report_date.split('-').reverse().join('/');
    note.textContent = ` · Báo cáo ${day} · ${d.cutoff || 'Chưa có mốc'}${d.sync_error ? ' · Đồng bộ lỗi' : ''}`;
    note.title = [...(d.warnings || []), d.sync_error || ''].filter(Boolean).join('\n');
    if (d.stats) {
      for (const [key, id] of [['DayQty','day'],['Takt','takt'],['OWE','owe'],['DefectRate','def']]) {
        if (d.stats[key].Pct == null) {
          neutral(`st-${id}-pct`, '—', 's-pct');
          neutral(`st-${id}-chip`, 'CHƯA CÓ DỮ LIỆU', 'pct-chip');
        }
      }
    }
    if (d.kpi) {
      text('qc-output-label', 'Tổng kiểm (Đạt + Lỗi)');
      text('qc-output-description', 'Đạt từ Sheet + sản phẩm lỗi QLCL');
      text('qc-slot-source', 'Lỗi / (Đạt Sheet + Lỗi QLCL) từng mốc');
      text('src-badge', d.qc_status === 'ok' ? 'Dữ liệu QC' : 'Chưa có dữ liệu QC');
      if (d.qc_status !== 'ok') neutral('src-badge', 'Chưa có dữ liệu QC', 'src-badge');
      if (d.kpi.TyLeLoi == null) {
        neutral('kpi-status-chip', 'CHƯA CÓ DỮ LIỆU');
        neutral('kpi-ty-le', '—', 'kp-big');
        neutral('sb-rate', '—', 'v');
      }
      if (d.kpi.CanhBaoCount == null) {
        text('kpi-canh-bao', '—');
        neutral('kpi-canh-bao-chip', 'CHƯA CÓ DỮ LIỆU');
        text('alert-area', 'Chưa có dữ liệu cảnh báo.');
      }
    }
  }
};
