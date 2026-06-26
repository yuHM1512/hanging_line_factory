"""TV router — TV-1/2/4 dashboards + setup page.

URL scheme:
    /tv               → setup gallery + rotation config (localStorage)
    /tv/1?mono=...&date=YYYY-MM-DD     → TV-1 page
    /tv/2?mono=...&date=YYYY-MM-DD     → TV-2 page
    /tv/4?mono=...&date=YYYY-MM-DD     → TV-4 page

Data endpoints under /api/tv/*.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates

from . import db
from .admin import compute_end_date, get_holidays, parse_mono

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/tv", tags=["tv"])


# ============================================================
# Hằng số ngày làm việc
# ============================================================
WORK_SECONDS_PER_DAY = 29520           # 8h12m hữu ích (đã trừ break)
WORK_MINUTES_PER_DAY = WORK_SECONDS_PER_DAY / 60   # = 492 phút
TAKT_WEIGHTS = [1.85, 2.0, 2.0, 1.85]  # 4 slot đầu /8.2 — slot 5 = phần dư
SLOT_LABELS = [
    ("7:30 - 9:30", "7:30 → 9:30"),
    ("9:30 - 11:30", "9:30 → 11:30"),
    ("12:30 - 14:30", "12:30 → 14:30"),
    ("14:30 - 16:30", "14:30 → 16:30"),
    ("Sau 16:30", "Sau 16:30"),
]
SLOT_RANGES = [
    ("07:30", "09:30"),
    ("09:30", "11:30"),
    ("12:30", "14:30"),
    ("14:30", "16:30"),
    ("16:30", "23:59"),
]


# ============================================================
# Pages
# ============================================================
@router.get("")
@router.get("/")
def page_setup(request: Request):
    return templates.TemplateResponse(
        "tv/setup.html", {"request": request}
    )


@router.get("/1")
def page_tv1(
    request: Request,
    mono: Optional[str] = None,
    date: Optional[date] = None,
):
    return templates.TemplateResponse(
        "tv/tv1.html",
        {"request": request, "init_mono": mono or "", "init_date": str(date) if date else ""},
    )


@router.get("/2")
def page_tv2(
    request: Request,
    mono: Optional[str] = None,
    date: Optional[date] = None,
):
    return templates.TemplateResponse(
        "tv/tv2.html",
        {"request": request, "init_mono": mono or "", "init_date": str(date) if date else ""},
    )


@router.get("/3")
def page_tv3(
    request: Request,
    mono: Optional[str] = None,
    date: Optional[date] = None,
):
    return templates.TemplateResponse(
        "tv/tv3.html",
        {"request": request, "init_mono": mono or "", "init_date": str(date) if date else ""},
    )


@router.get("/4")
def page_tv4(
    request: Request,
    mono: Optional[str] = None,
    date: Optional[date] = None,
):
    return templates.TemplateResponse(
        "tv/tv4.html",
        {"request": request, "init_mono": mono or "", "init_date": str(date) if date else ""},
    )


# ============================================================
# Common API
# ============================================================
@router.get("/api/plans")
def api_tv_plans():
    """List NhuCauCon (tPlanMaster) đã có cluster đủ 6/6 + có ít nhất 1 ngày scan.

    Trả về Plan + range ngày có data để picker.
    """
    sql = """
        SELECT pm.MONo, pm.SoDonHang, pm.StyleNo, pm.[LineNo] AS LineNoOut,
               pm.NhuCauMe,
               CONVERT(varchar(10), pm.FirstHangDate, 120) AS FirstHangDate,
               (SELECT COUNT(*) FROM app.tClusterStationConfig c
                WHERE c.NhuCauMe = pm.NhuCauMe) AS ClusterCount,
               CONVERT(varchar(10), (SELECT MIN(ShtDate) FROM {MES_DB}.dbo.tRecentWork
                                     WHERE MONo = pm.MONo), 120) AS DataFrom,
               CONVERT(varchar(10), (SELECT MAX(ShtDate) FROM {MES_DB}.dbo.tRecentWork
                                     WHERE MONo = pm.MONo), 120) AS DataTo
        FROM app.tPlanMaster pm
        WHERE pm.NhuCauMe IS NOT NULL
        ORDER BY pm.[LineNo], pm.SoDonHang
    """
    return db.query(sql)


def _resolve_plan_full(mono: str) -> dict:
    """Trả về full info cho 1 plan (con + mẹ + 6 cụm)."""
    plan = db.query(
        "SELECT pm.PlanMaster_guid, pm.MONo, pm.SoDonHang, pm.StyleNo, "
        "pm.[LineNo] AS LineNoOut, pm.FirstHangDate, pm.SLKH, pm.DailyAim, "
        "pm.Customer, pm.NhuCauMe "
        "FROM app.tPlanMaster pm WHERE pm.MONo = ?",
        (mono,),
    )
    if not plan:
        raise HTTPException(404, f"Plan {mono!r} không tồn tại")
    p = plan[0]
    if not p["NhuCauMe"]:
        raise HTTPException(400, "Plan này chưa gắn NhuCauMe")

    mother = db.query(
        "SELECT DMKT, PhanLoaiDH, LDBienChe FROM app.tDemandRoot WHERE NhuCauMe = ?",
        (p["NhuCauMe"],),
    )
    if mother:
        p["DMKT"] = float(mother[0]["DMKT"])
        p["PhanLoaiDH"] = mother[0]["PhanLoaiDH"]
        p["LDBienChe"] = mother[0]["LDBienChe"]
    else:
        p["DMKT"] = p["PhanLoaiDH"] = p["LDBienChe"] = None

    cluster = db.query(
        "SELECT ClusterOrder, RouteStepOdr, GroupLabel, Role "
        "FROM app.tClusterStationConfig WHERE NhuCauMe = ? ORDER BY ClusterOrder",
        (p["NhuCauMe"],),
    )
    p["Cluster"] = cluster

    sam = db.query(
        "SELECT SAM, OWE_Target FROM app.tSAM WHERE StyleNo = ?", (p["StyleNo"],)
    )
    if sam:
        p["SAM"] = float(sam[0]["SAM"])
        p["OWE_Target"] = float(sam[0]["OWE_Target"]) if sam[0]["OWE_Target"] is not None else None
    else:
        p["SAM"] = None
        p["OWE_Target"] = None

    p["POs"] = db.query(
        "SELECT PONo, Qty, CONVERT(varchar(10), ShipDate, 120) AS ShipDate "
        "FROM app.tPlanPO WHERE PlanMaster_guid = ? ORDER BY ShipDate, PONo",
        (p["PlanMaster_guid"],),
    )
    p["PlanMaster_guid"] = str(p["PlanMaster_guid"])
    return p


def _resolve_route_step_to_station_guids(
    mono: str, route_step_odr: int
) -> list[str]:
    """Tìm các Station_guid mà 1 cluster (RouteStepOdr) lấy số.

    Bao gồm tất cả SeqNo trong group (head + IsCombine=1 con).
    """
    rows = db.query(
        """
        ;WITH Steps AS (
          SELECT ds.Odr, ds.SeqNo,
                 MAX(CASE WHEN ds.IsCombine = 0 THEN ds.Odr END)
                   OVER (ORDER BY ds.Odr ROWS UNBOUNDED PRECEDING) AS HeadOdr,
                 rm.guid AS RouteM_guid
          FROM {MES_DB}.dbo.tRouteDS ds
          JOIN {MES_DB}.dbo.tRouteM rm ON ds.RouteM_guid = rm.guid
          JOIN {MES_DB}.dbo.tMOM mm ON rm.MOM_guid = mm.guid
          WHERE mm.MONo = ?
        )
        SELECT DISTINCT CAST(dt.Station_guid AS varchar(50)) AS Station_guid
        FROM Steps s
        JOIN {MES_DB}.dbo.tRouteDT dt ON dt.RouteM_guid = s.RouteM_guid AND dt.SeqNo = s.SeqNo
        WHERE s.HeadOdr = ?
        """,
        (mono, route_step_odr),
    )
    return [r["Station_guid"] for r in rows]


def _scan_count_for_cluster(
    mono: str, route_step_odr: int,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> int:
    """Số scan (cumulative qty) cho cluster trong khoảng date.

    Đếm DISTINCT (CardNo, SeqNo, ShtDate, BeginTime) để tránh double-count.
    Thật ra mỗi (CardNo, SeqNo, BeginTime) là 1 lượt scan riêng → COUNT(*) OK
    nhưng khi 1 cụm có nhiều SeqNo song song trên cùng SP, phải MAX-style.
    """
    seq_nos = db.query(
        """
        ;WITH Steps AS (
          SELECT ds.Odr, ds.SeqNo,
                 MAX(CASE WHEN ds.IsCombine = 0 THEN ds.Odr END)
                   OVER (ORDER BY ds.Odr ROWS UNBOUNDED PRECEDING) AS HeadOdr
          FROM {MES_DB}.dbo.tRouteDS ds
          JOIN {MES_DB}.dbo.tRouteM rm ON ds.RouteM_guid = rm.guid
          JOIN {MES_DB}.dbo.tMOM mm ON rm.MOM_guid = mm.guid
          WHERE mm.MONo = ?
        )
        SELECT DISTINCT SeqNo FROM Steps WHERE HeadOdr = ?
        """,
        (mono, route_step_odr),
    )
    if not seq_nos:
        return 0
    seq_list = [r["SeqNo"] for r in seq_nos]
    placeholders = ",".join(["?"] * len(seq_list))

    where_date = ""
    params: list[Any] = [mono] + seq_list
    if from_date and to_date:
        where_date = "AND rw.ShtDate BETWEEN ? AND ?"
        params.extend([from_date, to_date])
    elif to_date:
        where_date = "AND rw.ShtDate <= ?"
        params.append(to_date)

    # Đếm lượt qua cụm = MAX (count theo SeqNo) trong group
    # = COUNT(*) / COUNT(DISTINCT SeqNo) nếu 1 SP scan đủ SeqNo
    # An toàn: dùng MAX per SeqNo rồi MIN (vì SP qua hết các seq)
    sql = f"""
        SELECT SeqNo, COUNT(*) AS Qty
        FROM {{MES_DB}}.dbo.tRecentWork rw
        WHERE rw.MONo = ? AND rw.SeqNo IN ({placeholders}) {where_date}
        GROUP BY SeqNo
    """
    rows = db.query(sql, params)
    if not rows:
        return 0
    qtys = [r["Qty"] for r in rows]
    # 1 SP đi qua cả group → mỗi SeqNo trong group được scan 1 lần
    # Lấy MIN để bảo thủ (= số SP đã pass qua tất cả SeqNo của cụm)
    # Nếu group chỉ 1 SeqNo thì = COUNT(*)
    return min(qtys)


def _hourly_actual(mono: str, the_date: date) -> dict[int, int]:
    """KCS scan theo slot 1-5 cho ngày the_date.

    Filter giống công thức vàng: StRole=13 AND IsLastSeq=1.
    """
    rows = db.query(
        """
        SELECT rw.BeginTime, rw.Qty
        FROM {MES_DB}.dbo.tRecentWork rw
        INNER JOIN {MES_DB}.dbo.tStation st ON rw.Station_guid = st.guid
        WHERE st.StRole = 13 AND rw.IsLastSeq = 1
          AND rw.MONo = ? AND rw.ShtDate = ?
        """,
        (mono, the_date),
    )
    # Slot ranges:
    #   1: 07:30 → 09:30
    #   2: 09:30 → 11:30
    #   3: 11:30 → 14:30   ← bao gồm 11:30-12:30 (lunch scans dồn vào slot này)
    #   4: 14:30 → 16:30
    #   5: 16:30 → ...
    counts = {i: 0 for i in range(1, 6)}
    for r in rows:
        bt = r["BeginTime"]
        if not bt:
            continue
        t = bt.time() if hasattr(bt, "time") else bt
        hm = t.strftime("%H:%M")
        slot = None
        if "07:30" <= hm < "09:30":
            slot = 1
        elif "09:30" <= hm < "11:30":
            slot = 2
        elif "11:30" <= hm < "14:30":
            slot = 3
        elif "14:30" <= hm < "16:30":
            slot = 4
        elif hm >= "16:30":
            slot = 5
        if slot:
            counts[slot] += int(r["Qty"] or 0)
    return counts


def _slot_from_time(t) -> Optional[int]:
    """Map 1 thời điểm (time/datetime) → slot 1..5. None nếu ngoài giờ."""
    if t is None:
        return None
    if hasattr(t, "time"):
        t = t.time()
    hm = t.strftime("%H:%M")
    if "07:30" <= hm < "09:30":
        return 1
    if "09:30" <= hm < "11:30":
        return 2
    if "11:30" <= hm < "14:30":
        return 3
    if "14:30" <= hm < "16:30":
        return 4
    if hm >= "16:30":
        return 5
    return None


def _kcs_defective_hourly(mono: str, the_date: date) -> dict[int, int]:
    """Số SP lỗi KCS bucket theo slot 1-5 (từ chuyền treo, không phải nhập tay).

    Filter golden: StRole=13 AND IsLastSeq=1; aggregate SUM(DefectiveQty)
    theo khung giờ BeginTime.
    """
    rows = db.query(
        """
        SELECT rw.BeginTime, rw.DefectiveQty
        FROM {MES_DB}.dbo.tRecentWork rw
        INNER JOIN {MES_DB}.dbo.tStation st ON rw.Station_guid = st.guid
        WHERE st.StRole = 13 AND rw.IsLastSeq = 1
          AND rw.MONo = ? AND rw.ShtDate = ?
          AND rw.DefectiveQty > 0
        """,
        (mono, the_date),
    )
    counts = {i: 0 for i in range(1, 6)}
    for r in rows:
        bt = r["BeginTime"]
        if not bt:
            continue
        t = bt.time() if hasattr(bt, "time") else bt
        hm = t.strftime("%H:%M")
        slot = None
        if "07:30" <= hm < "09:30":
            slot = 1
        elif "09:30" <= hm < "11:30":
            slot = 2
        elif "11:30" <= hm < "14:30":
            slot = 3
        elif "14:30" <= hm < "16:30":
            slot = 4
        elif hm >= "16:30":
            slot = 5
        if slot:
            counts[slot] += int(r["DefectiveQty"] or 0)
    return counts


def _hourly_target(daily_aim: int) -> list[int]:
    """Phân bổ DailyAim ra 5 slot theo công thức user §9.

    1.85 / 2 / 2 / 1.85 / dư  ÷ 8.2 × DailyAim
    """
    if not daily_aim:
        return [0, 0, 0, 0, 0]
    base_4 = [round(daily_aim * w / 8.2) for w in TAKT_WEIGHTS]
    slot_5 = daily_aim - sum(base_4)
    return base_4 + [max(slot_5, 0)]


def _output_kcs(mono: str, from_date: Optional[date], to_date: date) -> dict:
    """SUM(Qty), SUM(DefectiveQty) qua KCS (StRole=13 AND IsLastSeq=1)."""
    where = "rw.MONo = ? AND st.StRole = 13 AND rw.IsLastSeq = 1"
    params: list[Any] = [mono]
    if from_date:
        where += " AND rw.ShtDate BETWEEN ? AND ?"
        params.extend([from_date, to_date])
    else:
        where += " AND rw.ShtDate <= ?"
        params.append(to_date)
    rows = db.query(
        f"""
        SELECT ISNULL(SUM(rw.Qty), 0) AS Qty,
               ISNULL(SUM(rw.DefectiveQty), 0) AS DefQty
        FROM {{MES_DB}}.dbo.tRecentWork rw
        INNER JOIN {{MES_DB}}.dbo.tStation st ON rw.Station_guid = st.guid
        WHERE {where}
        """,
        params,
    )
    return {"Qty": int(rows[0]["Qty"]), "Def": int(rows[0]["DefQty"])}


def _workers_count(
    mono: str, the_date: date, ld_bien_che: Optional[int] = None
) -> int:
    """Fallback chain:
       1. tDailyHeadcount override per (date, line) — khi có endpoint nhập
       2. LDBienChe từ NhuCauMe (mặc định cho mọi ngày của plan)
       3. Last resort: COUNT(DISTINCT EmpID) từ tRecentWork
    """
    line_no = parse_mono(mono)["LineNo"]
    if line_no:
        override = db.query(
            "SELECT Headcount FROM app.tDailyHeadcount WHERE ShtDate = ? AND [LineNo] = ?",
            (the_date, line_no),
        )
        if override:
            return int(override[0]["Headcount"])
    if ld_bien_che:
        return int(ld_bien_che)
    rows = db.query(
        "SELECT COUNT(DISTINCT EmpID) AS N FROM {MES_DB}.dbo.tRecentWork "
        "WHERE MONo = ? AND ShtDate = ?",
        (mono, the_date),
    )
    return int(rows[0]["N"]) if rows else 0


def _workday_index(first_hang: date, the_date: date, holidays: set) -> int:
    """Day N = số ngày làm việc (1-based, skip CN + lễ) từ first_hang đến the_date."""
    if the_date < first_hang:
        return 0
    d = first_hang
    n = 0
    while d <= the_date:
        if d.weekday() != 6 and d not in holidays:
            n += 1
        d += timedelta(days=1)
    return n


def _ndsx_level(phan_loai: str, ndsx_sec: float) -> int:
    """Map NDSX seconds → cấp độ.

    Vest → 0 (sentinel, không phân cấp)
    Còn lại: CĐ1 (>120), CĐ2 (45..120), CĐ3 (<45)
    """
    if phan_loai == "Vest":
        return 0
    if ndsx_sec > 120:
        return 1
    if ndsx_sec >= 45:
        return 2
    return 3


def _curve_ratio(phan_loai: str, ndsx_level: int, day_n: int) -> float:
    """Lookup ratio cho ngày N. Nếu vượt curve → dùng ratio cuối cùng."""
    if day_n < 1:
        return 0.0
    rows = db.query(
        "SELECT TOP 1 Ratio FROM app.tProductionCurve "
        "WHERE Category = ? AND NDSXLevel = ? AND DayN <= ? "
        "ORDER BY DayN DESC",
        (phan_loai, ndsx_level, day_n),
    )
    return float(rows[0]["Ratio"]) if rows else 1.0


def compute_day_target(
    first_hang_me: date,
    the_date: date,
    dmkt: float,
    phan_loai: str,
    workers: int,
    holidays: set,
) -> dict:
    """Tính mục tiêu năng suất ngày cho 1 plan/mẹ tại ngày `the_date`.

    Năng suất giao = ĐMKT × LĐ × ratio[day_n]
    """
    if not dmkt or not workers or not first_hang_me:
        return {"target": 0, "day_n": 0, "ndsx_sec": 0,
                "ndsx_level": 0, "ratio": 0.0}
    ndsx_sec = WORK_SECONDS_PER_DAY / (workers * dmkt)
    ndsx_level = _ndsx_level(phan_loai, ndsx_sec)
    day_n = _workday_index(first_hang_me, the_date, holidays)
    ratio = _curve_ratio(phan_loai, ndsx_level, day_n)
    target = round(dmkt * workers * ratio)
    return {
        "target": target,
        "day_n": day_n,
        "ndsx_sec": round(ndsx_sec, 1),
        "ndsx_level": ndsx_level,
        "ratio": ratio,
    }


def _me_first_hang(nhu_cau_me_id: str) -> Optional[date]:
    rows = db.query(
        "SELECT MIN(FirstHangDate) AS D FROM app.tPlanMaster WHERE NhuCauMe = ?",
        (nhu_cau_me_id,),
    )
    return rows[0]["D"] if rows and rows[0]["D"] else None


def _forecast_end_date(
    first_hang: date, slkh: int, last_day_output: int, cumulative_done: int,
    today: date, holidays: set,
) -> Optional[date]:
    """Ngày kết thúc thực tế = hôm nay + (remain / last_day_output), skip CN+lễ.

    Nếu plan đã xong → trả None.
    """
    remain = slkh - cumulative_done
    if remain <= 0:
        return today
    if last_day_output <= 0:
        return None  # chưa biết
    days_needed = math.ceil(remain / last_day_output)
    d = today + timedelta(days=1)
    remaining = days_needed
    while remaining > 0:
        if d.weekday() != 6 and d not in holidays:
            remaining -= 1
            if remaining == 0:
                return d
        d += timedelta(days=1)
    return d


# ============================================================
# TV-1 endpoint
# ============================================================
@router.get("/api/tv1")
def api_tv1(
    mono: str = Query(..., description="MONo full string"),
    the_date: date = Query(..., alias="date"),
):
    plan = _resolve_plan_full(mono)
    holidays = get_holidays()
    first_hang = plan["FirstHangDate"]
    first_hang_me = _me_first_hang(plan["NhuCauMe"]) or first_hang
    slkh = int(plan["SLKH"] or 0)
    dmkt = plan["DMKT"] or 0
    ld = plan["LDBienChe"] or 0
    sam = plan["SAM"] or 0
    owe_target_pct = (plan["OWE_Target"] * 100) if plan["OWE_Target"] else 85.0

    # Workers fallback chain (như cũ): tDailyHeadcount → LDBienChe → scan distinct
    workers = _workers_count(mono, the_date, ld_bien_che=ld)

    # MỤC TIÊU NGÀY = compute từ curve (ĐMKT × LĐ × ratio_day_n)
    tgt = compute_day_target(first_hang_me, the_date, dmkt,
                             plan["PhanLoaiDH"], workers, holidays)
    daily_aim = tgt["target"]

    # Cumulative + today output
    cum = _output_kcs(mono, first_hang, the_date)
    today = _output_kcs(mono, the_date, the_date)
    yesterday_out = 0
    if the_date > first_hang:
        y = _output_kcs(mono, the_date - timedelta(days=1), the_date - timedelta(days=1))
        yesterday_out = y["Qty"]
    last_day_output = today["Qty"] if today["Qty"] > 0 else yesterday_out

    # WIP = qty(first cluster cumulative) − qty(KCS cumulative golden formula)
    # Last cluster bắt buộc dùng StRole=13 + IsLastSeq=1 (vì SP có thể chốt nhiều SeqNo)
    wip = 0
    first_cluster = next((c for c in plan["Cluster"] if c["Role"] == "first"), None)
    if first_cluster:
        in_qty = _scan_count_for_cluster(mono, first_cluster["RouteStepOdr"], first_hang, the_date)
        wip = max(in_qty - cum["Qty"], 0)   # cum["Qty"] = golden KCS

    # Takt
    takt_kh = round(WORK_SECONDS_PER_DAY / daily_aim) if daily_aim else 0
    takt_real = round(WORK_SECONDS_PER_DAY / today["Qty"]) if today["Qty"] else 0

    # TPT (phút) = (WIP+1) × takt_real / 60
    tpt_min = round((wip + 1) * takt_real / 60) if takt_real else 0

    # OWE: SAM × Output_today / (working_min × LĐ)
    owe_pct = 0.0
    if sam and today["Qty"] and ld:
        rpt = WORK_MINUTES_PER_DAY * ld / today["Qty"]   # phút/SP
        owe_pct = round(sam / rpt * 100, 1) if rpt else 0

    # End dates
    end_target = compute_end_date(first_hang, slkh, daily_aim, holidays)
    end_actual = _forecast_end_date(first_hang, slkh, last_day_output,
                                    cum["Qty"], the_date, holidays)

    # Hourly target + actual
    target_slots = _hourly_target(daily_aim)
    actual_slots = _hourly_actual(mono, the_date)

    # placeholder anchor: HĐKP for date
    hdkp = db.query(
        "SELECT Slot, RootCause, CAPAction FROM app.tHourlyAction "
        "WHERE PlanMaster_guid = ? AND ShtDate = ? ORDER BY Slot",
        (plan["PlanMaster_guid"], the_date),
    )

    # Defect rate
    defect_rate = round(cum["Def"] / cum["Qty"] * 100, 1) if cum["Qty"] else 0

    # Mã đơn KH = SoDonHang without '#'
    ma_don_kh = plan["SoDonHang"].lstrip("#")

    return {
        "header": {
            "Tổ": plan["LineNoOut"],
            "MaDonKH": ma_don_kh,
            "MONo": mono,
            "StyleNo": plan["StyleNo"],
            "Customer": plan["Customer"],
            "FirstHangDate": first_hang.isoformat(),
            "Workers": workers,
            "WIP": wip,
            "TPT": tpt_min,
            "PhanLoaiDH": plan["PhanLoaiDH"],
            "DailyAim": daily_aim,
        },
        "hero": {
            "SLKH": slkh,
            "TH": cum["Qty"],
            "Remain": max(slkh - cum["Qty"], 0),
            "Pct": round(cum["Qty"] / slkh * 100, 1) if slkh else 0,
        },
        "stats": {
            "DayQty": {"KH": daily_aim, "TH": today["Qty"],
                       "Pct": round(today["Qty"] / daily_aim * 100, 1) if daily_aim else 0},
            "Takt": {"KH": takt_kh, "TT": takt_real,
                     "Pct": round(takt_kh / takt_real * 100, 1) if takt_real else 0},
            "OWE": {"Pct": owe_pct, "Target": round(owe_target_pct, 1)},
            "DefectRate": {"Pct": defect_rate, "Threshold": 5},
            "EndDay": {
                "Target": end_target.strftime("%d-%m") if end_target else None,
                "Actual": end_actual.strftime("%d-%m") if end_actual else None,
                "DiffDays": (end_actual - end_target).days if end_target and end_actual else None,
            },
        },
        "hours": [
            {"label": SLOT_LABELS[i][0], "kh": target_slots[i], "th": actual_slots[i + 1]}
            for i in range(5)
        ],
        "hdkp": [dict(r) for r in hdkp],
        "pos": plan["POs"],
        "total_po_qty": sum(int(r["Qty"]) for r in plan["POs"]),
    }


# ============================================================
# TV-2 endpoint — 6 cluster cards + bar chart
# ============================================================
@router.get("/api/tv2")
def api_tv2(
    mono: str = Query(..., description="MONo full string"),
    the_date: date = Query(..., alias="date"),
):
    plan = _resolve_plan_full(mono)
    holidays = get_holidays()
    first_hang = plan["FirstHangDate"]
    first_hang_me = _me_first_hang(plan["NhuCauMe"]) or first_hang
    dmkt = plan["DMKT"] or 0
    ld = plan["LDBienChe"] or 0
    workers = _workers_count(mono, the_date, ld_bien_che=ld)

    # Target line = computed từ curve (end-of-day → ratio đã đầy đủ)
    tgt = compute_day_target(first_hang_me, the_date, dmkt,
                             plan["PhanLoaiDH"], workers, holidays)
    target_today = tgt["target"]

    # Tính qty/ngày + lũy kế cho từng cụm 1..6
    clusters_data = []
    for c in sorted(plan["Cluster"], key=lambda x: x["ClusterOrder"]):
        odr = c["RouteStepOdr"]
        role = c["Role"]
        if role == "last":
            # Cụm KCS: dùng golden formula
            today_qty = _output_kcs(mono, the_date, the_date)["Qty"]
            cum_qty = _output_kcs(mono, first_hang, the_date)["Qty"]
        else:
            today_qty = _scan_count_for_cluster(mono, odr, the_date, the_date)
            cum_qty = _scan_count_for_cluster(mono, odr, first_hang, the_date)
        clusters_data.append({
            "Order": c["ClusterOrder"],
            "Role": role,
            "Label": c["GroupLabel"] or f"Cụm {c['ClusterOrder']}",
            "RouteStepOdr": odr,
            "QtyToday": today_qty,
            "Cumulative": cum_qty,
            "Pass": today_qty >= target_today,
        })

    # Y-axis max cho chart = max(values + target) × 1.15, làm tròn lên 50
    all_qtys = [c["QtyToday"] for c in clusters_data] + [target_today]
    max_val = max(all_qtys) if all_qtys else 100
    y_max = ((int(max_val * 1.15) // 50) + 1) * 50

    # Mã đơn KH
    ma_don_kh = plan["SoDonHang"].lstrip("#")

    return {
        "header": {
            "Tổ": plan["LineNoOut"],
            "MaDonKH": ma_don_kh,
            "MONo": mono,
            "StyleNo": plan["StyleNo"],
            "Customer": plan["Customer"],
            "FirstHangDate": first_hang.isoformat(),
            "Workers": workers,
            "Target": target_today,
        },
        "clusters": clusters_data,
        "target": target_today,
        "y_max": y_max,
    }



# ============================================================
# TV-3 endpoint — Chất lượng cuối chuyền & Máy hỏng
# ============================================================
@router.get("/api/tv3")
def api_tv3(
    mono: str = Query(..., description="MONo full string"),
    the_date: date = Query(..., alias="date"),
):
    plan = _resolve_plan_full(mono)
    holidays = get_holidays()
    first_hang = plan["FirstHangDate"]
    ld = plan["LDBienChe"] or 0
    workers = _workers_count(mono, the_date, ld_bien_che=ld)

    # WIP — reuse từ TV-1 (cụm 'first' → KCS)
    cum_kcs = _output_kcs(mono, first_hang, the_date)
    today_kcs = _output_kcs(mono, the_date, the_date)
    wip = 0
    first_cluster = next((c for c in plan["Cluster"] if c["Role"] == "first"), None)
    if first_cluster:
        in_qty = _scan_count_for_cluster(mono, first_cluster["RouteStepOdr"], first_hang, the_date)
        wip = max(in_qty - cum_kcs["Qty"], 0)

    # ===== Defect log aggregates =====
    plan_guid = plan["PlanMaster_guid"]

    # Slot HIỆN TẠI = slot của scan KCS GẦN NHẤT trong ngày (chuyền treo).
    # KHÔNG dùng tDefectLog.Slot vì đó là input thủ công của tổ trưởng.
    recent_scan_row = db.query(
        """
        SELECT MAX(rw.BeginTime) AS BT
        FROM {MES_DB}.dbo.tRecentWork rw
        INNER JOIN {MES_DB}.dbo.tStation st ON rw.Station_guid = st.guid
        WHERE st.StRole = 13 AND rw.IsLastSeq = 1
          AND rw.MONo = ? AND rw.ShtDate = ?
        """,
        (mono, the_date),
    )
    last_scan_bt = recent_scan_row[0]["BT"] if recent_scan_row else None
    current_slot = _slot_from_time(last_scan_bt)
    SLOT_LABELS_VI = {
        1: "Mốc 1 · 7:30 → 9:30",
        2: "Mốc 2 · 9:30 → 11:30",
        3: "Mốc 3 · 12:30 → 14:30",
        4: "Mốc 4 · 14:30 → 16:30",
        5: "Mốc 5 · Sau 16:30",
    }
    current_slot_label = SLOT_LABELS_VI.get(current_slot) if current_slot else None

    # ── Số lượng lỗi LẤY TỪ CHUYỀN TREO (KCS golden DefectiveQty) ──
    # Mốc hiện tại = bucket theo BeginTime tương ứng slot tổ trưởng đang nhập
    # Lũy kế ngày = SUM(DefectiveQty) cả ngày (= today_kcs["Def"])
    hourly_def = _kcs_defective_hourly(mono, the_date) if current_slot else {}
    defect_slot = hourly_def.get(current_slot, 0) if current_slot else 0
    defect_day = int(today_kcs["Def"])

    # Reinspect
    ri = db.query(
        "SELECT FixedQty FROM app.tReinspectDaily "
        "WHERE PlanMaster_guid = ? AND ShtDate = ?",
        (plan_guid, the_date),
    )
    fixed_day = int(ri[0]["FixedQty"]) if ri else 0

    # Tỷ lệ kiểm lại = đã sửa / lỗi KCS-detected
    kcs_defect = today_kcs["Def"]
    if kcs_defect > 0:
        reinspect_pct = round(fixed_day / kcs_defect * 100, 1)
    else:
        reinspect_pct = 100.0

    # ===== Defect detail table (mốc gần nhất) — gộp theo DefectCode =====
    defect_groups: list[dict] = []
    if True:
        raw = db.query(
            """
            SELECT dl.DefectCode, dc.DefectName, dl.StationLabel,
                   SUM(dl.Qty) AS Qty
            FROM app.tDefectLog dl
            JOIN app.tDefectCatalog dc ON dl.DefectCode = dc.DefectCode
            WHERE dl.PlanMaster_guid = ? AND dl.ShtDate = ?
            GROUP BY dl.DefectCode, dc.DefectName, dl.StationLabel
            ORDER BY SUM(dl.Qty) DESC, dl.DefectCode, dl.StationLabel
            """,
            (plan_guid, the_date),
        )
        by_code: dict[str, dict] = {}
        for r in raw:
            code = r["DefectCode"]
            entry = by_code.setdefault(code, {
                "DefectCode": code,
                "DefectName": r["DefectName"],
                "Stations": [],
                "TotalQty": 0,
            })
            entry["Stations"].append({
                "Label": r["StationLabel"], "Qty": int(r["Qty"]),
            })
            entry["TotalQty"] += int(r["Qty"])
        # Sort theo tổng SL giảm dần, lấy 6 dạng đầu
        defect_groups = sorted(by_code.values(),
                               key=lambda x: -x["TotalQty"])[:6]

    # Top defect (group by code, top 3)
    top_defects = db.query(
        """
        SELECT TOP 3 dl.DefectCode, dc.DefectName, SUM(dl.Qty) AS Qty
        FROM app.tDefectLog dl
        JOIN app.tDefectCatalog dc ON dl.DefectCode = dc.DefectCode
        WHERE dl.PlanMaster_guid = ? AND dl.ShtDate = ?
        GROUP BY dl.DefectCode, dc.DefectName
        ORDER BY SUM(dl.Qty) DESC
        """,
        (plan_guid, the_date),
    )
    top_max = max([t["Qty"] for t in top_defects], default=0)

    # ===== Machine breakdown =====
    brks = db.query(
        """
        SELECT CAST(b.Breakdown_guid AS varchar(50)) AS Breakdown_guid,
               mc.MachineName, b.DownMinutes, b.Reason, b.Slot
        FROM app.tMachineBreakdown b
        JOIN app.tMachineCatalog mc ON b.MachineID = mc.MachineID
        WHERE b.PlanMaster_guid = ? AND b.ShtDate = ?
        ORDER BY b.Slot, b.LoggedAt
        """,
        (plan_guid, the_date),
    )
    downtime_min = sum(int(b["DownMinutes"]) for b in brks)

    # Footer figures
    kcs_today_qty = today_kcs["Qty"]
    pass_today = max(kcs_today_qty - kcs_defect, 0)
    defect_rate = round(kcs_defect / kcs_today_qty * 100, 1) if kcs_today_qty else 0.0

    ma_don_kh = plan["SoDonHang"].lstrip("#")

    return {
        "header": {
            "Tổ": plan["LineNoOut"],
            "MaDonKH": ma_don_kh,
            "MONo": mono,
            "StyleNo": plan["StyleNo"],
            "Customer": plan["Customer"],
            "NhuCauMe": plan["NhuCauMe"],
            "FirstHangDate": first_hang.isoformat(),
            "Workers": workers,
            "WIP": wip,
        },
        "kpi": {
            "ReinspectPct": reinspect_pct,
            "DefectSlot": defect_slot,
            "CurrentSlot": current_slot,
            "CurrentSlotLabel": current_slot_label,
            "FixedDay": fixed_day,
            "DefectDay": defect_day,
            "DefectThreshold": 5,
        },
        "defects": defect_groups,
        "top_defects": [
            {"DefectCode": r["DefectCode"], "DefectName": r["DefectName"],
             "Qty": int(r["Qty"]),
             "BarPct": round(int(r["Qty"]) / top_max * 100) if top_max else 0}
            for r in top_defects
        ],
        "breakdowns": [
            {"Breakdown_guid": b["Breakdown_guid"], "MachineName": b["MachineName"],
             "DownMinutes": int(b["DownMinutes"]), "Reason": b["Reason"],
             "Slot": b["Slot"]}
            for b in brks
        ],
        "breakdown_count": len(brks),
        "downtime_min": downtime_min,
        "kcs": {
            "Qty": kcs_today_qty,
            "Pass": pass_today,
            "Defect": kcs_defect,
            "DefectRate": defect_rate,
        },
    }


# ============================================================
# TV-4 endpoint — Lộ trình ra chuyền theo Nhu cầu mẹ
# ============================================================
def _kcs_qty_for_me(nhu_cau_me_id: str, from_date: date, to_date: date) -> int:
    """Tổng KCS qty của TẤT CẢ con thuộc 1 NhuCauMe trong khoảng date."""
    monos = db.query(
        "SELECT MONo FROM app.tPlanMaster WHERE NhuCauMe = ?",
        (nhu_cau_me_id,),
    )
    if not monos:
        return 0
    mono_list = [r["MONo"] for r in monos]
    placeholders = ",".join(["?"] * len(mono_list))
    rows = db.query(
        f"""
        SELECT ISNULL(SUM(rw.Qty), 0) AS Q
        FROM {{MES_DB}}.dbo.tRecentWork rw
        INNER JOIN {{MES_DB}}.dbo.tStation st ON rw.Station_guid = st.guid
        WHERE st.StRole = 13 AND rw.IsLastSeq = 1
          AND rw.MONo IN ({placeholders})
          AND rw.ShtDate BETWEEN ? AND ?
        """,
        mono_list + [from_date, to_date],
    )
    return int(rows[0]["Q"]) if rows else 0


def _workers_for_me_day(
    nhu_cau_me_id: str, the_date: date, ld_default: int
) -> int:
    """LĐ ngày: dùng fallback chain giống TV-1 nhưng gom cho cả mẹ.

    1. tDailyHeadcount(date, line) override — nếu có
    2. LDBienChe (default từ NhuCauMe)
    3. COUNT DISTINCT EmpID từ tRecentWork (mọi MONo của mẹ)
    """
    # Override: lấy LineNo của 1 con bất kỳ làm key
    line_no_rows = db.query(
        "SELECT TOP 1 [LineNo] AS L FROM app.tPlanMaster WHERE NhuCauMe = ?",
        (nhu_cau_me_id,),
    )
    if line_no_rows:
        override = db.query(
            "SELECT Headcount FROM app.tDailyHeadcount WHERE ShtDate = ? AND [LineNo] = ?",
            (the_date, line_no_rows[0]["L"]),
        )
        if override:
            return int(override[0]["Headcount"])
    if ld_default:
        return int(ld_default)
    monos = db.query(
        "SELECT MONo FROM app.tPlanMaster WHERE NhuCauMe = ?",
        (nhu_cau_me_id,),
    )
    if not monos:
        return 0
    mono_list = [r["MONo"] for r in monos]
    placeholders = ",".join(["?"] * len(mono_list))
    rows = db.query(
        f"SELECT COUNT(DISTINCT EmpID) AS N FROM {{MES_DB}}.dbo.tRecentWork "
        f"WHERE MONo IN ({placeholders}) AND ShtDate = ?",
        mono_list + [the_date],
    )
    return int(rows[0]["N"]) if rows else 0


@router.get("/api/tv4")
def api_tv4(
    mono: str = Query(..., description="MONo full string"),
    the_date: date = Query(..., alias="date"),
):
    plan = _resolve_plan_full(mono)
    nhu_cau_me_id = plan["NhuCauMe"]
    holidays = get_holidays()

    # Mẹ aggregate
    me_rows = db.query(
        "SELECT SUM(SLKH) AS Total, MIN(FirstHangDate) AS FirstDate "
        "FROM app.tPlanMaster WHERE NhuCauMe = ?",
        (nhu_cau_me_id,),
    )
    total_slkh = int(me_rows[0]["Total"] or 0)
    first_hang_me = me_rows[0]["FirstDate"]

    dmkt = plan["DMKT"] or 0
    ld_default = plan["LDBienChe"] or 0
    phan_loai = plan["PhanLoaiDH"]

    # NĐSX cố định cho mẹ (tính theo LĐ biên chế)
    ndsx_sec = round(WORK_SECONDS_PER_DAY / (ld_default * dmkt), 1) if (ld_default and dmkt) else 0
    ndsx_level = _ndsx_level(phan_loai, ndsx_sec)

    # Last actual scan date (KCS) across all children
    monos = db.query(
        "SELECT MONo FROM app.tPlanMaster WHERE NhuCauMe = ?",
        (nhu_cau_me_id,),
    )
    mono_list = [r["MONo"] for r in monos]
    last_actual_date = first_hang_me
    if mono_list:
        ph = ",".join(["?"] * len(mono_list))
        r = db.query(
            f"""SELECT MAX(rw.ShtDate) AS D
                FROM {{MES_DB}}.dbo.tRecentWork rw
                INNER JOIN {{MES_DB}}.dbo.tStation st ON rw.Station_guid = st.guid
                WHERE st.StRole = 13 AND rw.IsLastSeq = 1
                  AND rw.MONo IN ({ph})""",
            mono_list,
        )
        if r and r[0]["D"]:
            last_actual_date = r[0]["D"]

    # Show until: max(SoCaKH, last_actual_date, the_date) + tiny buffer
    stop_date = max(last_actual_date, the_date)

    days = []
    cum_target = 0
    cum_actual = 0
    day_n = 1
    cur_date = first_hang_me
    day_100_pct = None
    day_ratio_1 = None

    while day_n <= 80:  # safety cap
        # Skip CN + lễ
        while cur_date.weekday() == 6 or cur_date in holidays:
            cur_date += timedelta(days=1)

        is_past = cur_date <= the_date
        workers = _workers_for_me_day(nhu_cau_me_id, cur_date, ld_default) if is_past else ld_default
        ratio = _curve_ratio(phan_loai, ndsx_level, day_n)
        target = round(dmkt * workers * ratio) if workers else 0
        actual = _kcs_qty_for_me(nhu_cau_me_id, cur_date, cur_date) if is_past else None

        cum_target += target
        if actual is not None:
            cum_actual += actual

        pct = round(actual / target * 100, 1) if (actual is not None and target) else None

        if day_ratio_1 is None and ratio >= 1.0:
            day_ratio_1 = day_n
        if day_100_pct is None and cum_target >= total_slkh:
            day_100_pct = day_n

        days.append({
            "DayN": day_n,
            "Date": cur_date.isoformat(),
            "Workers": workers,
            "TargetNS": target,
            "Actual": actual,
            "CumTarget": cum_target,
            "CumActual": cum_actual,
            "Ratio": round(ratio, 4),
            "Pct": pct,
            "IsPast": is_past,
            "IsCurrent": cur_date == the_date,
        })

        # Stop condition: đã qua SoCaKH VÀ qua ngày actual cuối VÀ qua ngày đang xem
        if (day_100_pct is not None and cur_date >= stop_date):
            break

        day_n += 1
        cur_date += timedelta(days=1)

    return {
        "header": {
            "Tổ": plan["LineNoOut"],
            "MaDonKH": plan["SoDonHang"].lstrip("#"),
            "StyleNo": plan["StyleNo"],
            "Customer": plan["Customer"],
            "SLKH": total_slkh,
            "DMKT": dmkt,
            "PhanLoaiDH": phan_loai,
            "NDSXSec": ndsx_sec,
            "NDSXLevel": ndsx_level,
            "LDBienChe": ld_default,
            "FirstHangDate": first_hang_me.isoformat(),
            "SoCaKH": day_100_pct or len(days),
            "DayRatio1": day_ratio_1,
        },
        "days": days,
        "current_day_n": next(
            (d["DayN"] for d in days if d["IsCurrent"]), None
        ),
    }
