"""Live output parity and QC mapping check; synthetic QC is always rolled back."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import os
import importlib.util
from unittest.mock import patch
from datetime import date
import httpx
import psycopg2
import psycopg2.extras
from app import flat_sheet, flat_tv


def main():
    state=flat_sheet.snapshot()
    client=httpx.Client(base_url=os.getenv('QLCL_API_URL','http://localhost:8008'),timeout=15)
    conn=psycopg2.connect(os.environ['FLAT_LINE_QLCL_DATABASE_URL'])
    try:
        cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        verified=[]
        for p in state['plans']:
            if not p['reports']:
                continue
            day=max(r['day'] for r in p['reports'])
            qty=flat_sheet.daily_totals([r for r in p['reports'] if r['day']==day])[5]
            cur.execute('SELECT id,don_vi,source_record_id FROM prod_plan WHERE source_system=%s AND source_record_id=%s',('flat_line_sheet',flat_sheet.unit()+':'+p['demand']))
            plan=cur.fetchone()
            assert plan, p['demand']
            response=client.get('/api/qc/hanging-output',params={'plan_id':plan['id'],'date':day})
            response.raise_for_status()
            out=response.json()
            assert out['qty']==qty,(p['demand'],out,qty)
            verified.append((plan,day,qty))
        print('Production parity:',[(p['id'],d,q) for p,d,q in verified])
        conn.rollback()
        plan,day,qty=next(r for r in verified if r[2] and r[2]>0)
        # Connect quality() to this uncommitted transaction; never publish fake QC.
        class Borrowed:
            def set_session(self,**kwargs): pass
            def cursor(self,**kwargs): return conn.cursor(**kwargs)
            def close(self): pass
        demand=plan['source_record_id'].split(':',1)[1]
        with patch('psycopg2.connect',return_value=Borrowed()):
            before=flat_sheet.quality(demand,day)
            cur.execute("INSERT INTO qc_error_log_sp(plan_id,date,station,output,defect_count) VALUES(%s,%s,'Trạm cuối chuyền',0,2) RETURNING id",(plan['id'],day))
            log_id=cur.fetchone()['id']
            for index,clock in [(1,'08:30'),(1,'08:31'),(2,'15:30')]:
                cur.execute('INSERT INTO qc_defect(error_log_sp_id,sp_index,created_at) VALUES(%s,%s,%s::timestamptz)',(log_id,index,f'{day} {clock}:00+07'))
            cur.execute("INSERT INTO qc_error_log_sp(plan_id,date,station,output,defect_count) VALUES(%s,%s,'Trạm đầu chuyền',0,99) RETURNING id",(plan['id'],day))
            other_id=cur.fetchone()['id']
            cur.execute('INSERT INTO qc_defect(error_log_sp_id,sp_index,created_at) VALUES(%s,1,%s::timestamptz)',(other_id,f'{day} 08:30:00+07'))
            cur.execute("INSERT INTO qc_defect_multi(plan_id,date,time,station,ma_loi) VALUES(%s,%s,'08:30','Trạm đầu chuyền','TEST IGNORE')",(plan['id'],day))
            d=flat_tv.dashboard(3,'flat:'+demand,date.fromisoformat(day))
            assert d['kpi']['TongLoi']==before.get('defects',0)+2,d
            assert d['kpi']['TyLeLoi']==round((before.get('defects',0)+2)/qty*100,1)
            after=flat_sheet.quality(demand,day)
            old={s['slot']:s['defects'] for s in before.get('slots',[])}
            new={s['slot']:s['defects'] for s in after['slots']}
            assert new[1]==old.get(1,0)+1
            assert new[4]==old.get(4,0)+1
            assert sum(r['n'] for r in d['combo'])==sum(r['quantity'] for r in before.get('details',[]))+3
            assert len(after['alerts'])==len(before.get('alerts',[]))
        print('TV3: defective garments deduplicated; morning/afternoon buckets and BP rate passed (rollback).')
    finally:
        conn.rollback()
        conn.close()
        client.close()

if __name__=='__main__':
    main()
