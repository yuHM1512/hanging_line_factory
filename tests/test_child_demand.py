import unittest
from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app import admin, tv


PLAN = {
    'PlanMaster_guid': 'guid-1', 'MONo': 'MO-1', 'SoDonHang': '#ORDER',
    'StyleNo': 'STYLE', 'LineNoOut': 2, 'FirstHangDate': date(2026, 9, 1),
    'BaseSLKH': 10000, 'SLKH': 10500, 'DailyAim': 500, 'Customer': 'C',
    'NhuCauMe': 'MOTHER', 'LatestDemand': 'ORDER', 'DMKT': 10, 'PhanLoaiDH': 'Vest',
    'LDBienChe': 40, 'SAM': 0, 'OWE_Target': None,
    'MeFirstHangDate': date(2026, 9, 1), 'Cluster': [], 'POs': [],
}
KCS = {
    'cum': {'Qty': 5000, 'Def': 0}, 'today': {'Qty': 500, 'Def': 0},
    'last_day_output': 500, 'hourly': {i: 100 for i in range(1, 6)},
}
TARGET = {'target': 500, 'day_n': 1, 'ndsx_sec': 0, 'ndsx_level': 0, 'ratio': 1, 'overridden': False}


def run_tv1(child):
    with patch.object(tv, '_resolve_plan_full', return_value=dict(PLAN)), \
            patch.object(tv, 'get_holidays', return_value=set()), \
            patch.object(tv, '_kcs_bulk', return_value=KCS), \
            patch.object(tv, '_workers_count', return_value=40), \
            patch.object(tv, 'compute_day_target', return_value=TARGET), \
            patch.object(tv, '_child_demand_for_date', return_value=child) as lookup, \
            patch.object(tv.db, 'query', return_value=[]):
        result = tv.api_tv1('MO-1', date(2026, 9, 10))
    return result, lookup


class ChildDemandTVTests(unittest.TestCase):
    def test_lookup_filters_by_prod_date_and_mother(self):
        with patch.object(tv.db, 'query', return_value=[{'DemandNo': 'KH7', 'ProdDate': date(2026, 9, 8)}]) as q:
            row = tv._child_demand_for_date('MOTHER', date(2026, 9, 10))
        self.assertEqual(row['DemandNo'], 'KH7')
        sql, params = q.call_args.args
        self.assertIn('pa.ProdDate <= ?', sql)
        self.assertIn('ORDER BY pa.ProdDate DESC', sql)
        self.assertEqual(params, ('MOTHER', date(2026, 9, 10)))

    def test_lookup_survives_missing_migration(self):
        with patch.object(tv.db, 'query', side_effect=RuntimeError('Invalid column name DemandNo')):
            self.assertIsNone(tv._child_demand_for_date('MOTHER', date(2026, 9, 10)))

    def test_lookup_without_mother(self):
        with patch.object(tv.db, 'query') as q:
            self.assertIsNone(tv._child_demand_for_date(None, date(2026, 9, 10)))
        q.assert_not_called()

    def test_tv1_shows_child_from_prod_date(self):
        result, lookup = run_tv1({'DemandNo': '#KH7', 'ProdDate': date(2026, 9, 8)})
        self.assertEqual(lookup.call_args.args, ('MOTHER', date(2026, 9, 10)))
        self.assertEqual(result['header']['LatestDemand'], 'KH7')
        self.assertEqual(result['header']['LatestDemandFrom'], '2026-09-08')
        self.assertEqual(result['header']['MaDonKH'], 'ORDER')

    def test_tv1_keeps_old_demand_when_no_child_due(self):
        result, _ = run_tv1(None)
        self.assertEqual(result['header']['LatestDemand'], 'ORDER')
        self.assertIsNone(result['header']['LatestDemandFrom'])


class FakeCursor:
    def __init__(self, fetches):
        self.fetches = list(fetches)
        self.executed = []
        self.rowcount = 1

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        return self

    def fetchone(self):
        return self.fetches.pop(0) if self.fetches else None


def fake_conn(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor

    @contextmanager
    def cm():
        yield conn
    return cm


class ChildDemandAdminTests(unittest.TestCase):
    user = {'UserID': 'u1'}

    def body(self, **kw):
        data = {'DemandNo': ' KH7 ', 'Qty': 500, 'ProdDate': '2026-09-08'}
        data.update(kw)
        return admin.ChildDemandIn.model_validate(data) if hasattr(admin.ChildDemandIn, 'model_validate') \
            else admin.ChildDemandIn.parse_obj(data)

    def test_create_inserts_child_row(self):
        cur = FakeCursor([(1,), None])
        with patch.object(admin.db, 'get_conn', fake_conn(cur)), \
                patch.object(admin, '_actor_id', return_value='u1'):
            admin.api_plan_child_demand_create('guid-1', self.body(), self.user)
        sql, params = cur.executed[-1]
        self.assertIn('DemandNo, ProdDate', sql)
        self.assertEqual(params[:6], ('guid-1', 500, 'Nhu cầu con', None, 'KH7', date(2026, 9, 8)))

    def test_create_rejects_duplicate_name(self):
        cur = FakeCursor([(1,), (1,)])
        with patch.object(admin.db, 'get_conn', fake_conn(cur)), \
                patch.object(admin, '_actor_id', return_value='u1'):
            with self.assertRaises(HTTPException) as ctx:
                admin.api_plan_child_demand_create('guid-1', self.body(), self.user)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_child_qty_must_be_positive(self):
        with self.assertRaises(Exception):
            self.body(Qty=0)

    def test_history_falls_back_before_migration(self):
        old_rows = [{'Adjustment_guid': 'a', 'DeltaQty': 100, 'DemandNo': None, 'ProdDate': None}]
        with patch.object(admin.db, 'query',
                          side_effect=[RuntimeError("Invalid column name 'DemandNo'."), old_rows]) as q:
            self.assertEqual(admin.api_plan_adjustment_list('guid-1'), old_rows)
        self.assertIn('NULL AS DemandNo', q.call_args.args[0])

    def test_history_reraises_other_errors(self):
        with patch.object(admin.db, 'query', side_effect=RuntimeError('timeout')):
            with self.assertRaises(RuntimeError):
                admin.api_plan_adjustment_list('guid-1')

    def test_update_validation(self):
        self.assertEqual(admin._validate_child_fields(None, None, -5), (None, None))
        self.assertEqual(admin._validate_child_fields(' KH7 ', date(2026, 9, 8), 5), ('KH7', date(2026, 9, 8)))
        with self.assertRaises(HTTPException):
            admin._validate_child_fields('KH7', None, 5)
        with self.assertRaises(HTTPException):
            admin._validate_child_fields('KH7', date(2026, 9, 8), -5)


if __name__ == '__main__':
    unittest.main()
