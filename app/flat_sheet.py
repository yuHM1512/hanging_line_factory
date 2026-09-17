"""Read-only Sheets ingestion; atomic last-good snapshots in the app database."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from . import db

ROOT = Path(__file__).resolve().parent.parent
router = APIRouter(prefix="/tv/flat", tags=["flat-sheet-tv"])
log = logging.getLogger(__name__)
LOCK = threading.Lock()
SLOTS = ["09H30", "11H30", "14H30", "16H30", "Sau 16H30"]
MINUTES = [111, 120, 120, 111, 30]


def unit():
    return os.getenv("QLCL_DON_VI", "XN2")


def key(value):
    text = str(value).replace("đ", "d").replace("Đ", "D")
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower())


def number(value):
    if value in (None, ""):
        return None
    return float(str(value).replace(",", "").strip())


def sheet_date(value):
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Ngày không hợp lệ: {value}")


def sheet_id(url):
    match = re.search(r"/spreadsheets/d/([\w-]+)", url)
    if not match:
        raise ValueError("Cần URL Google Sheets đầy đủ trong env")
    return match[1]


def read_sources():
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    path = Path(os.environ["FLAT_LINE_GOOGLE_SERVICE_ACCOUNT_FILE"])
    if not path.is_absolute():
        path = ROOT / path
    creds = Credentials.from_service_account_file(str(path), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    with AuthorizedSession(creds) as session:
        def read(source, tab, area):
            sid = sheet_id(os.environ[source])
            region = "'" + os.environ[tab].replace("'", "''") + "'!" + os.environ[area]
            response = session.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/{quote(region, safe='')}", params={"valueRenderOption": "FORMATTED_VALUE"}, timeout=45)
            if not response.ok:
                raise ValueError(f"Không đọc được tab {os.environ[tab]} (HTTP {response.status_code})")
            return response.json().get("values", [])
        return (
            read("FLAT_LINE_PLAN_SPREADSHEET_URL", "FLAT_LINE_PLAN_WORKSHEET", "FLAT_LINE_PLAN_RANGE"),
            read("FLAT_LINE_PLAN_SPREADSHEET_URL", "FLAT_LINE_FACTORY_WORKSHEET", "FLAT_LINE_FACTORY_RANGE"),
            read("FLAT_LINE_DATA_SPREADSHEET_URL", "FLAT_LINE_DATA_WORKSHEET", "FLAT_LINE_DATA_RANGE"),
        )


def parse_sources(planning, factory, data):
    if not planning or not factory or not data:
        raise ValueError("Nguồn Sheet rỗng; giữ bản đồng bộ trước")
    header = {key(v): i for i, v in enumerate(planning[0])}
    required = ["nhucaubatdau", "mahang", "loaichuyen", "to", "sanluongkh", "dmkt", "phanloaidh", "ldbienche", "ngayraichuyen", "khachhang"]
    if any(k not in header for k in required):
        raise ValueError("Tiêu đề Rải chuyền không đúng cấu hình")
    if len(data[0]) < 74 or key(data[0][67]) != "quydoisanluong" or key(data[0][73]) != "nhucaume":
        raise ValueError("Data phải có BP=Quy đổi sản lượng và BV=Nhu cầu mẹ")
    plans = {}
    warnings = []
    expected_unit = re.search(r"\d+", unit()).group()
    for row in planning[1:]:
        row = row + [""] * 30
        get = lambda name: str(row[header[name]]).strip()
        if key(get("loaichuyen")) != "chuyenbet":
            continue
        demand = get("nhucaubatdau")
        team = get("to")
        if not re.search(rf"(?:U|XN)\s*{expected_unit}\b", team, re.I):
            raise ValueError("Chuyền bệt có đơn vị không khớp env")
        if not demand or demand in plans:
            raise ValueError("Nhu cầu mẹ trống hoặc trùng trong Rải chuyền")
        quantity = number(get("sanluongkh"))
        dmkt = number(get("dmkt"))
        workers = number(get("ldbienche"))
        style = get("mahang")
        category = get("phanloaidh")
        if not style or not quantity or quantity <= 0 or not dmkt or dmkt <= 0 or not workers or workers <= 0:
            raise ValueError(f"Nhu cầu {demand}: thiếu mã hàng, SLKH, ĐMKT hoặc LĐ biên chế hợp lệ")
        plans[demand] = dict(demand=demand, style=style, team=team,
            quantity=quantity, dmkt=dmkt, category=category,
            workers=workers, first=sheet_date(get("ngayraichuyen")), customer=get("khachhang"), pos=[], names=[], reports=[])
    # Numbered setting headers move between factories (XN2 Z:AE; XN3 X:AC).
    factory_headers = [key(v) for v in factory[0]]
    name_cols = [next((j for j,h in enumerate(factory_headers) if re.fullmatch(rf"{i}(?:ha|ktdm)",h)), None) for i in range(1,7)]
    if any(c is None for c in name_cols):
        raise ValueError("Không tìm được 6 tiêu đề cụm trong tab xí nghiệp")
    if factory_headers[8] != 'thongtinehd' or factory_headers[11] != 'nhucaubatdau':
        raise ValueError("Cột I/L tab xí nghiệp không đúng EHD/nhu cầu mẹ")
    team_col = next((j for j,h in enumerate(factory_headers) if h == 'quydoi'), None)
    settings = []
    for raw in factory[1:]:
        row = raw + [""] * 31
        if str(row[21]).strip() and any(row[c] for c in name_cols):
            settings.append((str(row[21]).strip(), key(row[team_col]) if team_col is not None else '', [row[c] for c in name_cols]))
        parent = str(row[11]).strip()
        if parent not in plans:
            continue
        for line in str(row[8]).splitlines():
            if not line.strip():
                continue
            match = re.fullmatch(r"\s*(.+?)\s*-\s*([\d,]+)\s*:\s*(.+?)\s*", line)
            if not match:
                warnings.append(f"EHD chưa tách được: {line}")
                continue
            po, qty, shipping = match.groups()
            plans[parent]["pos"].append(dict(po=po, quantity=number(qty), date=sheet_date(shipping)))
    for plan in plans.values():
        matches = [names for style, team, names in settings if style == plan['style'] and (not team or team == key(plan['team']))]
        if len(matches) > 1:
            warnings.append(f"{plan['demand']}: nhiều cấu hình cụm; cần kiểm tra Sheet")
        plan["names"] = matches[0] if len(matches) == 1 else [""] * 6
        if not all(plan["names"]):
            warnings.append(f"{plan['demand']}: thiếu tên cụm; đang dùng tên trạm mặc định")
        plan["names"] = [n or f"Trạm {i+1}" for i, n in enumerate(plan["names"])]
        plan["pos"].sort(key=lambda p: (p["date"], p["po"]))
    report_map = {}
    for i, raw in enumerate(data[1:], 2):
        row = raw + [""] * 74
        parent = str(row[73]).strip()
        if parent not in plans:
            continue
        if key(row[6]) not in [key(s) for s in SLOTS]:
            raise ValueError(f"Data dòng {i}: mốc chưa hỗ trợ {row[6]}")
        slot = [key(s) for s in SLOTS].index(key(row[6]))
        day = sheet_date(row[1])
        identity = (parent, day, key(row[2]), str(row[3]).strip(), slot)
        if identity in report_map:
            warnings.append(f"Data dòng {i}: báo cáo trùng nhu cầu con/ngày/tổ/mốc; dùng dòng mới nhất")
        report_map[identity] = dict(day=day, team=str(row[2]), child=str(row[3]).strip(), slot=slot,
            direct=number(row[4]), indirect=number(row[5]), quantities=[number(v) for v in row[7:12]]+[number(row[67])],
            action=str(row[15]).strip(), source_row=i)
    for (parent, *_), report in report_map.items():
        plans[parent]["reports"].append(report)
    return dict(plans=list(plans.values()), warnings=warnings)


class SyncBusy(Exception):
    """A Sheets refresh is already in progress."""


def sync(wait: bool = True):
    if not LOCK.acquire(blocking=wait):
        raise SyncBusy()
    try:
        try:
            payload = parse_sources(*read_sources())
            text = json.dumps(payload, ensure_ascii=False)
            with db.get_conn() as conn:
                conn.autocommit = False
                cur = conn.cursor()
                cur.execute("UPDATE app.tFlatSheetSnapshot WITH (UPDLOCK, SERIALIZABLE) SET Payload=?, SyncedAt=SYSUTCDATETIME(), LastAttemptAt=SYSUTCDATETIME(), LastError=NULL WHERE Unit=?", (text, unit()))
                if not cur.rowcount:
                    cur.execute("INSERT INTO app.tFlatSheetSnapshot VALUES (?,?,SYSUTCDATETIME(),SYSUTCDATETIME(),NULL)", (unit(), text))
                conn.commit()
            from .flat_qlcl import push
            try:
                result = push(payload)
                payload['qlcl_sync'] = dict(ok=True, synced_at=datetime.now(timezone.utc).isoformat(),
                    rows=result['upserted'], missing_plans=result.get('missing_plans',[]))
            except Exception:
                payload['qlcl_sync'] = dict(ok=False, message='Đã lưu Sheet; chưa gửi được sản lượng sang QLCL. Sẽ thử lại ở lượt sync tiếp theo.')
                log.warning('Flat output push failed; local snapshot retained')
            with db.get_conn() as conn:
                conn.cursor().execute('UPDATE app.tFlatSheetSnapshot SET Payload=? WHERE Unit=?',
                    (json.dumps(payload,ensure_ascii=False),unit()))
            return payload
        except Exception as exc:
            # Do not persist credentials, connection strings, or upstream response bodies.
            error = str(exc)[:450] if isinstance(exc, ValueError) else type(exc).__name__
            with db.get_conn() as conn:
                conn.cursor().execute("UPDATE app.tFlatSheetSnapshot SET LastAttemptAt=SYSUTCDATETIME(), LastError=? WHERE Unit=?", (error, unit()))
            raise
    finally:
        LOCK.release()


def start_sync():
    if os.getenv("FLAT_LINE_SYNC_ENABLED", "false").lower() != "true":
        return
    def loop():
        import time
        while True:
            try:
                sync()
            except Exception:
                log.error("Flat Sheets sync failed; retaining last good snapshot", exc_info=False)
            time.sleep(max(60, int(os.getenv("FLAT_LINE_SYNC_INTERVAL_SECONDS", "120"))))
    threading.Thread(target=loop, daemon=True, name="flat-sheet-sync").start()


def snapshot():
    rows = db.query("SELECT Payload,SyncedAt,LastError FROM app.tFlatSheetSnapshot WHERE Unit=?", (unit(),))
    if not rows:
        raise HTTPException(503, "Chưa có dữ liệu chuyền bệt; chờ đồng bộ nguồn Sheet")
    result = json.loads(rows[0]["Payload"])
    result["synced_at"] = rows[0]["SyncedAt"].replace(tzinfo=timezone.utc).isoformat()
    result["sync_error"] = rows[0]["LastError"]
    return result


def sync_status():
    rows = db.query("SELECT Payload,SyncedAt,LastAttemptAt,LastError FROM app.tFlatSheetSnapshot WHERE Unit=?", (unit(),))
    common = dict(unit=unit(), enabled=os.getenv("FLAT_LINE_SYNC_ENABLED", "false").lower() == "true",
                  interval_seconds=max(60, int(os.getenv("FLAT_LINE_SYNC_INTERVAL_SECONDS", "120"))))
    if not rows:
        return dict(**common, synced_at=None, last_attempt_at=None, sync_error=None)
    row = rows[0]
    iso = lambda value: value.replace(tzinfo=timezone.utc).isoformat() if value else None
    return dict(**common, synced_at=iso(row["SyncedAt"]), last_attempt_at=iso(row["LastAttemptAt"]),
                sync_error=row["LastError"], qlcl_sync=json.loads(row['Payload']).get('qlcl_sync'))


@router.get("/api/status")
def status_api():
    return sync_status()


@router.post("/api/sync")
def sync_api():
    try:
        payload = sync(wait=False)
    except SyncBusy:
        raise HTTPException(409, "Một lượt đồng bộ Sheet đang chạy")
    except Exception:
        status = sync_status()
        raise HTTPException(502, status.get("sync_error") or "Không đồng bộ được Google Sheets")
    return dict(ok=True, plans=len(payload.get("plans", [])), **sync_status())


def daily_totals(reports):
    """Last reported cumulative value per child/team, never sum snapshots or MAX corrections."""
    groups = {}
    for r in reports:
        groups.setdefault((r["child"], key(r["team"])), []).append(r)
    amounts = [0.0] * 6
    known = [False] * 6
    for group in groups.values():
        group.sort(key=lambda r: r["slot"])
        for j in range(6):
            available = [r["quantities"][j] for r in group if r["quantities"][j] is not None]
            if available:
                amounts[j] += available[-1]
                known[j] = True
    return [v if known[i] else None for i, v in enumerate(amounts)]


def headcount(reports, fallback):
    teams = {}
    for r in sorted(reports, key=lambda x: (x["slot"], x["source_row"])):
        teams.setdefault(key(r["team"]), r)
    direct = sum(r["direct"] or 0 for r in teams.values()) if teams else fallback
    total = sum((r["direct"] or 0)+(r["indirect"] or 0) for r in teams.values()) if teams else None
    return direct, total


def quality(demand, day):
    """Read QC through the same authenticated QLCL service as hanging TVs."""
    import httpx
    try:
        response = httpx.get(
            os.getenv('QLCL_API_URL', 'http://localhost:8008').strip().rstrip('/') + '/api/tv3/flat-qc-data',
            params={'demand': demand, 'don_vi': unit(), 'date': str(day)},
            headers={'X-API-Key': os.getenv('QLCL_API_KEY', '')},
            timeout=5.0,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or result.get('status') not in ('ok', 'empty'):
            raise ValueError('Invalid QLCL QC response')
        return result
    except Exception:
        log.warning('Flat-line QC API unavailable')
        return {'status': 'unavailable', 'message': 'Không đọc được QC qua API QLCL; kiểm tra URL, API key và phiên bản QLCL.'}


@router.get("/api/plans")
def plans_api():
    state = snapshot()
    return {**{k: v for k, v in state.items() if k != "plans"}, "plans": [{k: v for k, v in p.items() if k != "reports"} for p in state["plans"]]}


@router.get("/api/dashboard")
def dashboard_api(demand: str, day: str = ""):
    from .tv import _ndsx_level, _workday_index
    from .admin import get_holidays
    state = snapshot()
    p = next((p for p in state['plans'] if p['demand'] == demand), None)
    if p is None:
        raise HTTPException(404, "Không tìm thấy nhu cầu Chuyền bệt")
    try:
        requested = date.fromisoformat(day) if day else (datetime.now(timezone(timedelta(hours=7))).date())
    except ValueError:
        raise HTTPException(422, "Ngày không hợp lệ")
    dates = sorted({r['day'] for r in p['reports'] if r['day'] <= requested.isoformat()})
    selected = dates[-1] if dates else requested.isoformat()
    reports = [r for r in p['reports'] if r['day'] == selected]
    cutoff = max((r['slot'] for r in reports), default=-1)
    minutes = sum(MINUTES[:cutoff+1])
    direct, total_workers = headcount(reports, p['workers'])
    holidays = get_holidays()
    first = date.fromisoformat(p['first'])
    level = _ndsx_level(p['category'], 29520 / (p['workers'] * p['dmkt'])) if p['workers'] and p['dmkt'] else 0
    curve = db.query("SELECT DayN,Ratio FROM app.tProductionCurve WHERE Category=? AND NDSXLevel=? ORDER BY DayN", (p['category'], level))
    def target(dt, workers):
        n = _workday_index(first, dt, holidays)
        matches = [r for r in curve if r['DayN'] <= n]
        return round(p['dmkt'] * workers * float(matches[-1]['Ratio'])) if matches and workers else None
    aim = target(date.fromisoformat(selected), direct)
    actual = daily_totals(reports)
    byday = {d: [r for r in p['reports'] if r['day'] == d] for d in dates}
    cumulative = [sum(daily_totals(rs)[i] or 0 for rs in byday.values()) for i in range(6)]
    slots = []
    previous = 0
    for i, label in enumerate(SLOTS):
        has = any(r['slot'] == i for r in reports)
        value = daily_totals([r for r in reports if r['slot'] <= i])[5] if has else None
        delta = value - previous if value is not None else None
        if value is not None:
            previous = value
        slots.append(dict(label=label, actual=delta, cumulative=value, target=round(aim*sum(MINUTES[:i+1])/492)-round(aim*sum(MINUTES[:i])/492) if aim is not None else None))
    sam_rows = db.query("SELECT SAM,OWE_Target FROM app.tSAM WHERE StyleNo=?", (p['style'],))
    sam = float(sam_rows[0]['SAM']) if sam_rows and sam_rows[0]['SAM'] else None
    owe_target = float(sam_rows[0]['OWE_Target'])*100 if sam_rows and sam_rows[0]['OWE_Target'] else None
    owe = round(sam * actual[5] / (minutes * total_workers) * 100, 1) if sam and minutes and total_workers and actual[5] is not None else None
    wip = cumulative[0]-cumulative[5]
    takt = round(minutes*60/actual[5], 1) if actual[5] else None
    schedule = []
    cum_target = cum_actual = 0
    dt = min(first, date.fromisoformat(dates[0])) if dates else first
    end_target = None
    # A bounded forecast, plus every actual date even beyond the original plan.
    while len(schedule) < 180:
        if dt.weekday() != 6 and dt not in holidays or dt.isoformat() in byday:
            rs = byday.get(dt.isoformat(), [])
            workers, _ = headcount(rs, p['workers'])
            goal = target(dt, workers) if dt.weekday() != 6 and dt not in holidays else 0
            qty = daily_totals(rs)[5] if rs else None
            cum_target += goal or 0
            cum_actual += qty or 0
            schedule.append(dict(day=dt.isoformat(), n=len(schedule)+1, workers=workers, target=goal, actual=qty, cum_target=cum_target, cum_actual=cum_actual if dt.isoformat()<=selected else None))
            if end_target is None and cum_target >= p['quantity']:
                end_target = dt.isoformat()
            if end_target and dt.isoformat() >= selected:
                break
        dt += timedelta(days=1)
    qc = quality(demand, selected)
    # QC can arrive after a production milestone: compare to the displayed BP with a clear source timestamp.
    from .quality import inspection
    qc['rate'] = inspection(actual[5], qc.get('defects') if qc['status']=='ok' else None)['pct']
    warnings = list(state['warnings'])
    if not curve:
        warnings.append("Chưa có đường cong năng suất phù hợp")
    if not sam:
        warnings.append("Chưa có SAM cho mã hàng trong cấu hình app")
    if any(s['actual'] is not None and s['actual'] < 0 for s in slots):
        warnings.append("BP có điều chỉnh giảm; đang giữ đúng chênh lệch báo cáo")
    if cutoff >= 0 and any(not any(r['slot'] == i for r in reports) for i in range(cutoff + 1)):
        warnings.append("Thiếu mốc báo cáo: chênh lệch tại mốc kế tiếp bao gồm khoảng bị thiếu")
    if reports and any(r['quantities'][5] is None for r in reports):
        warnings.append("Có báo cáo thiếu BP; sản lượng chỉ tổng hợp các giá trị đã có")
    if dates and dates[0] < p['first']:
        warnings.append("Có sản lượng trước ngày rải chuyền; vẫn tính vào lũy kế mẹ")
    return dict(plan={k:v for k,v in p.items() if k!='reports'}, unit=unit(), selected=selected, requested=requested.isoformat(),
        cutoff=SLOTS[cutoff] if cutoff>=0 else None, minutes=minutes, workers=total_workers, direct=direct,
        daily=actual, cumulative=cumulative, target=aim, target_to_slot=round(aim*minutes/492) if aim is not None else None,
        slots=slots, owe=owe, owe_target=owe_target, sam=sam, wip=wip, takt=takt,
        takt_target=round(29520/aim,1) if aim else None, tpt=round((wip+1)*takt/60,1) if takt else None,
        end_target=end_target, schedule=schedule, qc=qc, warnings=warnings,
        actions=[dict(slot=SLOTS[r['slot']], text=r['action']) for r in reports if r['action']],
        synced_at=state['synced_at'], sync_error=state['sync_error'])


@router.get("")
@router.get("/{screen}")
def page(request: Request, screen: int = 1):
    if screen not in (1,2,3,4):
        raise HTTPException(404)
    demand = request.query_params.get('demand', '')
    if not demand:
        return RedirectResponse('/tv')
    day = request.query_params.get('day') or datetime.now(timezone(timedelta(hours=7))).date().isoformat()
    return RedirectResponse(f'/tv/{screen}?mono={quote("flat:"+demand)}&date={quote(day)}')
