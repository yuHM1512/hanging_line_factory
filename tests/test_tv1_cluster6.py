import unittest
from unittest.mock import patch

from app import tv


class TV1Cluster6FilterTests(unittest.TestCase):
    def setUp(self):
        tv._CLUSTER6_QC_CACHE.clear()

    def test_uses_cluster6_last_seq_all_stations(self):
        plan = {"Cluster": [
            {"ClusterOrder": 1, "RouteStepOdr": 1, "Role": "first"},
            {"ClusterOrder": 6, "RouteStepOdr": 40, "Role": "normal"},
        ]}
        with patch.object(tv.db, "query", return_value=[{"SeqNo": "45"}]) as q, \
             patch.object(tv, "_last_qc_filter") as legacy:
            self.assertEqual(tv._tv1_qc_filter("MO-1", plan), ("45", None))
        legacy.assert_not_called()
        sql, params = q.call_args.args
        self.assertNotIn("StRole", sql)
        self.assertNotIn("IsLastSeq", sql)
        self.assertIn("ORDER BY cs.Odr DESC", sql)
        self.assertNotIn("StNo", sql)
        self.assertEqual(params, ("MO-1", 40, "MO-1"))

    def test_falls_back_without_cluster6_route(self):
        plan = {"Cluster": [{"ClusterOrder": 6, "RouteStepOdr": 0, "Role": "last"}]}
        with patch.object(tv, "_last_qc_filter", return_value=("9", 1)) as legacy, \
             patch.object(tv.db, "query") as q:
            self.assertEqual(tv._tv1_qc_filter("MO-1", plan), ("9", 1))
        legacy.assert_called_once_with("MO-1")
        q.assert_not_called()

    def test_no_scans_returns_none(self):
        plan = {"Cluster": [{"ClusterOrder": 6, "RouteStepOdr": 40, "Role": "last"}]}
        with patch.object(tv.db, "query", return_value=[]):
            self.assertEqual(tv._tv1_qc_filter("MO-1", plan), (None, None))


    def test_bulk_sums_all_stations_when_stno_none(self):
        with patch.object(tv.db, "query", return_value=[]) as q:
            tv._kcs_bulk("MO-1", __import__("datetime").date(2026, 11, 12), ("114", None))
        sql, params = q.call_args.args
        self.assertNotIn("st.StNo = ?", sql)
        self.assertIn("rw.QcOdr = 0", sql)          # không đếm lần QC tái kiểm
        self.assertEqual(params[:2], ("114", "MO-1"))

    def test_output_kcs_all_stations_keeps_qcodr_filter(self):
        with patch.object(tv.db, "query", return_value=[{"Qty": 0, "DefQty": 0}]) as q:
            d = __import__("datetime").date(2026, 11, 12)
            tv._output_kcs("MO-1", d, d, ("114", None))
        sql, params = q.call_args.args
        self.assertIn("rw.QcOdr = 0", sql)
        self.assertNotIn("st.StNo = ?", sql)

    def test_bulk_keeps_station_filter_for_legacy(self):
        with patch.object(tv.db, "query", return_value=[]) as q:
            tv._kcs_bulk("MO-1", __import__("datetime").date(2026, 11, 12), ("114", 32))
        sql, params = q.call_args.args
        self.assertIn("st.StNo = ?", sql)
        self.assertEqual(params[:3], ("114", 32, "MO-1"))


if __name__ == "__main__":
    unittest.main()
