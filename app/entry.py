"""Entry router for line-lead data entry.

URL scheme:
    /entry       -> single-page UI for logged-in users
    /entry/api/* -> JSON endpoints
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from . import auth, db

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/entry", tags=["entry"])


class EntryModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


def _resolve_plan(mono: str) -> dict:
    rows = db.query(
        "SELECT PlanMaster_guid, [LineNo] FROM app.tPlanMaster WHERE MONo = ?",
        (mono,),
    )
    if not rows:
        raise HTTPException(404, f"Kế hoạch {mono!r} không tồn tại")
    return rows[0]


def _defect_total_kcs(plan_guid: str, sht_date: date) -> int:
    """Return total KCS defects for one plan/date."""
    rows = db.query(
        """
        SELECT ISNULL(SUM(rw.DefectiveQty), 0) AS Q
        FROM {MES_DB}.dbo.tRecentWork rw
        INNER JOIN {MES_DB}.dbo.tStation st ON rw.Station_guid = st.guid
        INNER JOIN app.tPlanMaster pm ON pm.PlanMaster_guid = ?
        WHERE st.StRole = 13 AND rw.IsLastSeq = 1
          AND rw.MONo = pm.MONo AND rw.ShtDate = ?
        """,
        (plan_guid, sht_date),
    )
    return int(rows[0]["Q"]) if rows else 0


# ============================================================
# Page
# ============================================================
@router.get("")
@router.get("/")
def page_entry(request: Request, user: dict = Depends(auth.require_user)):
    return templates.TemplateResponse(
        "entry/index.html",
        {"request": request, "user": user, "is_admin": (user.get("Role") or "").lower() == "admin"},
    )


@router.get("/actions")
def page_actions(request: Request, user: dict = Depends(auth.require_user)):
    return templates.TemplateResponse(
        "entry/actions.html", {"request": request, "user": user, "today": date.today().isoformat()}
    )


def _entry_plan_for_user(mono: str, user: dict) -> dict:
    plan = _resolve_plan(mono)
    if (user.get("Role") or "").lower() == "admin":
        return plan
    if user.get("Unit", "").upper() != "XN2" or user.get("Dept") is None or user["Dept"] != plan["LineNo"]:
        raise HTTPException(403, "Kế hoạch không thuộc tổ của bạn")
    return plan


@router.get("/api/hourly-actions/plans")
def api_hourly_action_plans(user: dict = Depends(auth.require_user)):
    is_admin = (user.get("Role") or "").lower() == "admin"
    params: tuple[Any, ...] = ()
    where = ""
    if not is_admin:
        if user.get("Unit", "").upper() != "XN2" or user.get("Dept") is None:
            raise HTTPException(403, "Tài khoản chưa được gắn tổ XN2")
        where = " AND pm.[LineNo] = ?"
        params = (user["Dept"],)
    return db.query(
        "SELECT pm.MONo, pm.NhuCauMe, pm.StyleNo, pm.[LineNo] AS LineNoOut "
        "FROM app.tPlanMaster pm WHERE pm.NhuCauMe IS NOT NULL" + where +
        " ORDER BY pm.FirstHangDate DESC, pm.MONo", params
    )


@router.get("/api/hourly-actions")
def api_hourly_action_list(
    mono: str = Query(...),
    sht_date: date = Query(..., alias="date"),
    user: dict = Depends(auth.require_user),
):
    plan = _entry_plan_for_user(mono, user)
    rows = db.query(
        "SELECT Slot, RootCause, CAPAction, CreatedBy, "
        "CONVERT(varchar(19), CreatedAt, 120) AS CreatedAt "
        "FROM app.tHourlyAction WHERE PlanMaster_guid = ? AND ShtDate = ? ORDER BY Slot",
        (plan["PlanMaster_guid"], sht_date),
    )
    by_slot = {int(row["Slot"]): row for row in rows}
    return [
        {"Slot": slot, **by_slot[slot]} if slot in by_slot else {"Slot": slot, "RootCause": "", "CAPAction": ""}
        for slot in range(1, 6)
    ]


class HourlyActionItemIn(EntryModel):
    slot: int = Field(..., alias="Slot", ge=1, le=5)
    root_cause: str = Field("", alias="RootCause", max_length=500)
    cap_action: Optional[str] = Field(None, alias="CAPAction", max_length=500)


class HourlyActionBatchIn(EntryModel):
    mono: str = Field(..., alias="MONo")
    sht_date: date = Field(..., alias="ShtDate")
    items: list[HourlyActionItemIn] = Field(..., alias="Items", min_length=1)


@router.put("/api/hourly-actions")
@router.post("/api/hourly-actions")
def api_hourly_action_save(
    body: HourlyActionBatchIn,
    user: dict = Depends(auth.require_user),
):
    plan = _entry_plan_for_user(body.mono, user)
    if body.sht_date > date.today() or len({item.slot for item in body.items}) != len(body.items):
        raise HTTPException(422, "Ngày tương lai hoặc mốc giờ trùng không hợp lệ")
    for item in body.items:
        if (item.cap_action or '').strip() and not item.root_cause.strip():
            raise HTTPException(422, f"Mốc {item.slot}: cần nhập nguyên nhân")
    with db.get_conn() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        for item in body.items:
            root = item.root_cause.strip()
            cap = (item.cap_action or "").strip() or None
            cur.execute(
                "SELECT HourlyAction_guid FROM app.tHourlyAction "
                "WHERE PlanMaster_guid = ? AND ShtDate = ? AND Slot = ?",
                (plan["PlanMaster_guid"], body.sht_date, item.slot),
            )
            existing = cur.fetchone()
            if not root and not cap:
                if existing:
                    cur.execute("DELETE FROM app.tHourlyAction WHERE HourlyAction_guid = ?", (existing[0],))
                continue
            if not root:
                raise HTTPException(422, f"Mốc {item.slot}: cần nhập nguyên nhân")
            if existing:
                cur.execute(
                    "UPDATE app.tHourlyAction SET RootCause = ?, CAPAction = ?, "
                    "CreatedBy = ?, CreatedAt = SYSDATETIME() WHERE HourlyAction_guid = ?",
                    (root, cap, user["UserID"], existing[0]),
                )
            else:
                cur.execute(
                    "INSERT INTO app.tHourlyAction "
                    "(ShtDate, [LineNo], PlanMaster_guid, Slot, RootCause, CAPAction, CreatedBy) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (body.sht_date, plan["LineNo"], plan["PlanMaster_guid"], item.slot,
                     root, cap, user["UserID"]),
                )
        conn.commit()
    return {"ok": True}


# ============================================================
# Plans / Stations / Catalogs
# ============================================================
@router.get("/api/plans")
def api_plans(user: dict = Depends(auth.require_user)):
    """Return child plans that belong to the logged-in line lead."""
    is_admin = (user.get("Role") or "").lower() == "admin"
    if user["Dept"] is None and not is_admin:
        raise HTTPException(400, "Tài khoản chưa gắn số tổ (Dept)")
    where_sql = ""
    params: tuple = ()
    if not is_admin:
        where_sql = "WHERE pm.[LineNo] = ?"
        params = (user["Dept"],)
    rows = db.query(
        """
        SELECT pm.MONo, pm.SoDonHang, pm.StyleNo, pm.[LineNo] AS LineNoOut,
               pm.Customer, pm.NhuCauMe,
               CONVERT(varchar(10), pm.FirstHangDate, 120) AS FirstHangDate,
               pm.SLKH,
               (SELECT COUNT(*) FROM app.tClusterStationConfig c
                WHERE c.NhuCauMe = pm.NhuCauMe) AS ClusterCount
        FROM app.tPlanMaster pm
        """ + where_sql + """
        ORDER BY pm.FirstHangDate DESC, pm.SoDonHang
        """,
        params,
    )
    return rows


@router.get("/api/stations")
def api_stations(
    mono: str = Query(...),
    _user: dict = Depends(auth.require_user),
):
    """Return all route-step groups for the selected MONo."""
    rows = db.query(
        """
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
                 STRING_AGG(SeqName, ' + ') WITHIN GROUP (ORDER BY Odr) AS GroupLabel
          FROM Steps
          GROUP BY HeadOdr
        )
        SELECT
            CONCAT('odr:', CAST(g.HeadOdr AS varchar(20))) AS StationKey,
            CAST(NULL AS varchar(50)) AS StationGuid,
            CONCAT(CAST(g.HeadOdr AS varchar(20)), '. ', g.GroupLabel) AS StationLabel,
            g.HeadOdr AS RouteStepOdr,
            g.GroupLabel
        FROM Groups g
        ORDER BY g.HeadOdr
        """,
        (mono,),
    )
    if not rows:
        raise HTTPException(400, "Kế hoạch chưa có danh sách công đoạn")
    return rows


@router.get("/api/defect-catalog")
def api_defect_catalog():
    return db.query(
        "SELECT DefectCode, DefectName, DefectGroup, DisplayOrder "
        "FROM app.tDefectCatalog WHERE IsActive = 1 "
        "ORDER BY DisplayOrder"
    )


@router.get("/api/machines")
def api_machines():
    return db.query(
        "SELECT MachineID, MachineName FROM app.tMachineCatalog "
        "WHERE IsActive = 1 ORDER BY MachineName"
    )


# ============================================================
# Defect log
# ============================================================
class DefectItemIn(EntryModel):
    defect_code: str = Field(..., alias="DefectCode")
    station_guid: Optional[str] = Field(None, alias="StationGuid")
    station_label: str = Field(..., alias="StationLabel")
    qty: int = Field(..., alias="Qty", gt=0)


class DefectBatchIn(EntryModel):
    mono: str = Field(..., alias="MONo")
    sht_date: date = Field(..., alias="ShtDate")
    slot: int = Field(..., alias="Slot", ge=1, le=5)
    items: list[DefectItemIn] = Field(..., alias="Items", min_length=1)


@router.post("/api/defect-batch")
def api_defect_batch(
    body: DefectBatchIn,
    user: dict = Depends(auth.require_user),
):
    plan = _resolve_plan(body.mono)
    if (user.get("Role") or "").lower() != "admin" and user["Dept"] is not None and user["Dept"] != plan["LineNo"]:
        raise HTTPException(403, "Kế hoạch không thuộc tổ của bạn")
    inserted = 0
    try:
        with db.get_conn() as conn:
            cur = conn.cursor()
            for it in body.items:
                cur.execute(
                    "INSERT INTO app.tDefectLog "
                    "(PlanMaster_guid, ShtDate, [LineNo], Slot, "
                    " DefectCode, StationGuid, StationLabel, Qty, CreatedBy) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        plan["PlanMaster_guid"],
                        body.sht_date,
                        plan["LineNo"],
                        body.slot,
                        it.defect_code,
                        it.station_guid,
                        it.station_label,
                        it.qty,
                        user["UserID"],
                    ),
                )
                inserted += 1
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Lưu thất bại: {exc}") from exc
    return {"ok": True, "inserted": inserted}


@router.get("/api/defect-log")
def api_defect_log_list(
    mono: str = Query(...),
    sht_date: date = Query(..., alias="date"),
    slot: Optional[int] = None,
    _user: dict = Depends(auth.require_user),
):
    """List defect logs for one plan/date after data entry."""
    plan = _resolve_plan(mono)
    sql = (
        "SELECT CAST(dl.DefectLog_guid AS varchar(50)) AS DefectLog_guid, "
        "dl.Slot, dl.DefectCode, dc.DefectName, "
        "dl.StationLabel, dl.Qty, dl.CreatedBy, "
        "CONVERT(varchar(19), dl.LoggedAt, 120) AS LoggedAt "
        "FROM app.tDefectLog dl "
        "JOIN app.tDefectCatalog dc ON dl.DefectCode = dc.DefectCode "
        "WHERE dl.PlanMaster_guid = ? AND dl.ShtDate = ?"
    )
    params: list[Any] = [plan["PlanMaster_guid"], sht_date]
    if slot is not None:
        sql += " AND dl.Slot = ?"
        params.append(slot)
    sql += " ORDER BY dl.Slot, dl.LoggedAt DESC"
    return db.query(sql, params)


@router.delete("/api/defect-log/{guid}")
def api_defect_log_delete(
    guid: str,
    _user: dict = Depends(auth.require_user),
):
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM app.tDefectLog WHERE DefectLog_guid = ?", (guid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Không tìm thấy")
    return {"ok": True}


# ============================================================
# Machine breakdown
# ============================================================
class BreakdownItemIn(EntryModel):
    machine_id: int = Field(..., alias="MachineID", gt=0)
    down_minutes: int = Field(..., alias="DownMinutes", gt=0)
    reason: Optional[str] = Field(None, alias="Reason")


class BreakdownBatchIn(EntryModel):
    mono: str = Field(..., alias="MONo")
    sht_date: date = Field(..., alias="ShtDate")
    slot: int = Field(..., alias="Slot", ge=1, le=5)
    items: list[BreakdownItemIn] = Field(..., alias="Items", min_length=1)


@router.post("/api/breakdown-batch")
def api_breakdown_batch(
    body: BreakdownBatchIn,
    user: dict = Depends(auth.require_user),
):
    plan = _resolve_plan(body.mono)
    if (user.get("Role") or "").lower() != "admin" and user["Dept"] is not None and user["Dept"] != plan["LineNo"]:
        raise HTTPException(403, "Kế hoạch không thuộc tổ của bạn")
    inserted = 0
    try:
        with db.get_conn() as conn:
            cur = conn.cursor()
            for it in body.items:
                cur.execute(
                    "INSERT INTO app.tMachineBreakdown "
                    "(PlanMaster_guid, ShtDate, [LineNo], Slot, "
                    " MachineID, DownMinutes, Reason, CreatedBy) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        plan["PlanMaster_guid"],
                        body.sht_date,
                        plan["LineNo"],
                        body.slot,
                        it.machine_id,
                        it.down_minutes,
                        it.reason,
                        user["UserID"],
                    ),
                )
                inserted += 1
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Lưu thất bại: {exc}") from exc
    return {"ok": True, "inserted": inserted}


@router.get("/api/breakdown-log")
def api_breakdown_log(
    mono: str = Query(...),
    sht_date: date = Query(..., alias="date"),
    _user: dict = Depends(auth.require_user),
):
    plan = _resolve_plan(mono)
    return db.query(
        "SELECT CAST(b.Breakdown_guid AS varchar(50)) AS Breakdown_guid, "
        "b.Slot, b.MachineID, mc.MachineName, "
        "b.DownMinutes, b.Reason, b.CreatedBy, "
        "CONVERT(varchar(19), b.LoggedAt, 120) AS LoggedAt "
        "FROM app.tMachineBreakdown b "
        "JOIN app.tMachineCatalog mc ON b.MachineID = mc.MachineID "
        "WHERE b.PlanMaster_guid = ? AND b.ShtDate = ? "
        "ORDER BY b.Slot, b.LoggedAt DESC",
        (plan["PlanMaster_guid"], sht_date),
    )


@router.delete("/api/breakdown-log/{guid}")
def api_breakdown_log_delete(
    guid: str,
    _user: dict = Depends(auth.require_user),
):
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM app.tMachineBreakdown WHERE Breakdown_guid = ?", (guid,),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Không tìm thấy")
    return {"ok": True}


# ============================================================
# Reinspect
# ============================================================
@router.get("/api/reinspect")
def api_reinspect_get(
    mono: str = Query(...),
    sht_date: date = Query(..., alias="date"),
    _user: dict = Depends(auth.require_user),
):
    plan = _resolve_plan(mono)
    defect_total = _defect_total_kcs(plan["PlanMaster_guid"], sht_date)
    rows = db.query(
        "SELECT FixedQty, "
        "CONVERT(varchar(19), UpdatedAt, 120) AS UpdatedAt, UpdatedBy "
        "FROM app.tReinspectDaily WHERE PlanMaster_guid = ? AND ShtDate = ?",
        (plan["PlanMaster_guid"], sht_date),
    )
    fixed = int(rows[0]["FixedQty"]) if rows else 0
    return {
        "DefectTotal": defect_total,
        "FixedQty": fixed,
        "Remaining": max(defect_total - fixed, 0),
        "UpdatedAt": rows[0]["UpdatedAt"] if rows else None,
        "UpdatedBy": rows[0]["UpdatedBy"] if rows else None,
    }


class ReinspectIn(EntryModel):
    mono: str = Field(..., alias="MONo")
    sht_date: date = Field(..., alias="ShtDate")
    fixed_qty: int = Field(..., alias="FixedQty", ge=0)


@router.post("/api/reinspect")
def api_reinspect_set(
    body: ReinspectIn,
    user: dict = Depends(auth.require_user),
):
    plan = _resolve_plan(body.mono)
    if (user.get("Role") or "").lower() != "admin" and user["Dept"] is not None and user["Dept"] != plan["LineNo"]:
        raise HTTPException(403, "Kế hoạch không thuộc tổ của bạn")
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "MERGE app.tReinspectDaily AS tgt "
            "USING (SELECT ? AS PlanMaster_guid, ? AS ShtDate) AS src "
            "  ON tgt.PlanMaster_guid = src.PlanMaster_guid "
            "  AND tgt.ShtDate = src.ShtDate "
            "WHEN MATCHED THEN UPDATE SET "
            "  FixedQty = ?, UpdatedAt = SYSDATETIME(), UpdatedBy = ? "
            "WHEN NOT MATCHED THEN INSERT "
            "  (PlanMaster_guid, ShtDate, FixedQty, UpdatedBy) "
            "  VALUES (?, ?, ?, ?);",
            (
                plan["PlanMaster_guid"],
                body.sht_date,
                body.fixed_qty,
                user["UserID"],
                plan["PlanMaster_guid"],
                body.sht_date,
                body.fixed_qty,
                user["UserID"],
            ),
        )
    defect_total = _defect_total_kcs(plan["PlanMaster_guid"], body.sht_date)
    return {
        "ok": True,
        "DefectTotal": defect_total,
        "FixedQty": body.fixed_qty,
        "Remaining": max(defect_total - body.fixed_qty, 0),
    }
