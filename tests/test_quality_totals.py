import unittest
from contextlib import ExitStack
from datetime import date
from unittest.mock import patch
from app import tv, flat_tv
from app.quality import inspection


class QualityTotalsTests(unittest.TestCase):
    def test_passed_plus_defects_and_unknowns(self):
        self.assertEqual(inspection(174, 6), dict(dat=174, loi=6, kiem=180, pct=3.3))
        self.assertEqual(inspection(0, 6)['pct'], 100)
        self.assertEqual(inspection(174, 0)['pct'], 0)
        for passed, defects in [(None, 6), (174, None), (-20, 6), (0, 0)]:
            self.assertIsNone(inspection(passed, defects)['pct'])

    def test_hanging_uses_msd_as_passed_not_qlcl_total(self):
        plan = dict(FirstHangDate=None, LDBienChe=40, SoDonHang='order', LineNoOut=2, StyleNo='s', Customer='c')
        with ExitStack() as stack:
            for name, value in [('_resolve_plan_full', plan), ('_workers_count', 40),
                                ('_output_kcs', {'Qty': 999}),
                                ('_daily_output_for_configured_last_cluster', 174),
                                ('_hourly_output_for_configured_last_cluster', {1: 174}),
                                ('_fetch_qlcl_tv3', dict(found=True, total_kiem=9999, total_loi=6, slots=[dict(slot=1,loi=6)]))]:
                stack.enter_context(patch.object(tv, name, return_value=value))
            stack.enter_context(patch.object(tv.db, 'query', return_value=[]))
            result = tv.api_tv3('order', date(2026,9,17))
        self.assertEqual(result['kpi']['TongDat'], 174)
        self.assertEqual(result['kpi']['TongKiem'], 180)
        self.assertEqual(result['kpi']['TyLeLoi'], 3.3)
        self.assertEqual(result['slots'][0]['kiem'], 180)
        self.assertEqual(result['slots'][0]['pct'], 3.3)

    def test_flat_daily_and_slots_include_defective_garments(self):
        payload = dict(plan=dict(team='U2-L6',demand='mother',style='s',customer='c',first='2026-09-01',category='x'),
            qc=dict(status='ok',rate=99,defects=6,slots=[dict(slot=1,defects=6)],details=[],alerts=[]),
            workers=40,wip=0,tpt=1,target=100,selected='2026-09-17',requested='2026-09-17',cutoff='09H30',
            synced_at='stamp',warnings=[],sync_error=None,daily=[174]*6,cumulative=[174]*6,
            slots=[dict(label='09H30',actual=174),dict(label='11H30',actual=None)])
        with patch('app.flat_sheet.dashboard_api', return_value=payload):
            result = flat_tv.dashboard(3,'flat:mother',date(2026,9,17))
        self.assertEqual(result['kpi']['TongDat'], 174)
        self.assertEqual(result['kpi']['TongKiem'], 180)
        self.assertEqual(result['kpi']['TyLeLoi'], 3.3)
        self.assertEqual(result['slots'][0]['kiem'], 180)
        self.assertEqual(result['slots'][0]['pct'], 3.3)
        self.assertIsNone(result['slots'][1]['kiem'])
        self.assertIsNone(result['slots'][1]['pct'])
