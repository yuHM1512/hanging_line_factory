import unittest
from datetime import date
from unittest.mock import patch

from app import tv


class TV4BulkTests(unittest.TestCase):
    def setUp(self):
        tv._CLUSTER6_QC_CACHE.clear()

    def test_tv4_uses_cluster6_station_and_bounded_queries(self):
        plan = {
            "PlanMaster_guid": "g1", "NhuCauMe": "ME", "DMKT": 6.6, "LDBienChe": 70,
            "PhanLoaiDH": "Mới", "LineNoOut": 6, "SoDonHang": "#X", "StyleNo": "S",
            "Customer": "C",
            "Cluster": [{"ClusterOrder": 1, "RouteStepOdr": 1, "Role": "first"},
                        {"ClusterOrder": 6, "RouteStepOdr": 40, "Role": "normal"}],
        }
        calls = []

        def fake_query(sql, params=None):
            calls.append(sql)
            if "SUM(CASE WHEN pm.SLKH" in sql:
                return [{"Total": 1000, "FirstDate": date(2026, 11, 2)}]
            if "SELECT MONo FROM app.tPlanMaster" in sql:
                return [{"MONo": "MO-1"}]
            if "ClusterSeqs" in sql:
                self.assertNotIn("StRole", sql)
                return [{"SeqNo": "45", "StNo": 32}]
            if "GROUP BY rw.ShtDate" in sql:
                self.assertEqual(params[:3], ("MO-1", "45", 32))
                return [{"ShtDate": date(2026, 11, 2), "Q": 100},
                        {"ShtDate": date(2026, 11, 3), "Q": 150}]
            if "tProductionCurve" in sql:
                return [{"DayN": 1, "Ratio": 0.5}, {"DayN": 3, "Ratio": 1.0}]
            if "tTargetOverride" in sql:
                return [{"DayN": 2, "TargetQty": 222}]
            if "SELECT TOP 1 [LineNo]" in sql:
                return [{"L": 6}]
            if "tDailyHeadcount" in sql:
                return [{"ShtDate": date(2026, 11, 3), "Headcount": 60}]
            raise AssertionError("unexpected query: " + sql)

        with patch.object(tv, "_resolve_plan_full", return_value=plan), \
             patch.object(tv, "get_holidays", return_value=set()), \
             patch.object(tv.db, "query", side_effect=fake_query):
            res = tv.api_tv4(mono="MO-1", the_date=date(2026, 11, 4))

        days = res["days"]
        self.assertEqual([d["Actual"] for d in days[:3]], [100, 150, 0])
        self.assertEqual(days[0]["Workers"], 70)
        self.assertEqual(days[1]["Workers"], 60)
        self.assertEqual(days[0]["TargetNS"], round(6.6 * 70 * 0.5))
        self.assertEqual(days[1]["TargetNS"], 222)            # override DayN<=2
        self.assertEqual(days[3]["TargetNS"], 222)            # override vẫn áp dụng
        self.assertIsNone(days[-1]["Actual"])                 # ngày tương lai
        self.assertLessEqual(len(calls), 10)                  # không còn N query/ngày


if __name__ == "__main__":
    unittest.main()
