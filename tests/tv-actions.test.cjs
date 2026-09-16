const {test} = require('node:test');
const assert = require('node:assert/strict');
const actions = require('../static/js/tv-actions.js');
const rows = [
  {Slot: 5, CAPAction: 'Cuối ngày'},
  {Slot: 1, RootCause: 'Thiếu vật tư'},
  {Slot: 2, RootCause: '  ', CAPAction: '\n'},
  {Slot: 3, CAPAction: 'Bổ sung vật tư'},
  {Slot: 4, RootCause: '', CAPAction: ''}
];
const select = (time, data=rows) => actions.select(data, '2026-09-15', new Date(time)).map(r=>Number(r.Slot));
test('historical and end of day show only populated milestones in order', () => {
  assert.deepEqual(select('2026-09-16T09:00:00+07:00'), [1,3,5]);
  assert.deepEqual(select('2026-09-15T17:00:00+07:00'), [1,3,5]);
});
test('live view keeps latest populated action when newer production slots are empty', () => {
  assert.deepEqual(select('2026-09-15T10:00:00+07:00'), [1]);
  assert.deepEqual(select('2026-09-15T15:00:00+07:00'), [3]);
  assert.deepEqual(select('2026-09-15T16:45:00+07:00'), [5]);
});
test('new entry, clearing entry, blank day, future day and shift start', () => {
  assert.deepEqual(select('2026-09-15T15:00:00+07:00', [...rows,{Slot:4,RootCause:'Mới'}]), [4]);
  assert.deepEqual(select('2026-09-15T15:00:00+07:00', rows.filter(r=>r.Slot!==3)), [1]);
  assert.deepEqual(select('2026-09-15T18:00:00+07:00', []), []);
  assert.deepEqual(select('2026-09-14T18:00:00+07:00'), []);
  assert.deepEqual(select('2026-09-15T07:29:00+07:00'), []);
});
