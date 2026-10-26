(function () {
  'use strict';

  const tooltip = document.createElement('div');
  tooltip.id = 'tv-calc-tooltip';
  tooltip.innerHTML = `
    <div class="tv-tt-title"></div>
    <div class="tv-tt-desc"></div>
    <div class="tv-tt-formula"></div>
    <div class="tv-tt-example"></div>
    <div class="tv-tt-note"></div>`;
  document.body.appendChild(tooltip);

  const text = (el, selector) => {
    const node = selector ? el.querySelector(selector) : el;
    return node ? node.textContent.trim().replace(/\s+/g, ' ') : '';
  };
  const num = (value) => {
    const raw = String(value || '').replace(/[^0-9,.-]/g, '');
    if (!raw) return NaN;
    return Number(raw.includes(',') ? raw.replace(/\./g, '').replace(',', '.') : raw.replace(/\./g, ''));
  };
  const fmt = (value) => Number.isFinite(value) ? value.toLocaleString('vi-VN') : '—';
  const ratio = (actual, target) => Number.isFinite(actual) && Number.isFinite(target) && target
    ? `${(actual / target * 100).toFixed(1)}%` : '—';

  function markTargets(root) {
    const selectors = [
      '.hdr .hdr-line', '.hdr .fld',
      '.hero', '.stat', '.hour', '.rc', '.ehd',
      '.cl', '.chartcard', '.kp', '.left-qc-body', '.right-qc-body',
      '#row-workers', '#row-mix'
    ];
    root.querySelectorAll(selectors.join(',')).forEach((el) => {
      if (!el.classList.contains('tv-calc-target')) el.classList.add('tv-calc-target');
    });
  }

  function targetData(el) {
    const title = document.title || 'TV dashboard';
    const data = {
      title: 'Thông tin hiển thị',
      desc: 'Giá trị được lấy từ dữ liệu đang hiển thị trên màn hình.',
      formula: 'Đọc trực tiếp từ dữ liệu hiện tại của ô này.',
      example: text(el),
      note: 'Số liệu và phép tính được cập nhật lại sau mỗi lần refresh dữ liệu.'
    };

    if (el.matches('.hdr .hdr-line, .hdr .fld')) {
      data.title = text(el, '.k, .lk') || 'Thông tin header';
      data.example = text(el, '.v, .lv, .style');
      data.formula = 'Thông tin được lấy trực tiếp từ đơn hàng, chuyền và ca đang theo dõi.';
      return data;
    }

    if (el.classList.contains('hero')) {
      const plan = num(text(el, '#hero-kh, .h-rows .r:nth-child(1) .rv'));
      const actual = num(text(el, '#hero-th, .h-rows .r:nth-child(2) .rv'));
      const remain = num(text(el, '#hero-remain, .h-rows .r:nth-child(3) .rv'));
      data.title = 'Tiến độ tổng';
      data.formula = `% hoàn thành = Thực hiện / Kế hoạch × 100% = ${fmt(actual)} / ${fmt(plan)} × 100% = ${text(el, '.pct') || ratio(actual, plan)}`;
      data.example = `Kế hoạch ${fmt(plan)} SP − thực hiện ${fmt(actual)} SP = còn ${fmt(remain)} SP.`;
      return data;
    }

    if (el.classList.contains('stat')) {
      const label = text(el, '.s-k');
      const values = [...el.querySelectorAll('.s-sub .ssv')].map(x => num(x.textContent));
      const current = text(el, '.s-pct');
      data.title = label || 'Chỉ số sản xuất';
      if (label.includes('SL Ngày')) {
        data.formula = `% đạt ngày = Thực hiện / Kế hoạch × 100% = ${fmt(values[1])} / ${fmt(values[0])} × 100% = ${current}`;
        data.example = `Kế hoạch ${fmt(values[0])} SP; thực hiện ${fmt(values[1])} SP; chênh lệch ${fmt(values[1] - values[0])} SP.`;
      } else if (label.includes('Takt')) {
        data.formula = `Mức đạt nhịp = Nhịp kế hoạch / Nhịp thực tế × 100% = ${fmt(values[0])} / ${fmt(values[1])} × 100% = ${current}`;
        data.example = `Kế hoạch ${fmt(values[0])} giây/SP; thực tế ${fmt(values[1])} giây/SP.`;
      } else if (label.includes('OWE')) {
        data.formula = 'OWE = (Thời gian chuẩn × Sản lượng) / (Thời gian làm việc × Lao động) × 100%.';
        data.example = `Thực tế ${current}; mục tiêu ${text(el, '.ssv') || '—'}.`;
      } else if (label.includes('lỗi')) {
        data.formula = `Tỷ lệ lỗi = Sản phẩm lỗi / Tổng sản phẩm đã kiểm × 100% = ${current}.`;
        data.example = `Thực tế ${current}; ngưỡng cho phép ${text(el, '.ssv') || '—'}.`;
      } else {
        data.example = `Giá trị thực tế: ${current}.`;
      }
      return data;
    }

    if (el.classList.contains('hour')) {
      const values = [...el.querySelectorAll('.hv')].map(x => num(x.textContent));
      const slot = text(el, '.h-time');
      data.title = `Sản lượng khung ${slot}`;
      data.formula = `% đạt khung giờ = Thực hiện / Kế hoạch × 100% = ${fmt(values[1])} / ${fmt(values[0])} × 100% = ${ratio(values[1], values[0])}`;
      data.example = `${slot}: kế hoạch ${fmt(values[0])} SP; thực hiện ${fmt(values[1])} SP; chênh lệch ${fmt(values[1] - values[0])} SP.`;
      return data;
    }

    if (el.classList.contains('cl')) {
      const actual = num(text(el, '.cl-big'));
      const targetEl = [...document.querySelectorAll('.hdr .fld')].find(x => /mục tiêu/i.test(text(x, '.k')));
      const targetValue = num(text(targetEl, '.v'));
      data.title = `${text(el, '.cl-name')} · Sản lượng hiện tại`;
      data.formula = `Mức đạt cụm = Sản lượng cụm / Mục tiêu mốc × 100% = ${fmt(actual)} / ${fmt(targetValue)} × 100% = ${ratio(actual, targetValue)}`;
      data.example = `Hôm nay ${fmt(actual)} SP; lũy kế ${text(el, '.cl-sub .v') || '—'} SP; trạng thái ${text(el, '.pct-chip') || '—'}.`;
      return data;
    }

    if (el.classList.contains('kp')) {
      const label = text(el, '.k');
      const value = text(el, '.kp-big');
      data.title = label || 'Chỉ số chất lượng';
      if (/tỉ lệ lỗi/i.test(label)) data.formula = `Tỷ lệ lỗi = Tổng lỗi / Tổng kiểm × 100% = ${value} (so với target ${text(el, '.kp-sub') || '—'}).`;
      else if (/cảnh báo/i.test(label)) data.formula = 'Cảnh báo = số cụm có từ 3 sản phẩm liên tiếp cùng loại lỗi.';
      else data.formula = 'Tổng hợp từ dữ liệu kiểm tra chất lượng theo ngày đang chọn.';
      data.example = `Giá trị thực tế đang hiển thị: ${value}.`;
      return data;
    }

    if (el.classList.contains('left-qc-body')) {
      const values = [...el.querySelectorAll('.slot-col')].map((slot, i) => `${i + 1}: ${text(slot, '.bar-val') || '0%'} / ${text(slot, '.slot-sp') || '—'}`);
      data.title = 'Tỷ lệ lỗi theo mốc giờ';
      data.formula = 'Tỷ lệ lỗi từng mốc = Số lỗi tại mốc / Sản lượng đã kiểm tại mốc × 100%.';
      data.example = `Số thực tế theo mốc: ${values.join(' · ')}.`;
      return data;
    }

    if (el.id === 'row-workers') {
      data.title = 'Số lao động theo ngày';
      data.formula = 'Mục tiêu ngày = ĐMKT × Số lao động × Tỷ lệ năng suất theo ngày.';
      data.example = `Lao động đang hiển thị: ${[...el.querySelectorAll('td')].slice(1).map(x => text(x)).join(' · ')}.`;
      return data;
    }

    if (el.id === 'row-mix') {
      const current = el.querySelector('.current-col');
      const actual = num(text(current, '.mix-actual'));
      const target = num(text(current, '.mix-target'));
      data.title = 'Ra chuyền / Năng suất theo ngày';
      data.formula = `% đạt ngày = Thực tế / Mục tiêu × 100% = ${fmt(actual)} / ${fmt(target)} × 100% = ${ratio(actual, target)}`;
      data.example = `Ngày hiện tại: ${fmt(actual)} SP / ${fmt(target)} SP; ${text(current, '.mix-pct') || 'chưa có thực tế'}.`;
      return data;
    }

    return data;
  }

  function position(event) {
    const pad = 14;
    const rect = tooltip.getBoundingClientRect();
    let left = event.clientX + pad;
    let top = event.clientY + pad;
    if (left + rect.width > innerWidth - 12) left = event.clientX - rect.width - pad;
    if (top + rect.height > innerHeight - 12) top = event.clientY - rect.height - pad;
    tooltip.style.left = `${Math.max(12, left)}px`;
    tooltip.style.top = `${Math.max(12, top)}px`;
  }

  let active = null;
  function show(el, event) {
    active = el;
    const data = targetData(el);
    tooltip.querySelector('.tv-tt-title').textContent = data.title;
    tooltip.querySelector('.tv-tt-desc').textContent = data.desc;
    tooltip.querySelector('.tv-tt-formula').textContent = data.formula;
    tooltip.querySelector('.tv-tt-example').innerHTML = `<b>Số liệu tại thời điểm xem:</b> ${data.example}`;
    tooltip.querySelector('.tv-tt-note').textContent = `💡 ${data.note}`;
    tooltip.classList.add('is-visible');
    position(event);
  }

  document.addEventListener('mouseover', (event) => {
    const el = event.target.closest('.tv-calc-target');
    if (!el) return;
    if (el !== active) show(el, event);
  });
  document.addEventListener('mousemove', (event) => {
    if (active) position(event);
  });
  document.addEventListener('mouseout', (event) => {
    if (active && !event.relatedTarget?.closest?.('.tv-calc-target')) {
      active = null;
      tooltip.classList.remove('is-visible');
    }
  });

  markTargets(document);
  new MutationObserver(() => markTargets(document)).observe(document.body, { childList: true, subtree: true });
})();
