"""Admin router for setup and master-data CRUD."""
from __future__ import annotations

import csv
import io
import json
import logging
import math
import os
import re
import time
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from . import auth, db

# URL base app QLCL — dùng để lấy danh mục loại hàng và đồng bộ kế hoạch
QLCL_API_URL = os.environ.get("QLCL_API_URL", "http://localhost:8008")
# API key để xác thực với QLCL server (phải trùng với QLCL_API_KEY bên QLCL)
QLCL_API_KEY = os.environ.get("QLCL_API_KEY", "")
# Đơn vị của app này — gắn vào prod_plan.don_vi khi push sang QLCL
QLCL_DON_VI  = os.environ.get("QLCL_DON_VI", "XN")
QLCL_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(auth.require_admin)],
)

# Tạm: dùng admin cho audit cols. Sau này thay bằng session/JWT.


class AdminModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


def _actor_id(user: dict) -> str:
    return str(user.get("UserID") or "admin")


def _qlcl_base_url() -> str:
    base = (QLCL_API_URL or "").strip()
    if base and not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return base.rstrip("/")


def _qlcl_request(path: str, *, method: str = "GET", data: bytes | None = None) -> urllib.request.Request:
    req = urllib.request.Request(f"{_qlcl_base_url()}{path}", data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("Accept-Language", "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7")
    req.add_header("User-Agent", QLCL_USER_AGENT)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if QLCL_API_KEY:
        req.add_header("X-API-Key", QLCL_API_KEY)
    return req

# Chỉ hiện MONo có scan đầu tiên (MIN ShtDate) từ ngày này trở đi.
PLAN_CANDIDATE_START_DATE = date(2026, 4, 18)
PLAN_CANDIDATE_CACHE_TTL_SECONDS = 60
_plan_candidate_cache: dict[str, Any] = {"expires_at": 0.0, "rows": None}

# Regex parse Tổ từ MONo prefix (handle 'LINE 1 #', 'LINE; 1- #', 'LINE; 6-#')
_RE_LINE_NUM = re.compile(r"LINE\W*?(\d+)", re.IGNORECASE)
_RE_LEAD_DIGITS = re.compile(r"(\d+)")
# Số tổ tối đa — dùng để phân biệt số tổ với mã hàng trong format StyleNo-LineNo
_MAX_LINE_NO = 99


def parse_mono(mono: str) -> dict[str, Any]:
    """Tách MONo -> {LineNo, SoDonHang, StyleNo}.

    Hỗ trợ 2 format:

    Format 1 — có từ "LINE" (cũ):
        'LINE 3 #324230-4'  -> LineNo=3, SoDonHang='#324230-4', StyleNo='324230'
        'LINE; 6-#D093-6'   -> LineNo=6, SoDonHang='#D093-6',   StyleNo='D093'

    Format 2 — không có "LINE" (mới): [#]StyleNo-LineNo[-Repeat]
        '376556-5'    -> LineNo=5, SoDonHang='376556-5',   StyleNo='376556'
        '#D093-6'     -> LineNo=6, SoDonHang='#D093-6',    StyleNo='D093'
        '376556-5-2'  -> LineNo=5, SoDonHang='376556-5-2', StyleNo='376556'  (lần 2)
        'HWP100-1'    -> LineNo=1, SoDonHang='HWP100-1',   StyleNo='HWP100'
        '324212'      -> LineNo=None  (không đủ thông tin, bỏ qua)
    """
    if not mono:
        return {"LineNo": None, "SoDonHang": None, "StyleNo": None}

    # --- Format 1: có "LINE" ---
    m_line = _RE_LINE_NUM.search(mono)
    if m_line:
        line_no = int(m_line.group(1))
        so_dh = mono[mono.index("#"):] if "#" in mono else None
        style = None
        if so_dh:
            m_st = _RE_LEAD_DIGITS.match(so_dh.lstrip("#"))
            style = m_st.group(1) if m_st else None
        return {"LineNo": line_no, "SoDonHang": so_dh, "StyleNo": style}

    # --- Format 2: [#]StyleNo-LineNo[-Repeat] ---
    so_dh   = mono                      # SoDonHang = MONo chính nó
    stripped = mono.lstrip("#").strip()
    parts    = stripped.split("-")

    line_no = None
    style   = None

    if len(parts) >= 2:
        last        = parts[-1]
        second_last = parts[-2]

        if (last.isdigit() and second_last.isdigit()
                and 1 <= int(second_last) <= _MAX_LINE_NO):
            # Dạng StyleNo-LineNo-Repeat (vd 376556-5-2)
            line_no = int(second_last)
            style   = "-".join(parts[:-2]) or None
        elif last.isdigit() and 1 <= int(last) <= _MAX_LINE_NO:
            # Dạng StyleNo-LineNo (vd 376556-5)
            line_no = int(last)
            style   = "-".join(parts[:-1]) or None
        # else: không nhận ra được tổ → line_no=None, bỏ qua ở bước lọc

    return {"LineNo": line_no, "SoDonHang": so_dh, "StyleNo": style or stripped or None}


def _clear_plan_candidate_cache() -> None:
    _plan_candidate_cache["expires_at"] = 0.0
    _plan_candidate_cache["rows"] = None


def get_holidays() -> set[date]:
    rows = db.query("SELECT HolidayDate FROM app.tHoliday")
    return {r["HolidayDate"] for r in rows}


def compute_end_date(
    first_hang: Optional[date],
    slkh: Optional[int],
    daily_aim: Optional[int],
    holidays: set[date],
) -> Optional[date]:
    """Ngày kết thúc dự kiến = FirstHangDate + ceil(SLKH/DailyAim), skip CN + lễ."""
    if not first_hang or not slkh or not daily_aim or daily_aim <= 0:
        return None
    days_needed = math.ceil(slkh / daily_aim)
    d = first_hang
    remaining = days_needed
    # Sun = weekday() == 6
    while remaining > 0:
        if d.weekday() != 6 and d not in holidays:
            remaining -= 1
            if remaining == 0:
                return d
        d += timedelta(days=1)
    return d


# ============================================================
# Pages
# ============================================================
@router.get("")
@router.get("/")
def admin_home(request: Request):
    return templates.TemplateResponse(
        "admin/home.html", {"request": request, "user": request.state.current_user}
    )


@router.get("/holiday")
def page_holiday(request: Request):
    return templates.TemplateResponse(
        "admin/holiday.html", {"request": request, "user": request.state.current_user}
    )


@router.get("/demand")
def page_demand(request: Request):
    return templates.TemplateResponse(
        "admin/plan.html", {"request": request, "user": request.state.current_user}
    )


@router.get("/sam")
def page_sam(request: Request):
    return templates.TemplateResponse(
        "admin/sam.html", {"request": request, "user": request.state.current_user}
    )


@router.get("/user")
def page_user(request: Request):
    return templates.TemplateResponse(
        "admin/user.html", {"request": request, "user": request.state.current_user}
    )


@router.get("/plan")
def page_plan(request: Request):
    return RedirectResponse(url="/admin/demand", status_code=307)


# ============================================================
# Checklist API — tổng quan trạng thái setup
# ============================================================
@router.get("/api/checklist")
def api_checklist():
    """Trả về số lượng record mỗi bảng master data để hiển thị checklist."""
    counts = {}
    tables = {
        "holiday": "SELECT COUNT(*) AS c FROM app.tHoliday",
        "demand":  "SELECT COUNT(*) AS c FROM app.tDemandRoot",
        "plan":    "SELECT COUNT(*) AS c FROM app.tPlanMaster",
        "cluster": "SELECT COUNT(*) AS c FROM app.tClusterStationConfig",
        "sam":     "SELECT COUNT(*) AS c FROM app.tSAM",
        "user":    "SELECT COUNT(*) AS c FROM app.tUser",
    }
    for key, sql in tables.items():
        try:
            rows = db.query(sql)
            counts[key] = rows[0]["c"] if rows else 0
        except Exception:
            counts[key] = -1  # error
    return counts


# ============================================================
# M1 — Holiday
# ============================================================
class HolidayIn(AdminModel):
    holiday_date: date = Field(..., alias="HolidayDate")
    description: Optional[str] = Field(None, alias="Description")

@router.get("/api/holiday")
def api_holiday_list():
    return db.query(
        "SELECT CONVERT(varchar(10), HolidayDate, 120) AS HolidayDate, "
        "Description, CreatedBy, "
        "CONVERT(varchar(19), CreatedAt, 120) AS CreatedAt "
        "FROM app.tHoliday ORDER BY HolidayDate"
    )


@router.post("/api/holiday")
def api_holiday_create(body: HolidayIn, user: dict = Depends(auth.require_admin)):
    try:
        with db.get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO app.tHoliday (HolidayDate, Description, CreatedBy) "
                "VALUES (?, ?, ?)",
                (body.holiday_date, body.description, _actor_id(user)),
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Lưu thất bại: {exc}") from exc
    return {"ok": True}


@router.delete("/api/holiday/{holiday_date}")
def api_holiday_delete(holiday_date: date):
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM app.tHoliday WHERE HolidayDate = ?", (holiday_date,))
        n = cur.rowcount
    if n == 0:
        raise HTTPException(404, "Không tìm thấy ngày")
    return {"ok": True, "deleted": n}


# ============================================================
# M2 — DemandRoot (Nhu cầu mẹ)
# ============================================================
@router.get("/api/demand/candidates")
def api_demand_candidates():
    """Trả về các NhuCauCon (tPlanMaster) chưa được gán làm NhuCauMe.

    User pick từ list này → tự lấy StyleNo + LineNo + lấy NhuCauMe = SoDonHang.
    """
    sql = """
        SELECT pm.SoDonHang, pm.StyleNo, pm.[LineNo] AS LineNoOut,
               pm.MONo, pm.SLKH, pm.DailyAim, pm.Customer,
               CONVERT(varchar(10), pm.FirstHangDate, 120) AS FirstHangDate
        FROM app.tPlanMaster pm
        WHERE NOT EXISTS (
            SELECT 1 FROM app.tDemandRoot dr WHERE dr.NhuCauMe = pm.SoDonHang
        )
        ORDER BY pm.FirstHangDate, pm.[LineNo], pm.SoDonHang
    """
    return db.query(sql)


@router.get("/api/demand")
def api_demand_list():
    return db.query(
        "SELECT NhuCauMe, StyleNo, SLKH, ChildCount, DMKT, PhanLoaiDH, "
        "[LineNo] AS LineNoOut, LDBienChe, Notes, CreatedBy, "
        "CONVERT(varchar(10), EarliestFirstHangDate, 120) AS EarliestFirstHangDate, "
        "CONVERT(varchar(19), CreatedAt, 120) AS CreatedAt, "
        "CONVERT(varchar(19), UpdatedAt, 120) AS UpdatedAt "
        "FROM app.vDemandRoot ORDER BY StyleNo, NhuCauMe"
    )


class DemandIn(AdminModel):
    """Form NhuCauMe: chỉ cần pick 1 NhuCauCon + 3 trường nghiệp vụ.

    StyleNo + LineNo sẽ auto-derive từ NhuCauCon được pick (cùng tổ).
    """
    nhu_cau_me: str = Field(..., alias="NhuCauMe")  # = SoDonHang của con đầu
    dmkt: float = Field(..., alias="DMKT", gt=0)
    phan_loai: str = Field(..., alias="PhanLoaiDH")
    ld_bien_che: int = Field(..., alias="LDBienChe", gt=0)
    notes: Optional[str] = Field(None, alias="Notes")

@router.post("/api/demand")
def api_demand_create(body: DemandIn, user: dict = Depends(auth.require_admin)):
    if body.phan_loai not in ("Đặc biệt", "Mới", "Lặp lại", "Vest"):
        raise HTTPException(400, "Phân loại không hợp lệ")

    # Auto-derive StyleNo + LineNo từ NhuCauCon
    child = db.query(
        "SELECT TOP 1 PlanMaster_guid, StyleNo, [LineNo] AS LineNoOut "
        "FROM app.tPlanMaster WHERE SoDonHang = ?",
        (body.nhu_cau_me,),
    )
    if not child:
        raise HTTPException(
            400, f"Không tìm thấy NhuCauCon `{body.nhu_cau_me}`. Tạo NhuCauCon trước."
        )
    c = child[0]

    try:
        with db.get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO app.tDemandRoot "
                "(NhuCauMe, StyleNo, DMKT, PhanLoaiDH, [LineNo], "
                "LDBienChe, Notes, CreatedBy) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (body.nhu_cau_me, c["StyleNo"], body.dmkt, body.phan_loai,
                 c["LineNoOut"], body.ld_bien_che, body.notes, _actor_id(user)),
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Lưu thất bại: {exc}") from exc
    # KHÔNG auto-link — user sẽ vào /admin/plan → Sửa → chọn NhuCauMe từ dropdown
    return {"ok": True}


