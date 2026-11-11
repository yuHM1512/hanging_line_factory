import unittest
from unittest.mock import patch

from app import tv


class TV1Cluster6FilterTests(unittest.TestCase):
    def setUp(self):
        tv._CLUSTER6_QC_CACHE.clear()

    def test_uses_cluster6_route_step_and_max_stno(self):
        plan = {"Cluster": [
            {"ClusterOrder": 1, "RouteStepOdr": 1, "Role": "first"},
            {"ClusterOrder": 6, "RouteStepOdr": 40, "Role": "normal"},
        ]}
        with patch.object(tv.db, "query", return_value=[{"SeqNo": "45", "StNo": 32}]) as q, \
             patch.object(tv, "_last_qc_filter") as legacy:
            self.assertEqual(tv._tv1_qc_filter("MO-1", plan), ("45", 32))
        legacy.assert_not_called()
        sql, params = q.call_args.args
        self.assertNotIn("StRole", sql)
        self.assertNotIn("IsLastSeq", sql)
        self.assertIn("ORDER BY cs.Odr DESC, st.StNo DESC", sql)
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


if __name__ == "__main__":
    unittest.main()
