"""Manual flat-line operations and additive production reports."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import auth, db

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / 'templates'))


def check_demand(key: str, user: dict, enabled: bool = True) -> dict:
    rows = db.query('SELECT NhuCauMe, [LineNo], TrackFlatLine FROM app.tDemandRoot WHERE NhuCauMe = ?', (key,))
    if not rows:
        raise HTTPException(404, 'Không tìm thấy nhu cầu mẹ')
    row = rows[0]
    if user.get('Role', '').lower() != 'admin':
        if str(user.get('Unit', '')).upper() != 'XN2' or str(user.get('Dept')) != str(row['LineNo']):
            raise HTTPException(403, 'Nhu cầu không thuộc tổ của bạn')
    if enabled and not row['TrackFlatLine']:
        raise HTTPException(400, 'Nhu cầu chưa bật theo dõi chuyền bệt')
    return row


class OperationIn(BaseModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=200)


class ConfigIn(BaseModel):
    enabled: bool
    operations: list[OperationIn]


@router.get('/admin/api/flat-line')
def config(key: str, user: dict = Depends(auth.require_admin)):
    row = check_demand(key, user, False)
    return {'enabled': bool(row['TrackFlatLine']), 'operations': db.query(
        'SELECT ID AS id, Name AS name FROM app.tFlatOperation WHERE NhuCauMe=? AND IsActive=1 ORDER BY SortOrder, ID', (key,))}


@router.put('/admin/api/flat-line')
def save_config(key: str, body: ConfigIn, user: dict = Depends(auth.require_admin)):
    check_demand(key, user, False)
    if body.enabled and not body.operations:
        raise HTTPException(422, 'Thêm ít nhất một công đoạn')
    names = [op.name.strip() for op in body.operations]
    ids = [op.id for op in body.operations if op.id is not None]
    if any(not name for name in names) or len(set(ids)) != len(ids):
        raise HTTPException(422, 'Tên công đoạn hoặc ID không hợp lệ')
    with db.get_conn() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute('UPDATE app.tDemandRoot SET TrackFlatLine=? WHERE NhuCauMe=?', (body.enabled, key))
        cur.execute('UPDATE app.tFlatOperation SET IsActive=0 WHERE NhuCauMe=?', (key,))
        for index, op in enumerate(body.operations):
            if op.id is None:
                cur.execute('INSERT INTO app.tFlatOperation (NhuCauMe,Name,SortOrder) VALUES (?,?,?)', (key, op.name.strip(), index))
            else:
                cur.execute('UPDATE app.tFlatOperation SET Name=?,SortOrder=?,IsActive=1 WHERE ID=? AND NhuCauMe=?', (op.name.strip(), index, op.id, key))
                if cur.rowcount != 1:
                    raise HTTPException(422, 'Công đoạn không thuộc nhu cầu')
        conn.commit()
    return {'ok': True}


@router.get('/entry/flat-line')
def page(request: Request, user: dict = Depends(auth.require_user)):
    return templates.TemplateResponse('entry/flat-line.html', {'request': request, 'user': user, 'today': date.today().isoformat()})


@router.get('/entry/api/flat-line/demands')
def demands(user: dict = Depends(auth.require_user)):
    where = ''
    params = ()
    if user.get('Role', '').lower() != 'admin':
        if str(user.get('Unit', '')).upper() != 'XN2':
            raise HTTPException(403, 'Tài khoản phải thuộc XN2')
        where = ' AND [LineNo]=?'
        params = (user.get('Dept'),)
    return db.query('SELECT NhuCauMe,StyleNo,[LineNo] FROM app.tDemandRoot WHERE TrackFlatLine=1' + where + ' ORDER BY NhuCauMe', params)


@router.get('/entry/api/flat-line')
def reports(key: str, day: date, user: dict = Depends(auth.require_user)):
    check_demand(key, user)
    ops = db.query('SELECT o.ID,o.Name,o.IsActive,ISNULL(SUM(r.Qty),0) AS DayQty FROM app.tFlatOperation o LEFT JOIN app.tFlatReport r ON r.OperationID=o.ID AND r.ReportDate=? WHERE o.NhuCauMe=? GROUP BY o.ID,o.Name,o.IsActive,o.SortOrder ORDER BY o.SortOrder,o.ID', (day, key))
    logs = db.query('SELECT r.ID,r.OperationID,o.Name,r.Qty,r.CreatedBy,CONVERT(varchar(19),r.CreatedAt,120) AS CreatedAt FROM app.tFlatReport r JOIN app.tFlatOperation o ON o.ID=r.OperationID WHERE o.NhuCauMe=? AND r.ReportDate=? ORDER BY r.CreatedAt DESC,r.ID DESC', (key, day))
    for row in logs:
        row['CanEdit'] = user.get('Role', '').lower() == 'admin' or row['CreatedBy'] == user['UserID']
    return {'operations': ops, 'reports': logs}


class ReportItem(BaseModel):
    operation_id: int
    qty: int = Field(gt=0, le=2147483647)


class ReportIn(BaseModel):
    day: date
    items: list[ReportItem] = Field(min_length=1)


@router.post('/entry/api/flat-line')
def add_reports(key: str, body: ReportIn, user: dict = Depends(auth.require_user)):
    check_demand(key, user)
    if body.day > date.today() or len({i.operation_id for i in body.items}) != len(body.items):
        raise HTTPException(422, 'Ngày tương lai hoặc công đoạn trùng không hợp lệ')
    with db.get_conn() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        for item in body.items:
            cur.execute('SELECT ID FROM app.tFlatOperation WHERE ID=? AND NhuCauMe=? AND IsActive=1', (item.operation_id, key))
            if not cur.fetchone():
                raise HTTPException(422, 'Công đoạn không hợp lệ')
            cur.execute('INSERT INTO app.tFlatReport (OperationID,ReportDate,Qty,CreatedBy) VALUES (?,?,?,?)', (item.operation_id, body.day, item.qty, user['UserID']))
        conn.commit()
    return {'ok': True}


class EditIn(BaseModel):
    day: date
    qty: int = Field(ge=0, le=2147483647)


@router.put('/entry/api/flat-line/{report_id}')
def edit_report(report_id: int, body: EditIn, user: dict = Depends(auth.require_user)):
    if body.day > date.today():
        raise HTTPException(422, 'Không báo ngày tương lai')
    with db.get_conn() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute('SELECT o.NhuCauMe,r.CreatedBy,r.ReportDate,r.Qty FROM app.tFlatReport r WITH (UPDLOCK) JOIN app.tFlatOperation o ON o.ID=r.OperationID WHERE r.ID=?', (report_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, 'Không tìm thấy lần báo')
        check_demand(row[0], user)
        if user.get('Role', '').lower() != 'admin' and row[1] != user['UserID']:
            raise HTTPException(403, 'Chỉ được sửa lần báo của mình')
        cur.execute('INSERT INTO app.tFlatReportAudit (ReportID,OldDate,OldQty,NewDate,NewQty,ChangedBy) VALUES (?,?,?,?,?,?)', (report_id, row[2], row[3], body.day, body.qty, user['UserID']))
        cur.execute('UPDATE app.tFlatReport SET ReportDate=?,Qty=?,UpdatedBy=?,UpdatedAt=SYSDATETIME() WHERE ID=?', (body.day, body.qty, user['UserID'], report_id))
        conn.commit()
    return {'ok': True}