class DemandUpdate(AdminModel):
    dmkt: float = Field(..., alias="DMKT", gt=0)
    phan_loai: str = Field(..., alias="PhanLoaiDH")
    ld_bien_che: int = Field(..., alias="LDBienChe", gt=0)
    notes: Optional[str] = Field(None, alias="Notes")

@router.put("/api/demand/{nhu_cau_me}")
def api_demand_update(nhu_cau_me: str, body: DemandUpdate, user: dict = Depends(auth.require_admin)):
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE app.tDemandRoot SET "
            "DMKT = ?, PhanLoaiDH = ?, LDBienChe = ?, Notes = ?, "
            "UpdatedAt = SYSDATETIME(), UpdatedBy = ? "
            "WHERE NhuCauMe = ?",
            (body.dmkt, body.phan_loai, body.ld_bien_che, body.notes,
             _actor_id(user), nhu_cau_me),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Không tìm thấy Nhu cầu mẹ")
    return {"ok": True}


@router.delete("/api/demand/{nhu_cau_me}")
def api_demand_delete(nhu_cau_me: str, user: dict = Depends(auth.require_admin)):
    with db.get_conn() as conn:
        cur = conn.cursor()
        # Bỏ link FK trên con trước khi xoá mẹ
        cur.execute(
            "UPDATE app.tPlanMaster SET NhuCauMe = NULL, "
            "UpdatedAt = SYSDATETIME(), UpdatedBy = ? "
            "WHERE NhuCauMe = ?",
            (_actor_id(user), nhu_cau_me),
        )
        cur.execute("DELETE FROM app.tDemandRoot WHERE NhuCauMe = ?", (nhu_cau_me,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Không tìm thấy Nhu cầu mẹ")
    return {"ok": True}


# ============================================================
# M5 — Plan (Nhu cầu con) — tPlanMaster + tPlanPO
# ============================================================
@router.get("/api/plan/candidates")
def api_plan_candidates(request: Request):
    """List MONo từ MES `tMOM` chưa có trong app.tPlanMaster, kèm 2 điều kiện lọc.

    1. MIN(ShtDate) trong tRecentWork >= PLAN_CANDIDATE_START_DATE
    2. Có sản lượng ra chuyền > 0 (SUM(Qty) WHERE StRole=13 AND IsLastSeq=1)
    """
    force_refresh = request.query_params.get("refresh") == "1"
    now = time.monotonic()
    if not force_refresh and _plan_candidate_cache["expires_at"] > now:
        return _plan_candidate_cache["rows"]

    rows = db.query(
        """
        WITH FinalOutput AS (
            SELECT rw.MONo, SUM(rw.Qty) AS QtyOut
            FROM {MES_DB}.dbo.tRecentWork rw
            INNER JOIN {MES_DB}.dbo.tStation st ON rw.Station_guid = st.guid
            WHERE rw.ShtDate >= ?
              AND st.StRole = 13
              AND rw.IsLastSeq = 1
              AND rw.MONo IS NOT NULL
              AND rw.MONo <> ''
            GROUP BY rw.MONo
            HAVING SUM(rw.Qty) > 0
        )
        SELECT fo.MONo
        FROM FinalOutput fo
        WHERE EXISTS (
            SELECT 1
            FROM {MES_DB}.dbo.tMOM mm
            WHERE mm.MONo = fo.MONo
        )
          AND NOT EXISTS (
            SELECT 1
            FROM app.tPlanMaster pm
            WHERE pm.MONo = fo.MONo
          )
          AND NOT EXISTS (
            SELECT 1
            FROM {MES_DB}.dbo.tRecentWork rw_before
            WHERE rw_before.MONo = fo.MONo
              AND rw_before.ShtDate < ?
          )
        ORDER BY fo.MONo
        """,
        (PLAN_CANDIDATE_START_DATE, PLAN_CANDIDATE_START_DATE),
    )
    out = []
    for r in rows:
        mono = r["MONo"]
        parts = parse_mono(mono)
        if parts["SoDonHang"] and parts["StyleNo"]:
            out.append({"MONo": mono, **parts})
    _plan_candidate_cache["rows"] = out
    _plan_candidate_cache["expires_at"] = now + PLAN_CANDIDATE_CACHE_TTL_SECONDS
    return out


@router.get("/api/plan/candidates/{mono}/daily-output")
def api_plan_candidate_daily_output(mono: str):
    """Sản lượng KCS (StRole=13, IsLastSeq=1) theo từng ngày cho 1 MONo — đọc MES."""
    rows = db.query(
        """
        SELECT
            CONVERT(varchar(10), rw.ShtDate, 120) AS ShtDate,
            SUM(rw.Qty) AS Qty
        FROM {MES_DB}.dbo.tRecentWork rw
        INNER JOIN {MES_DB}.dbo.tStation st ON rw.Station_guid = st.guid
        WHERE rw.MONo = ?
          AND st.StRole = 13
          AND rw.IsLastSeq = 1
        GROUP BY rw.ShtDate
        ORDER BY rw.ShtDate
        """,
        (mono,),
    )
    total = sum(r["Qty"] for r in rows)
    return {"mono": mono, "rows": rows, "total": total}


class POIn(AdminModel):
    po_no: str = Field(..., alias="PONo")
    qty: int = Field(..., alias="Qty", gt=0)
    ship_date: date = Field(..., alias="ShipDate")
    notes: Optional[str] = Field(None, alias="Notes")

class PlanIn(AdminModel):
    mono: str = Field(..., alias="MONo")
    so_don_hang: str = Field(..., alias="SoDonHang")
    style_no: str = Field(..., alias="StyleNo")
    line_no: int = Field(..., alias="LineNo", ge=1, le=99)
    first_hang_date: date = Field(..., alias="FirstHangDate")
    slkh: int = Field(..., alias="SLKH", gt=0)
    daily_aim: Optional[int] = Field(None, alias="DailyAim", gt=0)
    customer: Optional[str] = Field(None, alias="Customer")
    nhu_cau_me: Optional[str] = Field(None, alias="NhuCauMe")
    loai_hang: Optional[str] = Field(None, alias="LoaiHang")
    notes: Optional[str] = Field(None, alias="Notes")
    pos: list[POIn] = Field(default_factory=list, alias="POs")


class DemandPlanIn(PlanIn):
    nhu_cau_me: str = Field(..., alias="NhuCauMe")
    demand_notes: Optional[str] = Field(None, alias="DemandNotes")
    dmkt: float = Field(..., alias="DMKT", gt=0)
    phan_loai_dh: str = Field(..., alias="PhanLoaiDH")
    ld_bien_che: int = Field(..., alias="LDBienChe", gt=0)


class AdjustmentIn(AdminModel):
    delta_qty: int = Field(..., alias="DeltaQty")
    reason: str = Field(..., alias="Reason", min_length=1, max_length=100)
    notes: Optional[str] = Field(None, alias="Notes", max_length=500)

def _enrich_plan_rows(rows: list[dict]) -> list[dict]:
    """Thêm EndDateExpected (computed) + PO count cho mỗi plan."""
    if not rows:
        return rows
    holidays = get_holidays()
    guids = [r["PlanMaster_guid"] for r in rows]
    # Đếm PO + sum Qty per plan (1 query)
    placeholders = ",".join(["?"] * len(guids))
    po_rows = db.query(
        f"SELECT PlanMaster_guid, COUNT(*) AS POCount, SUM(Qty) AS POQtySum "
        f"FROM app.tPlanPO WHERE PlanMaster_guid IN ({placeholders}) "
        f"GROUP BY PlanMaster_guid",
        guids,
    )
    po_map = {r["PlanMaster_guid"]: r for r in po_rows}
    adj_rows = db.query(
        f"SELECT PlanMaster_guid, SUM(DeltaQty) AS AdjustmentQty, COUNT(*) AS AdjustmentCount "
        f"FROM app.tPlanAdjustment WHERE PlanMaster_guid IN ({placeholders}) "
        f"GROUP BY PlanMaster_guid",
        guids,
    )
    adj_map = {r["PlanMaster_guid"]: r for r in adj_rows}
    for r in rows:
        po = po_map.get(r["PlanMaster_guid"], {})
        adj = adj_map.get(r["PlanMaster_guid"], {})
        base_slkh = int(r.get("SLKH") or 0)
        adjustment_qty = int(adj.get("AdjustmentQty") or 0)
        effective_slkh = max(0, base_slkh + adjustment_qty)
        r["POCount"] = po.get("POCount", 0)
        r["POQtySum"] = int(po.get("POQtySum") or 0)
        r["BaseSLKH"] = base_slkh
        r["AdjustmentQty"] = adjustment_qty
        r["AdjustmentCount"] = int(adj.get("AdjustmentCount") or 0)
        r["EffectiveSLKH"] = effective_slkh
        end = compute_end_date(r["FirstHangDate"], effective_slkh, r["DailyAim"], holidays)
        r["EndDateExpected"] = end.isoformat() if end else None
        # Stringify date for JSON
        r["FirstHangDate"] = r["FirstHangDate"].isoformat() if r["FirstHangDate"] else None
        # Stringify guid
        r["PlanMaster_guid"] = str(r["PlanMaster_guid"])
    return rows


@router.get("/api/plan")
def api_plan_list():
    rows = db.query(
        "SELECT pm.PlanMaster_guid, pm.MONo, pm.SoDonHang, pm.StyleNo, "
        "pm.[LineNo] AS LineNoOut, pm.FirstHangDate, pm.SLKH, pm.DailyAim, "
        "pm.Customer, pm.NhuCauMe, pm.LoaiHang, pm.Notes, "
        "dr.DMKT, dr.PhanLoaiDH, dr.LDBienChe, dr.Notes AS DemandNotes, "
        "pm.CreatedBy, "
        "CONVERT(varchar(19), pm.CreatedAt, 120) AS CreatedAt "
        "FROM app.tPlanMaster pm "
        "LEFT JOIN app.tDemandRoot dr ON dr.NhuCauMe = pm.NhuCauMe "
        "ORDER BY pm.FirstHangDate DESC, pm.[LineNo], pm.SoDonHang"
    )
    return _enrich_plan_rows(rows)


@router.get("/api/plan/{guid}")
def api_plan_detail(guid: str):
    rows = db.query(
        "SELECT pm.PlanMaster_guid, pm.MONo, pm.SoDonHang, pm.StyleNo, "
        "pm.[LineNo] AS LineNoOut, pm.FirstHangDate, pm.SLKH, pm.DailyAim, "
        "pm.Customer, pm.NhuCauMe, pm.LoaiHang, pm.Notes, "
        "dr.DMKT, dr.PhanLoaiDH, dr.LDBienChe, dr.Notes AS DemandNotes "
        "FROM app.tPlanMaster pm "
        "LEFT JOIN app.tDemandRoot dr ON dr.NhuCauMe = pm.NhuCauMe "
        "WHERE pm.PlanMaster_guid = ?",
        (guid,),
    )
    if not rows:
        raise HTTPException(404, "Plan không tồn tại")
    plan = _enrich_plan_rows(rows)[0]
    plan["POs"] = db.query(
        "SELECT PlanPO_guid, PONo, Qty, "
        "CONVERT(varchar(10), ShipDate, 120) AS ShipDate, Notes "
        "FROM app.tPlanPO WHERE PlanMaster_guid = ? ORDER BY ShipDate, PONo",
        (guid,),
    )
    return plan


@router.post("/api/plan")
def api_plan_create(body: PlanIn, user: dict = Depends(auth.require_admin)):
    new_guid = uuid.uuid4()
    try:
        with db.get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO app.tPlanMaster "
                "(PlanMaster_guid, MONo, SoDonHang, StyleNo, [LineNo], "
                "FirstHangDate, SLKH, DailyAim, Customer, NhuCauMe, LoaiHang, Notes, CreatedBy) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_guid, body.mono, body.so_don_hang, body.style_no, body.line_no,
                 body.first_hang_date, body.slkh, body.daily_aim, body.customer,
                 body.nhu_cau_me, body.loai_hang, body.notes, _actor_id(user)),
            )
            for po in body.pos:
                cur.execute(
                    "INSERT INTO app.tPlanPO (PlanMaster_guid, PONo, Qty, ShipDate, "
                    "Notes, CreatedBy) VALUES (?,?,?,?,?,?)",
                    (new_guid, po.po_no, po.qty, po.ship_date, po.notes, _actor_id(user)),
                )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Lưu thất bại: {exc}") from exc
    _clear_plan_candidate_cache()
    return {"ok": True, "guid": str(new_guid)}


