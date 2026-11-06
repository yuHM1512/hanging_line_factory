"""Gán tay MONo (MSD, chuyền treo) <-> Nhu cầu mẹ trên Sheet báo cáo 2H.

QLCL chưa có dữ liệu, nên TV-3 chuyền treo tạm hiển thị chất lượng nhập trong Data-U2
(cột N, Q:AK — cùng logic với chuyền bệt, xem flat_quality). MONo trong app và mã nhu cầu
trên Sheet không có khoá chung, nên admin gán tay ở /admin/sheet-demand-map.
Dữ liệu Sheet lấy từ snapshot do flat_sheet.sync() lưu (payload["hanging"]), không gọi Sheet trực tiếp.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from . import auth, db, flat_quality, flat_sheet

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(auth.require_admin)])


def _line(team: str) -> Optional[int]:
    match = re.search(r"L\s*(\d+)", team or "", re.I)
    return int(match.group(1)) if match else None


def _hanging() -> tuple[list, dict]:
    try:
        snap = flat_sheet.snapshot()
    except HTTPException:
        return [], {}
    return snap.get("hanging", []), snap


def mapped_demand(mono: str) -> Optional[str]:
    rows = db.query("SELECT NhuCauMe FROM app.tSheetDemandMap WHERE MONo = ?", (mono,))
    return rows[0]["NhuCauMe"] if rows else None


def tv3_quality(mono: str, the_date: date, line_no: Optional[int] = None) -> tuple[dict, dict]:
    """(summary theo flat_quality.summarize, meta cho TV). Không gán / không có dữ liệu → summary rỗng + qc_message."""
    empty = flat_quality.summarize([], -1)
    demand = mapped_demand(mono)
    if not demand:
        return empty, dict(sheet_demand=None, qc_message="MONo chưa được gán Nhu cầu mẹ trên Sheet (Quản trị → Gán nhu cầu Sheet)")
    hanging, snap = _hanging()
    meta = dict(sheet_demand=demand, synced_at=snap.get("synced_at"), sync_error=snap.get("sync_error"), qc_message=None)
    item = next((h for h in hanging if h["demand"] == demand), None)
    if not item:
        meta["qc_message"] = f"Chưa có dòng báo cáo nào của nhu cầu {demand} trên Sheet"
        return empty, meta
    reports = item["reports"]
    # Một nhu cầu mẹ có thể chạy nhiều tổ: ưu tiên dòng của đúng tổ của MONo.
    if line_no is not None:
        own = [r for r in reports if _line(r["team"]) == line_no]
        reports = own or reports
    day = [r for r in reports if r["day"] == the_date.isoformat()]
    q = flat_quality.summarize(day, max((r["slot"] for r in day), default=-1))
    if not day:
        meta["qc_message"] = "Chưa có báo cáo 2H trên Sheet cho ngày này"
    return q, meta


# ============================================================
# Admin: trang gán tay
# ============================================================
@router.get("/sheet-demand-map")
def page_sheet_demand_map(request: Request):
    from .admin import templates
    return templates.TemplateResponse(
        "admin/sheet-demand-map.html", {"request": request, "user": request.state.current_user}
    )


def _suggest(plan: dict, demands: list) -> Optional[str]:
    """Gợi ý: nhu cầu cùng tổ và chứa mã hàng, mới nhất trước. Chỉ gợi ý — người dùng vẫn phải bấm Lưu."""
    style = (plan.get("StyleNo") or "").strip()
    if not style:
        return None
    for d in demands:
        if style in d["demand"] and plan.get("LineNo") in {_line(t) for t in d["teams"]}:
            return d["demand"]
    return None


@router.get("/api/sheet-demand-map")
def api_sheet_demand_map():
    hanging, snap = _hanging()
    demands = [dict(demand=h["demand"], teams=h["teams"], first_day=h["first_day"], last_day=h["last_day"],
                    quality_rows=sum(1 for r in h["reports"] if r["quality"]["defects"] or r["quality"]["defect_qty"] is not None))
               for h in hanging]
    plans = db.query(
        "SELECT pm.MONo, pm.[LineNo], pm.StyleNo, pm.Customer, pm.FirstHangDate, "
        "m.NhuCauMe AS SheetDemand, m.UpdatedBy, CONVERT(varchar(16), m.UpdatedAt, 120) AS UpdatedAt "
        "FROM app.tPlanMaster pm LEFT JOIN app.tSheetDemandMap m ON m.MONo = pm.MONo "
        "ORDER BY pm.FirstHangDate DESC, pm.[LineNo], pm.MONo"
    )
    known = {d["demand"] for d in demands}
    for p in plans:
        if p["FirstHangDate"]:
            p["FirstHangDate"] = p["FirstHangDate"].strftime("%Y-%m-%d")
        p["Suggested"] = None if p["SheetDemand"] else _suggest(p, demands)
        p["SheetDemandFound"] = p["SheetDemand"] in known if p["SheetDemand"] else None
    return dict(plans=plans, demands=demands, synced_at=snap.get("synced_at"), sync_error=snap.get("sync_error"))


class SheetDemandIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    mono: str = Field(..., alias="MONo", min_length=1, max_length=100)
    demand: str = Field(..., alias="NhuCauMe", min_length=1, max_length=100)


@router.put("/api/sheet-demand-map")
def api_sheet_demand_map_save(body: SheetDemandIn, user: dict = Depends(auth.require_admin)):
    if not db.query("SELECT 1 FROM app.tPlanMaster WHERE MONo = ?", (body.mono,)):
        raise HTTPException(404, f"MONo {body.mono!r} không có trong kế hoạch")
    from .admin import _actor_id
    actor = _actor_id(user)
    demand = body.demand.strip()
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE app.tSheetDemandMap SET NhuCauMe=?, UpdatedAt=SYSDATETIME(), UpdatedBy=? WHERE MONo=?",
                    (demand, actor, body.mono))
        if not cur.rowcount:
            cur.execute("INSERT INTO app.tSheetDemandMap (MONo, NhuCauMe, UpdatedBy) VALUES (?,?,?)",
                        (body.mono, demand, actor))
    return {"ok": True}


@router.delete("/api/sheet-demand-map")
def api_sheet_demand_map_delete(mono: str):
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM app.tSheetDemandMap WHERE MONo = ?", (mono,))
        if cur.rowcount == 0:
            raise HTTPException(404, "MONo chưa được gán")
    return {"ok": True}
