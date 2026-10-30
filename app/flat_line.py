"""Manual flat-line operations and additive production reports."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import auth, db
from .settings import APP_UNIT

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / 'templates'))


def check_demand(key: str, user: dict, enabled: bool = True) -> dict:
    rows = db.query('SELECT NhuCauMe, [LineNo], TrackFlatLine FROM app.tDemandRoot WHERE NhuCauMe = ?', (key,))
    if not rows:
        raise HTTPException(404, 'Không tìm thấy nhu cầu mẹ')
    row = rows[0]
    if user.get('Role', '').lower() != 'admin':
        if str(user.get('Unit', '')).strip().upper() != APP_UNIT or str(user.get('Dept')) != str(row['LineNo']):
            raise HTTPException(403, 'Nhu cầu không thuộc tổ của bạn')
    if enabled and not row['TrackFlatLine']:
        raise HTTPException(400, 'Nhu cầu chưa bật theo dõi chuyền bệt')
    return row


class OperationIn(BaseModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=200)
    assigned_emp_id: str | None = Field(None, max_length=50)


class ConfigIn(BaseModel):
    enabled: bool
    operations: list[OperationIn]


@router.get('/admin/api/flat-line')
def config(key: str, user: dict = Depends(auth.require_admin)):
    row = check_demand(key, user, False)
    return {'enabled': bool(row['TrackFlatLine']), 'operations': db.query(
        'SELECT ID AS id, Name AS name, AssignedEmpID AS assigned_emp_id '
        'FROM app.tFlatOperation WHERE NhuCauMe=? AND IsActive=1 ORDER BY SortOrder, ID', (key,))}


@router.put('/admin/api/flat-line')
def save_config(key: str, body: ConfigIn, user: dict = Depends(auth.require_admin)):
    check_demand(key, user, False)
    if body.enabled and not body.operations:
        raise HTTPException(422, 'Thêm ít nhất một công đoạn')
    with db.get_conn() as conn:
        conn.autocommit = False
        apply_config(conn.cursor(), key, body)
        conn.commit()
    return {'ok': True}


def apply_config(cur, key: str, body: ConfigIn):
    if body.enabled and not body.operations:
        raise HTTPException(422, 'Thêm ít nhất một công đoạn')
    names = [op.name.strip() for op in body.operations]
    ids = [op.id for op in body.operations if op.id is not None]
    if any(not name for name in names) or len(set(ids)) != len(ids):
        raise HTTPException(422, 'Tên công đoạn hoặc ID không hợp lệ')
    cur.execute('UPDATE app.tDemandRoot SET TrackFlatLine=? WHERE NhuCauMe=?', (body.enabled, key))
    cur.execute('UPDATE app.tFlatOperation SET IsActive=0 WHERE NhuCauMe=?', (key,))
    for index, op in enumerate(body.operations):
        emp = (op.assigned_emp_id or '').strip() or None
        if op.id is None:
            cur.execute('INSERT INTO app.tFlatOperation (NhuCauMe,Name,SortOrder,AssignedEmpID) VALUES (?,?,?,?)', (key, op.name.strip(), index, emp))
        else:
            cur.execute('UPDATE app.tFlatOperation SET Name=?,SortOrder=?,IsActive=1,AssignedEmpID=? WHERE ID=? AND NhuCauMe=?', (op.name.strip(), index, emp, op.id, key))
            if cur.rowcount != 1:
                raise HTTPException(422, 'Công đoạn không thuộc nhu cầu')


@router.get('/entry/flat-line')
def page(request: Request, user: dict = Depends(auth.require_user)):
    return templates.TemplateResponse('entry/flat-line.html', {
        'request': request,
        'user': user,
        'today': date.today().isoformat(),
        'app_unit': APP_UNIT,
    })


@router.get('/entry/api/flat-line/demands')
def demands(user: dict = Depends(auth.require_user)):
    where = ''
    params = ()
    if user.get('Role', '').lower() != 'admin':
        if str(user.get('Unit', '')).strip().upper() != APP_UNIT:
            raise HTTPException(403, f'Tài khoản phải thuộc {APP_UNIT}')
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


# ============================================================
# Real-time operator station (+1 / -1)
# ============================================================
@router.get('/entry/station')
def station_page(request: Request, user: dict = Depends(auth.require_user)):
    return templates.TemplateResponse('entry/station.html', {
        'request': request,
        'user': user,
        'today': date.today().isoformat(),
        'app_unit': APP_UNIT,
    })


def _operator_emp(user: dict) -> str | None:
    """Mã nhân viên dùng để lọc công đoạn. Admin xem tất cả (None)."""
    if user.get('Role', '').lower() == 'admin':
        return None
    return user['UserID']


@router.get('/entry/api/station/my-ops')
def my_stations(day: date, user: dict = Depends(auth.require_user)):
    """Các công đoạn bệt đang gán cho mã NV đang đăng nhập + số đã báo trong ngày."""
    emp = _operator_emp(user)
    where = 'o.IsActive=1 AND d.TrackFlatLine=1'
    params: tuple = (day,)
    if emp is not None:
        where += ' AND o.AssignedEmpID=?'
        params = (day, emp)
    return db.query(
        'SELECT o.ID AS OperationID, o.Name AS OperationName, o.NhuCauMe, '
        'd.StyleNo, d.[LineNo] AS [LineNo], o.AssignedEmpID, '
        'ISNULL((SELECT SUM(r.Qty) FROM app.tFlatReport r '
        '        WHERE r.OperationID=o.ID AND r.ReportDate=?),0) AS TodayQty '
        'FROM app.tFlatOperation o '
        'JOIN app.tDemandRoot d ON d.NhuCauMe=o.NhuCauMe '
        'WHERE ' + where + ' ORDER BY d.NhuCauMe, o.SortOrder, o.ID',
        params,
    )


def _check_operation_access(cur, operation_id: int, user: dict) -> dict:
    cur.execute(
        'SELECT o.NhuCauMe, o.AssignedEmpID, o.IsActive, d.TrackFlatLine '
        'FROM app.tFlatOperation o JOIN app.tDemandRoot d ON d.NhuCauMe=o.NhuCauMe '
        'WHERE o.ID=?', (operation_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, 'Công đoạn không tồn tại')
    nhu_cau_me, assigned, is_active, track = row
    is_admin = user.get('Role', '').lower() == 'admin'
    if not is_admin:
        if not is_active or not track:
            raise HTTPException(400, 'Công đoạn chưa được theo dõi')
        if assigned != user['UserID']:
            raise HTTPException(403, 'Công đoạn không được phân cho bạn')
    return {'NhuCauMe': nhu_cau_me}


def _today_qty(cur, operation_id: int, day: date) -> int:
    cur.execute('SELECT ISNULL(SUM(Qty),0) FROM app.tFlatReport WHERE OperationID=? AND ReportDate=?', (operation_id, day))
    return int(cur.fetchone()[0])


class PulseIn(BaseModel):
    operation_id: int
    day: date


@router.post('/entry/api/station/pulse')
def pulse_add(body: PulseIn, user: dict = Depends(auth.require_user)):
    """Ghi nhận 1 sản phẩm (nút +1). Mỗi lần bấm = 1 dòng Qty=1 kèm thời gian."""
    if body.day > date.today():
        raise HTTPException(422, 'Không báo ngày tương lai')
    with db.get_conn() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        _check_operation_access(cur, body.operation_id, user)
        cur.execute('INSERT INTO app.tFlatReport (OperationID,ReportDate,Qty,CreatedBy) VALUES (?,?,1,?)', (body.operation_id, body.day, user['UserID']))
        qty = _today_qty(cur, body.operation_id, body.day)
        conn.commit()
    return {'ok': True, 'today_qty': qty}


@router.post('/entry/api/station/undo')
def pulse_undo(body: PulseIn, user: dict = Depends(auth.require_user)):
    """Hoàn tác (nút -1): xoá dòng mới nhất của công đoạn trong ngày."""
    with db.get_conn() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        _check_operation_access(cur, body.operation_id, user)
        cur.execute(
            'DELETE FROM app.tFlatReport WHERE ID = ('
            '  SELECT TOP 1 ID FROM app.tFlatReport '
            '  WHERE OperationID=? AND ReportDate=? ORDER BY CreatedAt DESC, ID DESC)',
            (body.operation_id, body.day))
        removed = cur.rowcount
        qty = _today_qty(cur, body.operation_id, body.day)
        conn.commit()
    return {'ok': True, 'today_qty': qty, 'removed': removed}
