"""API cho QLCL đọc sản lượng ra chuyền (chuyền treo) theo MONo + ngày.

QLCL gọi khi QC mở trang nhập liệu (kéo số trực tiếp, không phụ thuộc vòng push nền).
Số = cùng công thức TV-1: bước cuối cụm 6 theo cấu hình, cộng MỌI bàn QC
(fallback StRole=13 khi plan chưa cấu hình cụm 6), QcOdr=0, ShtDate = ngày yêu cầu.

Auth: header X-API-Key phải trùng QLCL_API_KEY (dùng chung key với chiều push sang QLCL).
"""
from __future__ import annotations

import hmac
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from . import tv
from .admin import QLCL_API_KEY

router = APIRouter(prefix="/api/qlcl", tags=["qlcl"])


def _require_key(request: Request) -> None:
    sent = request.headers.get("X-API-Key") or ""
    if not QLCL_API_KEY or not hmac.compare_digest(sent, QLCL_API_KEY):
        raise HTTPException(status_code=403, detail="API key không hợp lệ")


def daily_output(mono: str, the_date: date) -> dict:
    """Sản lượng ra chuyền 1 ngày của MONo (giống TV-1 / cụm 6)."""
    qc_seq, qc_stno = tv._tv1_qc_filter(mono)
    kcs = tv._output_kcs(mono, the_date, the_date, (qc_seq, qc_stno)) if qc_seq is not None else {"Qty": 0, "Def": 0}
    return {
        "mono": mono,
        "date": the_date.isoformat(),
        "qty": int(kcs["Qty"]),
        "defective_qty": int(kcs["Def"]),
        "seq_no": qc_seq,
        "st_no": qc_stno,
    }


@router.get("/hanging-output")
def api_hanging_output(
    request: Request,
    mono: str = Query(..., min_length=1),
    the_date: date = Query(..., alias="date"),
):
    _require_key(request)
    return daily_output(mono.strip(), the_date)
