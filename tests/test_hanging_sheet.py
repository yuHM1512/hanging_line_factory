import unittest
from datetime import date
from unittest.mock import patch

from app import flat_sheet, hanging_sheet, tv


def data_row(day, team, demand, slot, n='', groups=(), ak=''):
    r = [''] * 74
    r[1], r[2], r[3], r[6], r[13], r[36], r[73] = day, team, demand, slot, n, ak, demand
    for g, values in enumerate(groups):
        r[16 + 4 * g:20 + 4 * g] = list(values)
    return r


class HangingParseTests(unittest.TestCase):
    def test_groups_by_mother_demand_and_skips_bad_rows(self):
        rows = [
            data_row('05/11/2026', 'U2 - L1', 'PL-A', '09H30', n='2', groups=[('C4', '25', '2', 'cap')]),
            data_row('05/11/2026', 'U2 - L1', 'PL-A', '09H30', n='3'),          # nhập lại: dòng sau thắng
            data_row('05/11/2026', 'U2 - L3', 'PL-B', '11H30'),
            data_row('bad date', 'U2 - L3', 'PL-B', '11H30'),
            data_row('05/11/2026', 'U2 - L3', 'PL-B', '12H00'),
            data_row('01/01/2026', 'U2 - L3', 'PL-OLD', '09H30'),               # ngoài cửa sổ ~2 tháng
        ]
        result = {h['demand']: h for h in flat_sheet.hanging_quality(rows)}
        self.assertEqual(set(result), {'PL-A', 'PL-B'})
        self.assertEqual(len(result['PL-A']['reports']), 1)
        self.assertEqual(result['PL-A']['reports'][0]['quality']['defect_qty'], 3)
        self.assertEqual(result['PL-A']['teams'], ['U2 - L1'])
        self.assertEqual(result['PL-B']['reports'][0]['slot'], 1)


class HangingTV3Tests(unittest.TestCase):
    def snap(self):
        rows = [
            data_row('05/11/2026', 'U2 - L1', 'PL-A', '09H30', n='2', groups=[('C4', '25', '2', 'cap')]),
            data_row('05/11/2026', 'U2 - L2', 'PL-A', '09H30', n='9', groups=[('X', '1', '9', '')]),
            data_row('05/11/2026', 'U2 - L1', 'PL-A', '11H30', n='1', ak='3'),
        ]
        return dict(hanging=flat_sheet.hanging_quality(rows), synced_at='stamp', sync_error=None)

    def test_unmapped_mono_reports_message(self):
        with patch.object(hanging_sheet, 'mapped_demand', return_value=None):
            q, meta = hanging_sheet.tv3_quality('376556-1', date(2026, 11, 5), 1)
        self.assertEqual(q['status'], 'empty')
        self.assertIn('chưa được gán', meta['qc_message'])

    def test_mapped_mono_uses_own_line_rows(self):
        with patch.object(hanging_sheet, 'mapped_demand', return_value='PL-A'), \
             patch.object(flat_sheet, 'snapshot', return_value=self.snap()):
            q, meta = hanging_sheet.tv3_quality('376556-1', date(2026, 11, 5), 1)
            other_day, _ = hanging_sheet.tv3_quality('376556-1', date(2026, 11, 6), 1)
        self.assertEqual(meta['sheet_demand'], 'PL-A')
        self.assertIsNone(meta['qc_message'])
        self.assertEqual(q['defects_day'], 3)          # tổ L2 không tính
        self.assertEqual(q['window'], '11H30')
        self.assertEqual([w['window'] for w in q['windows']], ['09H30', '11H30'])
        self.assertEqual(q['windows'][0]['rows'][0]['type'], 'C4')
        self.assertEqual(other_day['status'], 'empty')

    def test_api_tv3_hanging_reads_sheet_with_msd_output(self):
        plan = dict(FirstHangDate=date(2026, 11, 1), LDBienChe=40, SoDonHang='376556-1', LineNoOut=1,
                    StyleNo='376556', Customer='c', PhanLoaiDH='Mới')
        with patch.object(tv, '_resolve_plan_full', return_value=plan), \
             patch.object(tv, '_workers_count', return_value=40), \
             patch.object(tv, '_daily_output_for_configured_last_cluster', return_value=97), \
             patch.object(tv, '_fetch_qlcl_tv3') as qlcl, \
             patch.object(hanging_sheet, 'mapped_demand', return_value='PL-A'), \
             patch.object(flat_sheet, 'snapshot', return_value=self.snap()):
            result = tv.api_tv3('376556-1', date(2026, 11, 5))
        qlcl.assert_not_called()
        self.assertEqual(result['source'], 'hanging_sheet')
        self.assertEqual(result['header']['MaDonKH'], 'PL-A')
        self.assertEqual(result['kpi']['TongDat'], 97)
        self.assertEqual(result['kpi']['TongLoi'], 3)
        self.assertEqual(result['kpi']['TyLeLoi'], 3.0)
        self.assertEqual(len(result['quality']['windows']), 2)


if __name__ == '__main__':
    unittest.main()
