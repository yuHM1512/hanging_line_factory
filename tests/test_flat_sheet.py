import unittest

from app.flat_sheet import LOCK, SyncBusy, daily_totals, headcount, key, sync


class FlatSheetAggregationTests(unittest.TestCase):
    def report(self, child, team, slot, bp, direct=40, indirect=4):
        return {
            "child": child,
            "team": team,
            "slot": slot,
            "source_row": slot + 2,
            "direct": direct,
            "indirect": indirect,
            "quantities": [bp, bp, bp, bp, bp, bp],
        }

    def test_last_cumulative_value_per_child_is_summed_for_mother(self):
        reports = [
            self.report("child-a", "U2 - L6", 0, 60),
            self.report("child-a", "U2 - L6", 1, 120),
            self.report("child-b", "U2 - L6", 0, 15),
            self.report("child-b", "U2 - L6", 1, 30),
        ]
        self.assertEqual(daily_totals(reports), [150] * 6)

    def test_headcount_uses_first_milestone_once_per_team(self):
        reports = [
            self.report("child-a", "U2 - L6", 0, 60, 40, 4),
            self.report("child-a", "U2 - L6", 1, 120, 42, 4),
            self.report("child-b", "U2-L6", 0, 10, 99, 9),
        ]
        self.assertEqual(headcount(reports, 50), (40, 44))
        self.assertEqual(key("U2 - L6"), key("U2-L6"))

    def test_manual_sync_does_not_overlap_background_sync(self):
        LOCK.acquire()
        try:
            with self.assertRaises(SyncBusy):
                sync(wait=False)
        finally:
            LOCK.release()


if __name__ == "__main__":
    unittest.main()


class FlatDashboardMissingFirstDayTests(unittest.TestCase):
    def test_missing_ngay_rai_chuyen_falls_back_to_first_report_day(self):
        from unittest.mock import patch
        from app import flat_sheet
        report = {"day": "2026-11-13", "team": "XN1-V1-L3", "child": "PL-1", "slot": 0, "source_row": 2,
                  "direct": 46, "indirect": 4, "quantities": [100, 100, 98, 90, 90, 90],
                  "action": "", "quality": None}
        plan = dict(demand="PL-1", style="311160", team="XN1-V1-L3", quantity=1000, dmkt=6.6,
                    category="Mới", workers=46, first=None, customer="DECATHLON", pos=[],
                    names=[f"Trạm {i}" for i in range(1, 7)], reports=[report])
        state = dict(plans=[plan], warnings=[], synced_at=None, sync_error=None)
        with patch.object(flat_sheet, "snapshot", return_value=state), \
             patch.object(flat_sheet.db, "query", return_value=[]), \
             patch("app.admin.get_holidays", return_value=set()), \
             patch.object(flat_sheet.flat_quality, "summarize", return_value={"status": "empty"}):
            d = flat_sheet.dashboard_api("PL-1", "2026-11-13")
        self.assertEqual(d["plan"]["first"], "2026-11-13")
        self.assertEqual(d["daily"][5], 90)
        self.assertTrue(any("Ngày rải chuyền" in w for w in d["warnings"]))
        self.assertIsNone(plan["first"])  # không sửa snapshot gốc
