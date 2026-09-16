import unittest
from datetime import date
from unittest.mock import patch

from app import flat_tv, tv


class SharedTVTests(unittest.TestCase):
    def test_all_four_routes_dispatch_flat_mother_without_mes_lookup(self):
        with patch.object(flat_tv, 'dashboard', return_value={'source':'flat_line_sheet'}) as adapter, patch.object(tv, '_resolve_plan_full') as mes:
            for screen in range(1,5):
                result = getattr(tv, f'api_tv{screen}')('flat:mother', date(2026,9,12))
                self.assertEqual(result['source'], 'flat_line_sheet')
                adapter.assert_called_with(screen,'flat:mother',date(2026,9,12))
            mes.assert_not_called()

    def test_flat_plans_join_existing_line_and_keep_mother_identity(self):
        p = dict(demand='mother',style='s',team='U2 - L6',customer='c',quantity=100,first='2026-09-01',reports=[dict(day='2026-09-12')])
        with patch('app.flat_sheet.snapshot',return_value={'plans':[p]}):
            rows=flat_tv.plans(6)
            self.assertEqual(rows[0]['MONo'],'flat:mother')
            self.assertTrue(rows[0]['IsFlat'])
            self.assertEqual(flat_tv.plans(3),[])
            with patch.object(tv.db,'query',return_value=[{'LineNo':3},{'LineNo':6}]):
                self.assertEqual(tv.api_tv_plan_lines(),[{'line_no':3},{'line_no':6}])

    def test_qc_unknown_stays_unknown_and_report_date_is_preserved(self):
        payload=dict(plan=dict(team='U2-L6',demand='mother',style='s',customer='c',first='2026-09-01',category='Lặp lại'),
            qc=dict(status='empty',rate=None),workers=44,wip=50,tpt=12,target=100,
            selected='2026-09-12',requested='2026-09-15',cutoff='09H30',synced_at='stamp',warnings=[],sync_error=None,
            daily=[10]*6,cumulative=[50]*6,slots=[dict(label='09H30',actual=10)])
        with patch('app.flat_sheet.dashboard_api',return_value=payload):
            result=flat_tv.dashboard(3,'flat:mother',date(2026,9,15))
        self.assertEqual(result['header']['ReportDate'],'2026-09-12')
        self.assertEqual(result['kpi']['TongKiem'],10)
        self.assertIsNone(result['kpi']['TongLoi'])
        self.assertIsNone(result['kpi']['DefectStatus'])
        self.assertIsNone(result['kpi']['CanhBaoCount'])
        self.assertEqual(result['slots'],[])


if __name__ == '__main__':
    unittest.main()
