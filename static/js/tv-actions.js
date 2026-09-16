/* Choose CAP entries by report day, not by the latest production milestone. */
const TVActions = {
  select(rows, reportDate, now = new Date()) {
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
    }).formatToParts(now).map(p => [p.type, p.value]));
    const today = `${parts.year}-${parts.month}-${parts.day}`;
    const minutes = Number(parts.hour) * 60 + Number(parts.minute);
    const populated = (rows || []).filter(r => Number(r.Slot) >= 1 && Number(r.Slot) <= 5 &&
      [r.RootCause, r.CAPAction].some(v => String(v ?? '').trim()))
      .sort((a, b) => Number(a.Slot) - Number(b.Slot));
    if (reportDate < today || (reportDate === today && minutes >= 17 * 60)) return populated;
    if (reportDate > today || minutes < 7 * 60 + 30) return [];
    const currentSlot = [570, 690, 870, 990].filter(end => minutes >= end).length + 1;
    return populated.filter(r => Number(r.Slot) <= currentSlot).slice(-1);
  }
};
if (typeof module !== 'undefined') module.exports = TVActions;
