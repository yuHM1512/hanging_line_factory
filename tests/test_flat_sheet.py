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
