/* TV-3: nút icon nhỏ, mờ ở góc trái dưới để chuyển nguồn QC Sheet <-> QLCL (giai đoạn test nội bộ). */
(function () {
  const params = new URLSearchParams(location.search);
  const isQlcl = params.get('src') === 'qlcl';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = '⇄';
  btn.title = isQlcl ? 'Nguồn QC: QLCL — bấm để về Sheet' : 'Nguồn QC: Sheet — bấm để xem QLCL';
  btn.setAttribute('aria-label', btn.title);
  btn.style.cssText = [
    'position:fixed', 'left:14px', 'bottom:14px', 'z-index:999',
    'width:28px', 'height:28px', 'padding:0', 'border-radius:50%',
    'border:1px solid rgba(255,255,255,.25)', 'background:rgba(15,30,60,.55)',
    'color:#fff', 'font-size:14px', 'line-height:26px', 'cursor:pointer',
    'opacity:.22', 'transition:opacity .2s',
    isQlcl ? 'box-shadow:0 0 0 2px rgba(89,199,140,.85)' : '',
  ].join(';');
  btn.addEventListener('mouseenter', () => { btn.style.opacity = '1'; });
  btn.addEventListener('mouseleave', () => { btn.style.opacity = '.22'; });
  btn.addEventListener('click', () => {
    if (isQlcl) params.delete('src'); else params.set('src', 'qlcl');
    location.search = params.toString();
  });
  document.body.appendChild(btn);
})();
