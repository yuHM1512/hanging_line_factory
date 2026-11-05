import unittest

from app import flat_quality


def row(n='', groups=(), ak=''):
    """Data-U2 row (A:BV) with N, Q:AJ (5 × [lỗi, trạm, số lỗi, HĐKP]) and AK filled."""
    r = [''] * 74
    r[13] = n
    for g, values in enumerate(groups):
        r[16 + 4 * g:20 + 4 * g] = list(values)
    r[36] = ak
    return r


def report(slot, **kw):
    return dict(slot=slot, quality=flat_quality.parse_row(row(**kw)))


class ParseTests(unittest.TestCase):
    def test_station_formats_seen_in_data_u2(self):
        q = flat_quality.parse_row(row(n='3', ak='2', groups=[
            ('M3. Mật độ chỉ', '33', '1', 'Chỉnh máy'),
            ('C9. Bung xì', '40.30', '2', ''),        # several stations, one total
            ('S12. Nhăn đùn', '50.  46a', '1,1', ''),  # per-station counts, alnum station
            ('S1. Đứt chỉ', '', '', ''),               # type only
        ]))
        self.assertEqual(q['defect_qty'], 3)
        self.assertEqual(q['reinspect'], 2)
        d = q['defects']
        self.assertEqual(flat_quality.positions(d[0]), ['Trạm 33: 1 lỗi'])
        self.assertEqual(flat_quality.positions(d[1]), ['Trạm 40, 30: 2 lỗi'])
        self.assertEqual(flat_quality.positions(d[2]), ['Trạm 50: 1 lỗi', 'Trạm 46a: 1 lỗi'])
        self.assertEqual(flat_quality.positions(d[3]), [])
        self.assertEqual([flat_quality.defect_qty(x) for x in d], [1, 2, 2, 1])

    def test_free_text_numbers_never_raise(self):
        q = flat_quality.parse_row(row(n='#N/A', ak='abc'))
        self.assertIsNone(q['defect_qty'])
        self.assertIsNone(q['reinspect'])


class SummaryTests(unittest.TestCase):
    def test_latest_milestone_table_and_day_accumulate(self):
        reports = [
            report(0, n='2', ak='1', groups=[('A', '1', '2', 'cap A')]),
            report(1, n='3', ak='3', groups=[('B', '5', '1', ''), ('A', '7', '2', 'cap A2')]),
        ]
        q = flat_quality.summarize(reports, 1)
        self.assertEqual(q['status'], 'ok')
        self.assertEqual(q['window'], '11H30')
        self.assertEqual([(r['type'], r['qty']) for r in q['rows']], [('A', 2), ('B', 1)])
        self.assertEqual(q['rows'][0]['cap'], 'cap A2')
        self.assertEqual(q['defects_2h'], 3)
        self.assertEqual(q['reinspect_2h'], 3)
        self.assertEqual(q['reinspect_rate'], 100.0)
        self.assertEqual(q['defects_day'], 5)
        self.assertEqual(q['reinspect_day'], 4)
        self.assertEqual(q['top3'], [dict(type='A', qty=4), dict(type='B', qty=1)])

    def test_same_type_from_two_children_is_merged(self):
        reports = [report(0, groups=[('A', '1', '1', 'x')]), report(0, groups=[('A', '2', '3', 'x')])]
        q = flat_quality.summarize(reports, 0)
        self.assertEqual(len(q['rows']), 1)
        self.assertEqual(q['rows'][0]['qty'], 4)
        self.assertEqual(q['rows'][0]['positions'], ['Trạm 1: 1 lỗi', 'Trạm 2: 3 lỗi'])
        self.assertEqual(q['rows'][0]['cap'], 'x')
        self.assertEqual(q['defects_2h'], 4)  # N missing → parsed groups

    def test_n_and_ak_without_defect_groups(self):
        q = flat_quality.summarize([report(2, n='2', ak='1')], 2)
        self.assertEqual(q['status'], 'ok')
        self.assertEqual(q['rows'], [])
        self.assertEqual(q['defects_2h'], 2)
        self.assertEqual(q['reinspect_rate'], 50.0)

    def test_end_of_day_window_joins_16h30_and_sau_16h30(self):
        reports = [
            report(2, n='5', groups=[('X', '1', '5', '')]),
            report(3, n='4', ak='0', groups=[('A', '3', '4', 'cap')]),
            report(4, n='2', ak='6'),
        ]
        q = flat_quality.summarize(reports, 4)
        self.assertEqual(q['window'], 'Sau 16H30')
        self.assertEqual([r['type'] for r in q['rows']], ['A'])
        self.assertEqual(q['defects_2h'], 6)
        self.assertEqual(q['reinspect_2h'], 6)
        self.assertEqual(q['reinspect_rate'], 100.0)
        self.assertEqual(q['defects_day'], 11)

    def test_every_milestone_up_to_cutoff_is_selectable(self):
        reports = [
            report(0, n='2', ak='2', groups=[('A', '1', '2', '')]),
            report(2, n='1', groups=[('B', '4', '1', '')]),
            report(3, n='4', groups=[('C', '3', '4', '')]),
            report(4, n='1', ak='5'),
        ]
        q = flat_quality.summarize(reports, 4)
        w = q['windows']
        self.assertEqual([x['window'] for x in w], ['09H30', '11H30', '14H30', '16H30', 'Sau 16H30'])
        self.assertEqual([x['reported'] for x in w], [True, False, True, True, True])
        self.assertEqual([r['type'] for r in w[0]['rows']], ['A'])
        self.assertEqual(w[0]['reinspect_rate'], 100.0)
        self.assertEqual(w[1]['rows'], [])
        self.assertIsNone(w[1]['defects_2h'])
        self.assertEqual([r['type'] for r in w[3]['rows']], ['C'])
        self.assertEqual(w[4]['defects_2h'], 5)  # 16H30 + Sau 16H30
        self.assertEqual(q['rows'], w[4]['rows'])  # top level = latest window
        self.assertEqual(q['defects_2h'], 5)

    def test_table_keeps_five_rows_and_counts_the_rest(self):
        q = flat_quality.summarize([report(0, groups=[(t, '', str(i + 1), '') for i, t in enumerate('ABCDE')]),
                                    report(0, groups=[('F', '', '9', '')])], 0)
        self.assertEqual([r['type'] for r in q['rows']], ['F', 'E', 'D', 'C', 'B'])
        self.assertEqual(q['more_rows'], 1)

    def test_old_snapshot_without_quality_is_empty(self):
        q = flat_quality.summarize([dict(slot=0)], 0)
        self.assertEqual(q['status'], 'empty')
        self.assertIsNone(q['defects_day'])
        self.assertIsNone(q['reinspect_rate'])


if __name__ == '__main__':
    unittest.main()