@router.post("/api/plan/setup-root")
def api_plan_setup_root(body: DemandPlanIn, user: dict = Depends(auth.require_admin)):
    """Create one DemandRoot and its first PlanMaster from a selected MONo."""
    new_guid = uuid.uuid4()
    cur = None
    try:
        with db.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("BEGIN TRAN")
            cur.execute(
                "SELECT 1 FROM app.tDemandRoot WHERE NhuCauMe = ?",
                (body.nhu_cau_me,),
            )
            if cur.fetchone():
                cur.execute("ROLLBACK TRAN")
                raise HTTPException(400, f"NhuCauMe `{body.nhu_cau_me}` da ton tai.")

            cur.execute(
                "INSERT INTO app.tDemandRoot "
                "(NhuCauMe, StyleNo, DMKT, PhanLoaiDH, [LineNo], "
                "LDBienChe, Notes, CreatedBy) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (body.nhu_cau_me, body.style_no, body.dmkt, body.phan_loai_dh,
                 body.line_no, body.ld_bien_che, body.demand_notes, _actor_id(user)),
            )
            cur.execute(
                "INSERT INTO app.tPlanMaster "
                "(PlanMaster_guid, MONo, SoDonHang, StyleNo, [LineNo], "
                "FirstHangDate, SLKH, DailyAim, Customer, NhuCauMe, LoaiHang, Notes, CreatedBy) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_guid, body.mono, body.so_don_hang, body.style_no, body.line_no,
                 body.first_hang_date, body.slkh, body.daily_aim, body.customer,
                 body.nhu_cau_me, body.loai_hang, body.notes, _actor_id(user)),
            )
            for po in body.pos:
                cur.execute(
                    "INSERT INTO app.tPlanPO (PlanMaster_guid, PONo, Qty, ShipDate, "
                    "Notes, CreatedBy) VALUES (?,?,?,?,?,?)",
                    (new_guid, po.po_no, po.qty, po.ship_date, po.notes, _actor_id(user)),
                )
            cur.execute("COMMIT TRAN")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        try:
            if cur is not None:
                cur.execute("IF @@TRANCOUNT > 0 ROLLBACK TRAN")
        except Exception:
            pass
        raise HTTPException(400, f"Luu that bai: {exc}") from exc
    _clear_plan_candidate_cache()
    return {"ok": True, "guid": str(new_guid), "NhuCauMe": body.nhu_cau_me}


