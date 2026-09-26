import unittest
from datetime import date
from unittest.mock import patch

from app import tv


class PlanAdjustmentTVTests(unittest.TestCase):
    def test_resolved_plan_uses_effective_quantity(self):
        plan = {
            'PlanMaster_guid': 'guid-1', 'MONo': 'MO-1', 'SoDonHang': '#ORDER',
            'StyleNo': 'STYLE', 'LineNoOut': 2, 'FirstHangDate': date(2026, 9, 1),
            'BaseSLKH': 10000, 'SLKH': 17008, 'DailyAim': 500, 'Customer': 'C',
            'NhuCauMe': 'MOTHER', 'DMKT': 10, 'PhanLoaiDH': 'Vest',
            'LDBienChe': 40, 'LuyKeChuyenTiep': 0, 'SAM': None,
            'OWE_Target': None, 'MeFirstHangDate': date(2026, 9, 1),
        }
        with patch.object(tv.db, 'query', side_effect=[[plan], [], []]) as query:
            result = tv._resolve_plan_full('MO-1')

        self.assertEqual(result['BaseSLKH'], 10000)
        self.assertEqual(result['SLKH'], 17008)
        self.assertIn('app.tPlanAdjustment', query.call_args_list[0].args[0])

    def test_tv1_progress_uses_effective_quantity(self):
        plan = {
            'PlanMaster_guid': 'guid-1', 'MONo': 'MO-1', 'SoDonHang': '#ORDER',
            'StyleNo': 'STYLE', 'LineNoOut': 2, 'FirstHangDate': date(2026, 9, 1),
            'BaseSLKH': 10000, 'SLKH': 17008, 'DailyAim': 500, 'Customer': 'C',
            'NhuCauMe': 'MOTHER', 'DMKT': 10, 'PhanLoaiDH': 'Vest',
            'LDBienChe': 40, 'SAM': 0, 'OWE_Target': None,
            'MeFirstHangDate': date(2026, 9, 1), 'Cluster': [], 'POs': [],
        }
        kcs = {
            'cum': {'Qty': 5000, 'Def': 0}, 'today': {'Qty': 500, 'Def': 0},
            'last_day_output': 500, 'hourly': {i: 100 for i in range(1, 6)},
        }
        target = {
            'target': 500, 'day_n': 1, 'ndsx_sec': 0,
            'ndsx_level': 0, 'ratio': 1, 'overridden': False,
        }
        with patch.object(tv, '_resolve_plan_full', return_value=plan), \
                patch.object(tv, 'get_holidays', return_value=set()), \
                patch.object(tv, '_kcs_bulk', return_value=kcs), \
                patch.object(tv, '_workers_count', return_value=40), \
                patch.object(tv, 'compute_day_target', return_value=target), \
                patch.object(tv.db, 'query', return_value=[]):
            result = tv.api_tv1('MO-1', date(2026, 9, 10))

        self.assertEqual(result['hero']['SLKH'], 17008)
        self.assertEqual(result['hero']['Remain'], 12008)
        self.assertEqual(result['hero']['Pct'], 29.4)


if __name__ == '__main__':
    unittest.main()
