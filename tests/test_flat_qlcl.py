import unittest
from app.flat_qlcl import build_outputs


class FlatOutputTests(unittest.TestCase):
    def test_children_latest_corrections_and_missing_milestones(self):
        def row(child,slot,value):
            return dict(child=child,team='U2-L6',day='2026-09-12',slot=slot,source_row=slot+2,quantities=[0]*5+[value])
        payload={'plans':[dict(demand='mother',reports=[row('a',0,60),row('a',1,120),row('a',4,100),row('b',0,10),row('b',4,30)])]}
        result=build_outputs(payload,'XN2')['outputs'][0]
        self.assertEqual(result['source_record_id'],'XN2:mother')
        self.assertEqual(result['qty'],130)
        self.assertEqual([s['qty'] for s in result['slots']],[70,60,None,None,0])
        self.assertEqual(build_outputs(payload,'XN2'),build_outputs(payload,'XN2'))

    def test_negative_correction_zero_and_unknown_are_preserved(self):
        rows=[dict(child='a',team='U2-L6',day='2026-09-12',slot=i,source_row=i,quantities=[0]*5+[v]) for i,v in enumerate([100,80,0])]
        result=build_outputs({'plans':[dict(demand='mother',reports=rows)]},'XN1')['outputs'][0]
        self.assertEqual(result['qty'],0)
        self.assertEqual(result['source_record_id'],'XN1-V1:mother')
        self.assertEqual([s['qty'] for s in result['slots']],[100,-20,-80,None,None])

if __name__=='__main__':
    unittest.main()