class PlanUpdate(AdminModel):
    style_no: str = Field(..., alias="StyleNo")
    line_no: int = Field(..., alias="LineNo", ge=1, le=99)
    first_hang_date: date = Field(..., alias="FirstHangDate")
    slkh: int = Field(..., alias="SLKH", gt=0)
    daily_aim: Optional[int] = Field(None, alias="DailyAim", gt=0)
    customer: Optional[str] = Field(None, alias="Customer")
    nhu_cau_me: Optional[str] = Field(None, alias="NhuCauMe")
    dmkt: float = Field(..., alias="DMKT", gt=0)
    phan_loai_dh: str = Field(..., alias="PhanLoaiDH")
    ld_bien_che: int = Field(..., alias="LDBienChe", gt=0)
    demand_notes: Optional[str] = Field(None, alias="DemandNotes")
    loai_hang: Optional[str] = Field(None, alias="LoaiHang")
    notes: Optional[str] = Field(None, alias="Notes")

@router.put("/api/plan/{guid}")
def api_plan_update(guid: str, body: PlanUpdate, user: dict = Depends(auth.require_admin)):
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT NhuCauMe FROM app.tPlanMaster WHERE PlanMaster_guid = ?",
            (guid,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Plan khong ton tai")
        current_nhu_cau_me = row[0]
        cur.execute(
            "UPDATE app.tDemandRoot SET "
            "StyleNo = ?, DMKT = ?, PhanLoaiDH = ?, [LineNo] = ?, "
            "LDBienChe = ?, Notes = ?, UpdatedAt = SYSDATETIME(), UpdatedBy = ? "
            "WHERE NhuCauMe = ?",
            (
                body.style_no,
                body.dmkt,
                body.phan_loai_dh,
                body.line_no,
                body.ld_bien_che,
                body.demand_notes,
                _actor_id(user),
                current_nhu_cau_me,
            ),
        )
        cur.execute(
            "UPDATE app.tPlanMaster SET "
            "StyleNo = ?, [LineNo] = ?, FirstHangDate = ?, SLKH = ?, DailyAim = ?, "
            "Customer = ?, NhuCauMe = ?, LoaiHang = ?, Notes = ?, "
            "UpdatedAt = SYSDATETIME(), UpdatedBy = ? "
            "WHERE PlanMaster_guid = ?",
            (body.style_no, body.line_no, body.first_hang_date, body.slkh, body.daily_aim,
             body.customer, body.nhu_cau_me, body.loai_hang, body.notes, _actor_id(user), guid),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Plan không tồn tại")
    _clear_plan_candidate_cache()
    return {"ok": True}


@router.delete("/api/plan/{guid}")
def api_plan_delete(guid: str):
    with db.get_conn() as conn:
        cur = conn.cursor()
        # tPlanPO có ON DELETE CASCADE → tự xoá theo
        cur.execute("DELETE FROM app.tPlanMaster WHERE PlanMaster_guid = ?", (guid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Plan không tồn tại")
    _clear_plan_candidate_cache()
    return {"ok": True}


# --- Proxy API: lấy danh mục loại hàng từ QLCL ---

@router.get("/api/plan/{guid}/adjustments")
def api_plan_adjustment_list(guid: str):
    return db.query(
        "SELECT Adjustment_guid, DeltaQty, Reason, Notes, CreatedBy, "
        "CONVERT(varchar(19), CreatedAt, 120) AS CreatedAt "
        "FROM app.tPlanAdjustment "
        "WHERE PlanMaster_guid = ? "
        "ORDER BY CreatedAt DESC, Adjustment_guid DESC",
        (guid,),
    )


@router.post("/api/plan/{guid}/adjustments")
def api_plan_adjustment_create(guid: str, body: AdjustmentIn, user: dict = Depends(auth.require_admin)):
    if body.delta_qty == 0:
        raise HTTPException(400, "So luong dieu chinh phai khac 0.")
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM app.tPlanMaster WHERE PlanMaster_guid = ?", (guid,))
        if not cur.fetchone():
            raise HTTPException(404, "Plan khong ton tai")
        cur.execute(
            "INSERT INTO app.tPlanAdjustment "
            "(PlanMaster_guid, DeltaQty, Reason, Notes, CreatedBy) "
            "VALUES (?,?,?,?,?)",
            (guid, body.delta_qty, body.reason, body.notes, _actor_id(user)),
        )
    return {"ok": True}


@router.delete("/api/plan-adjustments/{adjustment_guid}")
def api_plan_adjustment_delete(adjustment_guid: str):
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM app.tPlanAdjustment WHERE Adjustment_guid = ?",
            (adjustment_guid,),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Dieu chinh khong ton tai")
    return {"ok": True}


@router.get("/api/dm-loai-hang")
def api_dm_loai_hang_proxy():
    """Proxy lấy danh sách loại hàng từ app QLCL (dm_loai_hang.ten_loai)."""
    try:
        req = _qlcl_request("/api/dm/loai-hang")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        # Return only ten_loai list for dropdown
        rows = data.get("rows", [])
        return {"rows": [{"ten_loai": r["ten_loai"]} for r in rows]}
    except Exception as exc:  # noqa: BLE001
        return {"rows": [], "error": f"Không kết nối được QLCL: {exc}"}


def _push_daily_output_to_qlcl(monos: list[str]) -> dict | None:
    """Push daily MES output (StRole=13, IsLastSeq=1) for given MONos to QLCL."""
    if not monos:
        return None
    today_str = date.today().strftime("%Y-%m-%d")
    placeholders = ",".join(["?"] * len(monos))
    rows = db.query(
        f"""
        SELECT rw.MONo, COALESCE(SUM(rw.Qty), 0) AS Qty
        FROM {{MES_DB}}.dbo.tRecentWork rw
        JOIN {{MES_DB}}.dbo.tStation st ON st.StNo = rw.StNo
        WHERE rw.MONo IN ({placeholders})
          AND st.StRole = 13
          AND rw.IsLastSeq = 1
          AND CONVERT(DATE, rw.ShtDate) = ?
        GROUP BY rw.MONo
        """,
        (*monos, today_str),
    )
    mono_qty = {str(r["MONo"]): int(r["Qty"]) for r in rows}
    outputs = [{"mono": m, "qty": mono_qty.get(m, 0)} for m in monos]

    body = json.dumps({
        "don_vi": QLCL_DON_VI,
        "date": today_str,
        "outputs": outputs,
    }).encode()
    req = _qlcl_request("/api/qc/hanging-output/push", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _do_sync_to_qlcl() -> dict:
    """Core logic: đọc tPlanMaster → push sang QLCL. Gọi được từ cả endpoint lẫn background thread."""
    plan_rows = db.query(
        """
        SELECT CAST(pm.PlanMaster_guid AS NVARCHAR(36)) AS guid,
               pm.MONo,
               pm.SoDonHang,
               pm.StyleNo,
               pm.[LineNo],
               pm.LoaiHang,
               CONVERT(VARCHAR(10), pm.FirstHangDate, 120) AS FirstHangDate,
               pm.SLKH,
               pm.Customer,
               ISNULL((SELECT SUM(Qty) FROM app.tPlanPO po
                        WHERE po.PlanMaster_guid = pm.PlanMaster_guid),
                      pm.SLKH + ISNULL(adj.AdjustmentQty, 0)) AS TotalPOQty
        FROM app.tPlanMaster pm
        OUTER APPLY (
            SELECT SUM(DeltaQty) AS AdjustmentQty
            FROM app.tPlanAdjustment pa
            WHERE pa.PlanMaster_guid = pm.PlanMaster_guid
        ) adj
        ORDER BY pm.FirstHangDate DESC, pm.CreatedAt DESC
        """
    )

    plans = []
    for r in plan_rows:
        mono = str(r.get("MONo") or "").strip()
        if not mono:
            continue
        plans.append({
            "guid":       str(r["guid"]),
            "mono":       mono,
            "ke_hoach":   f"HL-{mono}",
            "line_no":    r.get("LineNo") or 0,
            "style_no":   str(r.get("StyleNo") or "").strip(),
            "customer":   str(r.get("Customer") or "").strip(),
            "loai_hang":  str(r.get("LoaiHang") or "").strip() or None,
            "first_hang": r.get("FirstHangDate"),
            "san_luong":  int(r.get("TotalPOQty") or r.get("SLKH") or 0),
        })

    if not plans:
        return {"status": "ok", "message": "Không có kế hoạch nào", "inserted": 0, "updated": 0}

    body = json.dumps({"don_vi": QLCL_DON_VI, "plans": plans}).encode()
    req = _qlcl_request("/api/prod-plan/push-from-hl", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())

    # Push daily MES output alongside plan sync
    try:
        _push_daily_output_to_qlcl([p["mono"] for p in plans if p.get("mono")])
    except Exception:
        logger.exception("Failed to push daily output to QLCL")

    return result


def _refresh_plan_employee_assignments(plan_master_guid: str | None = None) -> dict:
    """Rebuild local assignment cache from MES output history for declared plans."""
    where_clause = "WHERE PlanMaster_guid = ?" if plan_master_guid else ""
    params = (plan_master_guid,) if plan_master_guid else ()
    plan_rows = db.query(
        f"""
        SELECT PlanMaster_guid, MONo, NhuCauMe, [LineNo] AS LineNoOut
        FROM app.tPlanMaster
        {where_clause}
        ORDER BY FirstHangDate DESC, CreatedAt DESC
        """,
        params,
    )
    refreshed = 0
    assignment_rows: list[dict] = []

    with db.get_conn() as conn:
        cur = conn.cursor()
        for plan in plan_rows:
            plan_guid = plan["PlanMaster_guid"]
            root_mono = str(plan.get("MONo") or "").strip()
            if not root_mono:
                continue

            rows = db.query(
                """
                ;WITH RouteSeq AS (
                    SELECT ds.Odr, ds.SeqNo, COALESCE(sd.SeqName, ds.SeqNo) AS SeqName
                    FROM {MES_DB}.dbo.tMOM mm
                    JOIN {MES_DB}.dbo.tRouteM rm ON rm.MOM_guid = mm.guid
                    JOIN {MES_DB}.dbo.tRouteDS ds ON ds.RouteM_guid = rm.guid
                    LEFT JOIN {MES_DB}.dbo.tMOSeqM sm ON sm.MOM_guid = mm.guid
                    LEFT JOIN {MES_DB}.dbo.tMOSeqD sd
                      ON sd.MOSeqM_guid = sm.guid AND sd.SeqNo = ds.SeqNo
                    WHERE mm.MONo = ?
                      AND ds.IsUsing = 1
                )
                SELECT
                    w.MONo AS SourceMONo,
                    w.WorkLine,
                    w.StNo,
                    rs.Odr,
                    rs.SeqNo,
                    rs.SeqName,
                    w.EmpID,
                    w.EmpName,
                    SUM(w.Qty) AS Qty,
                    MIN(w.ShtDate) AS FirstWorkDate,
                    MAX(w.ShtDate) AS LastWorkDate
                FROM {MES_DB}.dbo.vHangerRecentWorkSum
                w
                JOIN RouteSeq rs ON rs.SeqNo = w.SeqNo
                WHERE w.MONo = ?
                  AND EXISTS (
                      SELECT 1
                      FROM {MES_DB}.dbo.tStation st
                      WHERE st.StNo = w.StNo
                        AND st.StRole = 13
                  )
                  AND w.EmpID IS NOT NULL AND LTRIM(RTRIM(w.EmpID)) <> ''
                  AND UPPER(LTRIM(RTRIM(w.EmpID))) <> 'TEST'
                  AND w.EmpName IS NOT NULL AND LTRIM(RTRIM(w.EmpName)) <> ''
                GROUP BY w.MONo, w.WorkLine, w.StNo, rs.Odr, rs.SeqNo, rs.SeqName, w.EmpID, w.EmpName
                """,
                (root_mono, root_mono),
            )

            cur.execute(
                "DELETE FROM app.tPlanEmployeeAssignment WHERE PlanMaster_guid = ?",
                (plan_guid,),
            )
            bo_phan = str(plan.get("LineNoOut")).strip() if plan.get("LineNoOut") is not None else None
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO app.tPlanEmployeeAssignment
                        (PlanMaster_guid, NhuCauMe, RootMONo, SourceMONo, DonVi,
                         [LineNo], BoPhan, WorkLine, StNo, Odr, SeqNo, SeqName,
                         EmpID, EmpName, Qty, FirstWorkDate, LastWorkDate)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        plan_guid,
                        plan.get("NhuCauMe"),
                        root_mono,
                        r.get("SourceMONo"),
                        QLCL_DON_VI,
                        plan.get("LineNoOut"),
                        bo_phan,
                        r.get("WorkLine"),
                        r.get("StNo"),
                        r.get("Odr"),
                        r.get("SeqNo"),
                        r.get("SeqName"),
                        str(r.get("EmpID") or "").strip(),
                        str(r.get("EmpName") or "").strip(),
                        int(r.get("Qty") or 0),
                        r.get("FirstWorkDate"),
                        r.get("LastWorkDate"),
                    ),
                )
            refreshed += len(rows)

    assignment_filter = "WHERE PlanMaster_guid = ?" if plan_master_guid else ""
    assignment_params = (plan_master_guid,) if plan_master_guid else ()
    assignment_rows = db.query(
        f"""
        SELECT DonVi, BoPhan, EmpID, EmpName, Odr, SeqName, SUM(Qty) AS Qty
        FROM app.tPlanEmployeeAssignment
        {assignment_filter}
        GROUP BY DonVi, BoPhan, EmpID, EmpName, Odr, SeqName
        """,
        assignment_params,
    )
    return {
        "plans": len(plan_rows),
        "assignments": refreshed,
        "employee_rows": assignment_rows,
    }


def _build_qc_employee_payload(employee_rows: list[dict]) -> list[dict]:
    employees: dict[str, dict] = {}
    for row in employee_rows:
        emp_id = str(row.get("EmpID") or "").strip()
        emp_name = str(row.get("EmpName") or "").strip()
        if not emp_id or not emp_name:
            continue
        target = employees.setdefault(
            emp_id,
            {
                "ma_nv": emp_id,
                "ho_ten": emp_name,
                "bo_phan": row.get("BoPhan") or "",
                "station": set(),
            },
        )
        if not target.get("bo_phan") and row.get("BoPhan"):
            target["bo_phan"] = row.get("BoPhan")
        odr = row.get("Odr")
        seq_name = str(row.get("SeqName") or "").strip()
        if odr and seq_name:
            target["station"].add(f"Odr {odr} - {seq_name}")

    out = []
    for item in employees.values():
        station = sorted(item.pop("station"))
        item["station"] = station
        out.append(item)
    out.sort(key=lambda x: x["ma_nv"])
    return out


def _do_sync_qc_employees_to_qlcl(plan_master_guid: str | None = None) -> dict:
    refreshed = _refresh_plan_employee_assignments(plan_master_guid)
    employees = _build_qc_employee_payload(refreshed["employee_rows"])
    if not employees:
        return {
            "status": "ok",
            "message": "Không có nhân viên/công đoạn để đồng bộ",
            "plans": refreshed["plans"],
            "assignments": refreshed["assignments"],
            "employees": 0,
            "inserted": 0,
            "updated": 0,
        }

    body = json.dumps({
        "don_vi": QLCL_DON_VI,
        "replace_station_scope": plan_master_guid is None,
        "employees": employees,
    }).encode()
    req = _qlcl_request("/api/qc/employees/push-from-hl", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())

    with db.get_conn() as conn:
        cur = conn.cursor()
        if plan_master_guid:
            cur.execute(
                "UPDATE app.tPlanEmployeeAssignment SET SyncedAt = SYSDATETIME() "
                "WHERE DonVi = ? AND PlanMaster_guid = ?",
                (QLCL_DON_VI, plan_master_guid),
            )
        else:
            cur.execute(
                "UPDATE app.tPlanEmployeeAssignment SET SyncedAt = SYSDATETIME() "
                "WHERE DonVi = ?",
                (QLCL_DON_VI,),
            )

    result["plans"] = refreshed["plans"]
    result["assignments"] = refreshed["assignments"]
    result["employees"] = len(employees)
    return result


@router.post("/api/sync-to-qlcl")
def api_sync_to_qlcl():
    """Push kế hoạch từ SQL Server XN sang QLCL server — gọi từ admin UI."""
    try:
        return _do_sync_to_qlcl()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise HTTPException(status_code=502, detail=f"QLCL trả lỗi {exc.code}: {detail}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Không kết nối được QLCL: {exc}")


@router.post("/api/sync-qc-employees-to-qlcl")
async def api_sync_qc_employees_to_qlcl(request: Request):
    """Push EmpID/Seq assignments from hanging app to QLCL quality_employees."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    plan_master_guid = str(payload.get("PlanMaster_guid") or "").strip() or None
    try:
        return _do_sync_qc_employees_to_qlcl(plan_master_guid)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise HTTPException(status_code=502, detail=f"QLCL trả lỗi {exc.code}: {detail}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Không đồng bộ được nhân sự sang QLCL: {exc}")


@router.get("/qc-assignment")
def page_qc_assignment(request: Request):
    return templates.TemplateResponse(
        "admin/qc-assignment.html",
        {"request": request, "user": request.state.current_user},
    )


@router.get("/api/plan-employee-assignments")
def api_plan_employee_assignments(
    line_no: Optional[int] = None,
    mono: Optional[str] = None,
):
    where = "1=1"
    params: list[Any] = []
    if line_no is not None:
        where += " AND a.[LineNo] = ?"
        params.append(line_no)
    if mono:
        where += " AND a.RootMONo = ?"
        params.append(mono)
    return db.query(
        f"""
        SELECT a.RootMONo, a.SourceMONo, a.DonVi, a.BoPhan,
            a.WorkLine, a.StNo, a.Odr, a.SeqNo, a.SeqName,
            a.EmpID, a.EmpName, a.Qty,
            CONVERT(varchar(10), a.FirstWorkDate, 120) AS FirstWorkDate,
            CONVERT(varchar(10), a.LastWorkDate, 120) AS LastWorkDate,
            CONVERT(varchar(19), a.SyncedAt, 120) AS SyncedAt
        FROM app.tPlanEmployeeAssignment a
        WHERE {where}
        ORDER BY a.Odr, a.SeqName, a.EmpName
        """,
        params if params else None,
    )


@router.get("/api/plan-employee-assignments/lines")
def api_assignment_lines():
    rows = db.query(
        "SELECT DISTINCT a.[LineNo] "
        "FROM app.tPlanEmployeeAssignment a "
        "WHERE a.[LineNo] IS NOT NULL "
        "ORDER BY a.[LineNo]"
    )
    return [{"line_no": r["LineNo"]} for r in rows]


@router.get("/api/plan-employee-assignments/monos")
def api_assignment_monos(line_no: Optional[int] = None):
    where = "1=1"
    params: list[Any] = []
    if line_no is not None:
        where += " AND a.[LineNo] = ?"
        params.append(line_no)
    return db.query(
        f"""
        SELECT DISTINCT a.RootMONo,
            pm.SoDonHang, pm.StyleNo, pm.Customer, pm.[LineNo] AS LineNoOut
        FROM app.tPlanEmployeeAssignment a
        INNER JOIN app.tPlanMaster pm ON pm.PlanMaster_guid = a.PlanMaster_guid
        WHERE {where}
        ORDER BY a.RootMONo
        """,
        params if params else None,
    )


@router.post("/api/plan/{guid}/po")
def api_po_add(guid: str, body: POIn, user: dict = Depends(auth.require_admin)):
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO app.tPlanPO (PlanMaster_guid, PONo, Qty, ShipDate, "
            "Notes, CreatedBy) VALUES (?,?,?,?,?,?)",
            (guid, body.po_no, body.qty, body.ship_date, body.notes, _actor_id(user)),
        )
    return {"ok": True}


@router.delete("/api/po/{po_guid}")
def api_po_delete(po_guid: str):
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM app.tPlanPO WHERE PlanPO_guid = ?", (po_guid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "PO không tồn tại")
    return {"ok": True}


# ============================================================
# M6 — Cluster station config (6 trạm cho TV-2 + WIP)
# ============================================================
@router.get("/cluster")
def page_cluster(request: Request):
    return templates.TemplateResponse(
        "admin/cluster.html", {"request": request, "user": request.state.current_user}
    )


_CLUSTER_GROUP_SQL = """
    ;WITH Steps AS (
      SELECT ds.Odr, ds.SeqNo, ds.IsCombine, sd.SeqName,
             MAX(CASE WHEN ds.IsCombine = 0 THEN ds.Odr END)
               OVER (ORDER BY ds.Odr ROWS UNBOUNDED PRECEDING) AS HeadOdr,
             rm.guid AS RouteM_guid
      FROM {MES_DB}.dbo.tRouteDS ds
      JOIN {MES_DB}.dbo.tRouteM rm ON ds.RouteM_guid = rm.guid
      JOIN {MES_DB}.dbo.tMOM mm ON rm.MOM_guid = mm.guid
      LEFT JOIN {MES_DB}.dbo.tMOSeqM sm ON sm.MOM_guid = mm.guid
      LEFT JOIN {MES_DB}.dbo.tMOSeqD sd ON sd.MOSeqM_guid = sm.guid AND sd.SeqNo = ds.SeqNo
      WHERE mm.MONo = ?
    ),
    Groups AS (
      SELECT HeadOdr,
             COUNT(*) AS StepCount,
             MIN(RouteM_guid) AS RouteM_guid
      FROM Steps
      GROUP BY HeadOdr
    )
    SELECT g.HeadOdr AS RouteStepOdr,
           STUFF((
             SELECT ' + ' + ISNULL(s2.SeqName, '')
             FROM Steps s2
             WHERE s2.HeadOdr = g.HeadOdr
             ORDER BY s2.Odr
             FOR XML PATH(''), TYPE
           ).value('.', 'nvarchar(max)'), 1, 3, '') AS GroupLabel,
           STUFF((
             SELECT '+' + CAST(s2.SeqNo AS varchar(10))
             FROM Steps s2
             WHERE s2.HeadOdr = g.HeadOdr
             ORDER BY s2.Odr
             FOR XML PATH(''), TYPE
           ).value('.', 'nvarchar(max)'), 1, 1, '') AS SeqNoList,
           g.StepCount,
           ISNULL(STUFF((
             SELECT ',' + CAST(st.StNo AS varchar(10))
             FROM {MES_DB}.dbo.tRouteDT dt
             JOIN {MES_DB}.dbo.tStation st ON dt.Station_guid = st.guid
             WHERE dt.RouteM_guid = g.RouteM_guid
               AND dt.SeqNo IN (SELECT SeqNo FROM Steps WHERE HeadOdr = g.HeadOdr)
             ORDER BY st.StNo
             FOR XML PATH(''), TYPE
           ).value('.', 'nvarchar(max)'), 1, 1, ''), '') AS StationNos
    FROM Groups g
    ORDER BY g.HeadOdr;
"""


def _resolve_canonical_mono(nhu_cau_me: str) -> Optional[str]:
    """NhuCauMe = SoDonHang con đầu → lookup MONo của con đó."""
    rows = db.query(
        "SELECT TOP 1 MONo FROM app.tPlanMaster WHERE SoDonHang = ?",
        (nhu_cau_me,),
    )
    return rows[0]["MONo"] if rows else None


@router.get("/api/cluster/list")
def api_cluster_list():
    """List NhuCauMe + trạng thái cluster config."""
    return db.query(
        """
        SELECT dr.NhuCauMe, dr.StyleNo, dr.[LineNo] AS LineNoOut,
               (SELECT COUNT(*) FROM app.tClusterStationConfig c
                WHERE c.NhuCauMe = dr.NhuCauMe) AS ClusterCount
        FROM app.tDemandRoot dr
        ORDER BY dr.[LineNo], dr.NhuCauMe
        """
    )


@router.get("/api/cluster/groups/{nhu_cau_me:path}")
def api_cluster_groups(nhu_cau_me: str):
    mono = _resolve_canonical_mono(nhu_cau_me)
    if not mono:
        raise HTTPException(404, f"Không tìm thấy NhuCauCon '{nhu_cau_me}'")
    return {
        "MONo": mono,
        "Groups": db.query(_CLUSTER_GROUP_SQL, (mono,)),
    }


@router.get("/api/cluster/{nhu_cau_me:path}")
def api_cluster_get(nhu_cau_me: str):
    return db.query(
        "SELECT Cluster_guid, ClusterOrder, RouteStepOdr, GroupLabel, Role "
        "FROM app.tClusterStationConfig WHERE NhuCauMe = ? "
        "ORDER BY ClusterOrder",
        (nhu_cau_me,),
    )


class ClusterPick(AdminModel):
    cluster_order: int = Field(..., alias="ClusterOrder", ge=1, le=6)
    route_step_odr: int = Field(..., alias="RouteStepOdr")
    group_label: str = Field(..., alias="GroupLabel")
    role: Optional[str] = Field(None, alias="Role")

class ClusterIn(AdminModel):
    picks: list[ClusterPick] = Field(..., alias="Picks")

@router.put("/api/cluster/{nhu_cau_me:path}")
def api_cluster_save(nhu_cau_me: str, body: ClusterIn, user: dict = Depends(auth.require_admin)):
    """Replace mode: xoá hết config cũ → insert 6 picks mới."""
    if len(body.picks) != 6:
        raise HTTPException(400, "Cần đúng 6 cụm (1 first + 4 middle + 1 last)")
    orders = sorted(p.cluster_order for p in body.picks)
    if orders != [1, 2, 3, 4, 5, 6]:
        raise HTTPException(400, "ClusterOrder phải đầy đủ 1..6, mỗi số 1 lần")
    # First = order 1 phải role='first'; Last = order 6 phải role='last'
    by_order = {p.cluster_order: p for p in body.picks}
    if by_order[1].role != "first":
        raise HTTPException(400, "Cụm order 1 phải có Role='first'")
    if by_order[6].role != "last":
        raise HTTPException(400, "Cụm order 6 phải có Role='last'")
    # Production-order check: RouteStepOdr strictly increasing
    rs_seq = [by_order[i].route_step_odr for i in range(1, 7)]
    if rs_seq != sorted(set(rs_seq)) or len(set(rs_seq)) != 6:
        raise HTTPException(400, "RouteStepOdr phải tăng dần theo thứ tự sản xuất, không trùng")

    # Verify mẹ tồn tại
    if not db.query(
        "SELECT 1 FROM app.tDemandRoot WHERE NhuCauMe = ?", (nhu_cau_me,)
    ):
        raise HTTPException(404, "NhuCauMe không tồn tại")

    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM app.tClusterStationConfig WHERE NhuCauMe = ?",
            (nhu_cau_me,),
        )
        for p in body.picks:
            cur.execute(
                "INSERT INTO app.tClusterStationConfig "
                "(NhuCauMe, ClusterOrder, RouteStepOdr, GroupLabel, Role, CreatedBy) "
                "VALUES (?,?,?,?,?,?)",
                (nhu_cau_me, p.cluster_order, p.route_step_odr,
                 p.group_label, p.role, _actor_id(user)),
            )
    return {"ok": True}


# ============================================================
# M4 — SAM (Google Sheet sync + CRUD)
# ============================================================
GS_SHEET_ID = "1fWprYtICgdRqKKt0w0szroCFMJ4C_e6QqtQ6o2SOjuc"
GS_GID = "2070629306"
GS_URL = (
    f"https://docs.google.com/spreadsheets/d/{GS_SHEET_ID}"
    f"/export?format=csv&gid={GS_GID}"
)
SAM_FACTORY_KEYWORD = "MARCH 29"
SAM_COL_STYLE = "CC - CONCEPTION"
SAM_COL_VALUE = "SAM_OWE"
SAM_COL_TARGET = "TARGET_OWE"
SAM_COL_FACTORY = "Factory"


@router.get("/api/sam")
def api_sam_list():
    return db.query(
        "SELECT StyleNo, SAM, OWE_Target, Source, "
        "CONVERT(varchar(19), UpdatedAt, 120) AS UpdatedAt, UpdatedBy "
        "FROM app.tSAM ORDER BY StyleNo"
    )


class SamIn(AdminModel):
    style_no: str = Field(..., alias="StyleNo")
    sam: float = Field(..., alias="SAM", gt=0)
    source: Optional[str] = Field(None, alias="Source")

@router.put("/api/sam/{style_no}")
def api_sam_upsert(style_no: str, body: SamIn, user: dict = Depends(auth.require_admin)):
    """Manual upsert (override). Source ghi rõ là manual."""
    actor = _actor_id(user)
    src = body.source or f"Manual override by {actor}"
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            MERGE app.tSAM AS tgt
            USING (SELECT ? AS StyleNo, ? AS SAM, ? AS Source) AS src
                  ON tgt.StyleNo = src.StyleNo
            WHEN MATCHED THEN UPDATE SET SAM = src.SAM, Source = src.Source,
                                         UpdatedAt = SYSDATETIME(),
                                         UpdatedBy = ?
            WHEN NOT MATCHED THEN INSERT (StyleNo, SAM, Source, UpdatedBy)
                                  VALUES (src.StyleNo, src.SAM, src.Source, ?);
            """,
            (style_no, body.sam, src, actor, actor),
        )
    return {"ok": True}


@router.delete("/api/sam/{style_no}")
def api_sam_delete(style_no: str):
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM app.tSAM WHERE StyleNo = ?", (style_no,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Không tìm thấy mã hàng")
    return {"ok": True}


@router.post("/api/sam/sync")
def api_sam_sync(user: dict = Depends(auth.require_admin)):
    """Fetch CSV từ Google Sheet → UPSERT app.tSAM theo StyleNo."""
    try:
        with urllib.request.urlopen(GS_URL, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            502,
            f"Không fetch được Google Sheet (kiểm tra share setting): {exc}",
        ) from exc

    reader = csv.reader(io.StringIO(raw))
    rows = list(reader)
    if len(rows) < 3:
        raise HTTPException(502, "Sheet rỗng hoặc cấu trúc lạ")

    # Row 0 = section labels, Row 1 = header
    header = rows[1]
    try:
        idx_factory = header.index(SAM_COL_FACTORY)
        idx_style = header.index(SAM_COL_STYLE)
        idx_sam = header.index(SAM_COL_VALUE)
        idx_target = header.index(SAM_COL_TARGET)
    except ValueError as e:
        raise HTTPException(
            502, f"Thiếu cột trong Sheet ({e}). Kiểm tra tiêu đề SAM/SOT Config."
        ) from e

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    src_label = f"Google Sheet · synced {timestamp}"

    inserted = updated = skipped = 0
    invalid: list[dict] = []

    with db.get_conn() as conn:
        cur = conn.cursor()
        for r in rows[2:]:
            if len(r) <= max(idx_sam, idx_target):
                continue
            factory = (r[idx_factory] or "").strip()
            style = (r[idx_style] or "").strip()
            sam_raw = (r[idx_sam] or "").strip()
            target_raw = (r[idx_target] or "").strip()
            if SAM_FACTORY_KEYWORD not in factory or not style or not sam_raw:
                continue
            try:
                sam_val = float(sam_raw.replace(",", "."))
                if sam_val <= 0:
                    raise ValueError("SAM <= 0")
            except ValueError:
                invalid.append({"StyleNo": style, "raw_sam": sam_raw})
                continue
            target_val: Optional[float] = None
            if target_raw:
                try:
                    target_val = float(target_raw.replace(",", "."))
                    if not (0 < target_val <= 1.5):
                        target_val = None  # bỏ qua nếu ngoài khoảng hợp lý
                except ValueError:
                    target_val = None

            # Check exists
            cur.execute(
                "SELECT SAM, OWE_Target FROM app.tSAM WHERE StyleNo = ?", (style,)
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO app.tSAM (StyleNo, SAM, OWE_Target, Source, UpdatedBy) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (style, sam_val, target_val, src_label, _actor_id(user)),
                )
                inserted += 1
            else:
                cur_sam = float(row[0])
                cur_target = float(row[1]) if row[1] is not None else None
                if cur_sam != sam_val or cur_target != target_val:
                    cur.execute(
                        "UPDATE app.tSAM SET SAM = ?, OWE_Target = ?, Source = ?, "
                        "UpdatedAt = SYSDATETIME(), UpdatedBy = ? WHERE StyleNo = ?",
                        (sam_val, target_val, src_label, _actor_id(user), style),
                    )
                    updated += 1
                else:
                    skipped += 1

    return {
        "ok": True,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "invalid_count": len(invalid),
        "invalid_samples": invalid[:10],
        "synced_at": timestamp,
    }


# ============================================================
# M6 — User (tổ trưởng / admin)
# ============================================================
class UserIn(AdminModel):
    user_id: str = Field(..., alias="UserID", min_length=1, max_length=50)
    display_name: Optional[str] = Field(None, alias="DisplayName")
    unit: Optional[str] = Field(None, alias="Unit")
    dept: Optional[int] = Field(None, alias="Dept", ge=1, le=10)
    role: str = Field("to_truong", alias="Role")


@router.get("/api/user")
def api_user_list():
    return db.query(
        "SELECT UserID, DisplayName, Unit, Dept, Role, "
        "CONVERT(varchar(19), CreatedAt, 120) AS CreatedAt "
        "FROM app.tUser ORDER BY Dept, UserID"
    )


@router.post("/api/user")
def api_user_create(body: UserIn):
    try:
        with db.get_conn() as conn:
            cur = conn.cursor()
            # IsActive bỏ trống → DB DEFAULT 1 (DF_tUser_IsActive)
            cur.execute(
                "INSERT INTO app.tUser "
                "(UserID, DisplayName, Unit, Dept, Role) "
                "VALUES (?, ?, ?, ?, ?)",
                (body.user_id, body.display_name, body.unit,
                 body.dept, body.role),
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Lưu thất bại: {exc}") from exc
    return {"ok": True}


class UserUpdate(AdminModel):
    display_name: Optional[str] = Field(None, alias="DisplayName")
    unit: Optional[str] = Field(None, alias="Unit")
    dept: Optional[int] = Field(None, alias="Dept", ge=1, le=10)
    role: str = Field(..., alias="Role")


@router.put("/api/user/{user_id}")
def api_user_update(user_id: str, body: UserUpdate):
    # IsActive không cập nhật qua UI — dùng sqlcmd nếu cần deactivate
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE app.tUser SET "
            "DisplayName = ?, Unit = ?, Dept = ?, Role = ? "
            "WHERE UserID = ?",
            (body.display_name, body.unit, body.dept, body.role, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "User không tồn tại")
    return {"ok": True}


@router.delete("/api/user/{user_id}")
def api_user_delete(user_id: str):
    if user_id == "admin":
        raise HTTPException(400, "Không thể xoá tài khoản admin")
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM app.tUser WHERE UserID = ?", (user_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "User không tồn tại")
    return {"ok": True}


# ============================================================
# M8 — Hiệu chỉnh lộ trình (Target Override)
# ============================================================
@router.get("/target-override")
def page_target_override(request: Request):
    return templates.TemplateResponse(
        "admin/target-override.html",
        {"request": request, "user": request.state.current_user},
    )


@router.get("/api/target-override/lines")
def api_target_override_lines():
    rows = db.query(
        "SELECT DISTINCT [LineNo] FROM app.tPlanMaster "
        "WHERE [LineNo] IS NOT NULL ORDER BY [LineNo]"
    )
    return [{"line_no": r["LineNo"]} for r in rows]


@router.get("/api/target-override/plans")
def api_target_override_plans(line_no: int):
    rows = db.query(
        "SELECT pm.PlanMaster_guid, pm.MONo, pm.StyleNo, pm.Customer, "
        "pm.FirstHangDate, pm.SLKH "
        "FROM app.tPlanMaster pm "
        "WHERE pm.[LineNo] = ? AND pm.FirstHangDate IS NOT NULL "
        "ORDER BY pm.FirstHangDate DESC",
        (line_no,),
    )
    for r in rows:
        if r["FirstHangDate"]:
            r["FirstHangDate"] = r["FirstHangDate"].strftime("%Y-%m-%d")
    return rows


@router.get("/api/target-override")
def api_target_override_list(plan_guid: str):
    rows = db.query(
        "SELECT o.Override_guid, o.DayN, o.TargetQty, o.Notes, "
        "o.CreatedBy, CONVERT(varchar(19), o.CreatedAt, 120) AS CreatedAt "
        "FROM app.tTargetOverride o "
        "WHERE o.PlanMaster_guid = ? "
        "ORDER BY o.DayN",
        (plan_guid,),
    )
    return rows


class TargetOverrideIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    plan_guid: str = Field(..., alias="PlanMasterGuid")
    day_n: int = Field(..., alias="DayN", ge=1)
    target_qty: int = Field(..., alias="TargetQty", gt=0)
    notes: Optional[str] = Field(None, alias="Notes")


@router.post("/api/target-override")
def api_target_override_create(
    body: TargetOverrideIn, user: dict = Depends(auth.require_admin),
):
    actor = _actor_id(user)
    existing = db.query(
        "SELECT 1 FROM app.tTargetOverride "
        "WHERE PlanMaster_guid = ? AND DayN = ?",
        (body.plan_guid, body.day_n),
    )
    if existing:
        with db.get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE app.tTargetOverride SET TargetQty = ?, Notes = ?, "
                "CreatedBy = ?, CreatedAt = SYSDATETIME() "
                "WHERE PlanMaster_guid = ? AND DayN = ?",
                (body.target_qty, body.notes, actor, body.plan_guid, body.day_n),
            )
        return {"ok": True, "action": "updated"}
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO app.tTargetOverride "
            "(PlanMaster_guid, DayN, TargetQty, Notes, CreatedBy) "
            "VALUES (?, ?, ?, ?, ?)",
            (body.plan_guid, body.day_n, body.target_qty, body.notes, actor),
        )
    return {"ok": True, "action": "created"}


@router.delete("/api/target-override/{override_guid}")
def api_target_override_delete(
    override_guid: str, user: dict = Depends(auth.require_admin),
):
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM app.tTargetOverride WHERE Override_guid = ?",
            (override_guid,),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Override không tồn tại")
    return {"ok": True}
