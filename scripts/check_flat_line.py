"""Integration checks against local app DB. Test reports are rolled back."""
from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import db, flat_line as flat, auth
from app.main import app


def main():
    user = auth.get_user_by_id('xn2_to3')
    key = '#352847'
    with db.get_conn() as conn:
        conn.autocommit = False
        class Shared:
            autocommit = False
            def cursor(self): return conn.cursor()
            def commit(self): pass
        @contextmanager
        def shared(): yield Shared()
        with patch.object(db, 'get_conn', shared):
            before = flat.reports(key, date.today(), user)
            ids = [o['ID'] for o in before['operations'] if o['IsActive']]
            flat.add_reports(key, flat.ReportIn(day=date.today(), items=[{'operation_id': ids[0], 'qty': 200}, {'operation_id': ids[1], 'qty': 90}]), user)
            flat.add_reports(key, flat.ReportIn(day=date.today(), items=[{'operation_id': ids[0], 'qty': 150}]), user)
            after = flat.reports(key, date.today(), user)
            assert after['operations'][0]['DayQty'] - before['operations'][0]['DayQty'] == 350
            report_id = after['reports'][0]['ID']
            flat.edit_report(report_id, flat.EditIn(day=date.today(), qty=125), user)
            updated = flat.reports(key, date.today(), user)
            assert updated['operations'][0]['DayQty'] - before['operations'][0]['DayQty'] == 325
            assert db.query('SELECT NewQty FROM app.tFlatReportAudit WHERE ReportID=?', (report_id,))[0]['NewQty'] == 125
            for outsider in [dict(user, Dept=99), dict(user, Unit='XN1')]:
                try: flat.edit_report(report_id, flat.EditIn(day=date.today(), qty=1), outsider)
                except HTTPException as exc: assert exc.status_code == 403
                else: raise AssertionError('Cross-line/unit write allowed')
        conn.rollback()
    client = TestClient(app)
    assert client.get('/entry/api/flat-line/demands').status_code == 401
    response = client.post('/auth/api/login', json={'UserID':'xn2_to3'})
    assert response.status_code == 200 and response.json()['next_url'] == '/entry'
    assert client.get('/entry/flat-line').status_code == 200
    assert client.get('/admin/api/flat-line', params={'key':key}).status_code == 403
    print('PASS: multi-operation reports, 200+150, edit/audit, access control, ID login, page render. Test reports rolled back.')


if __name__ == '__main__': main()
