"""FastAPI app: Hanging Conveyor Dashboard."""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import admin, auth, db, entry, queries, tv, flat_line

logger = logging.getLogger(__name__)

# Auto-sync sang QLCL — bật bằng QLCL_AUTO_SYNC_ENABLED=true trong .env
_AUTO_SYNC_ENABLED  = os.getenv("QLCL_AUTO_SYNC_ENABLED", "false").lower() in ("1", "true", "yes")
_AUTO_SYNC_INTERVAL = max(1, int(os.getenv("QLCL_AUTO_SYNC_INTERVAL_MINUTES", "60")))
_auto_sync_started  = False
_auto_sync_lock     = threading.Lock()

# Output sync riêng — chu kỳ ngắn hơn, chỉ push dữ liệu thay đổi
_OUTPUT_SYNC_ENABLED_RAW = os.getenv("QLCL_OUTPUT_SYNC_ENABLED", "").lower()
_OUTPUT_SYNC_ENABLED = (
    _OUTPUT_SYNC_ENABLED_RAW in ("1", "true", "yes")
    if _OUTPUT_SYNC_ENABLED_RAW
    else _AUTO_SYNC_ENABLED
)
_OUTPUT_SYNC_INTERVAL = max(30, int(os.getenv("QLCL_OUTPUT_SYNC_INTERVAL_SECONDS", "120")))
_output_sync_started = False


def _auto_sync_loop() -> None:
    logger.info("QLCL auto-sync started, interval=%s minutes", _AUTO_SYNC_INTERVAL)
    while True:
        time.sleep(_AUTO_SYNC_INTERVAL * 60)
        try:
            result = admin._do_sync_to_qlcl()
            logger.info(
                "QLCL auto-sync ok — inserted=%s updated=%s skipped=%s",
                result.get("inserted", 0),
                result.get("updated", 0),
                result.get("skipped", 0),
            )
        except Exception:
            logger.exception("QLCL auto-sync failed")


def _output_sync_loop() -> None:
    logger.info("QLCL output sync started, interval=%s seconds", _OUTPUT_SYNC_INTERVAL)
    while True:
        time.sleep(_OUTPUT_SYNC_INTERVAL)
        try:
            result = admin._push_output_incremental(lookback_days=1)
            pushed = result.get("dates_pushed", 0)
            if pushed:
                logger.info(
                    "QLCL output sync — dates_checked=%s dates_pushed=%s",
                    result.get("dates_checked", 0), pushed,
                )
        except Exception:
            logger.exception("QLCL output sync failed")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(title="Hanging Conveyor Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(tv.router)
app.include_router(entry.router)
app.include_router(flat_line.router)


@app.on_event("startup")
def startup_auto_sync() -> None:
    global _auto_sync_started, _output_sync_started
    if _AUTO_SYNC_ENABLED:
        with _auto_sync_lock:
            if not _auto_sync_started:
                t = threading.Thread(target=_auto_sync_loop, name="qlcl-auto-sync", daemon=True)
                t.start()
                _auto_sync_started = True
                logger.info("QLCL auto-sync thread started")
    if _OUTPUT_SYNC_ENABLED:
        with _auto_sync_lock:
            if not _output_sync_started:
                t = threading.Thread(target=_output_sync_loop, name="qlcl-output-sync", daemon=True)
                t.start()
                _output_sync_started = True
                logger.info("QLCL output sync thread started (interval=%ss)", _OUTPUT_SYNC_INTERVAL)


def _default_range() -> tuple[date, date]:
    bounds = queries.date_bounds()
    if bounds.get("max_date"):
        d_to = bounds["max_date"]
        d_from = max(bounds["min_date"], d_to - timedelta(days=6))
        return d_from, d_to
    today = date.today()
    return today - timedelta(days=6), today


@app.get("/")
def index(request: Request):
    user = auth.get_session_user(request)
    if user:
        return RedirectResponse(auth.role_home(user), status_code=303)
    return RedirectResponse("/login", status_code=303)


@app.get("/dashboard")
def dashboard(request: Request):
    bounds = queries.date_bounds()
    d_from, d_to = _default_range()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": auth.get_session_user(request),
            "min_date": bounds.get("min_date"),
            "max_date": bounds.get("max_date"),
            "default_from": d_from,
            "default_to": d_to,
        },
    )


@app.get("/api/health")
def health():
    return db.ping()


@app.get("/api/filters/lines")
def api_lines():
    return queries.list_lines()


@app.get("/api/filters/plans")
def api_plans(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    line: Optional[int] = None,
    plan: Optional[str] = None,
):
    return queries.list_plans(date_from, date_to, line)


@app.get("/api/filters/bounds")
def api_bounds():
    return queries.date_bounds()


@app.get("/api/summary")
def api_summary(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    line: Optional[int] = None,
    plan: Optional[str] = None,
):
    return queries.kpi_summary(date_from, date_to, line, plan)


@app.get("/api/output/by-day")
def api_output_by_day(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    line: Optional[int] = None,
    plan: Optional[str] = None,
):
    return queries.output_by_day(date_from, date_to, line, plan)


@app.get("/api/output/by-hour")
def api_output_by_hour(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    line: Optional[int] = None,
    plan: Optional[str] = None,
):
    return queries.output_by_hour(date_from, date_to, line, plan)


@app.get("/api/output/by-slot")
def api_output_by_slot(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    line: Optional[int] = None,
    plan: Optional[str] = None,
):
    return {
        "slots": [{"slot": s, "label": lbl} for s, lbl in queries.SHIFT_SLOTS],
        "rows": queries.output_by_slot(date_from, date_to, line, plan),
    }


@app.get("/api/output/by-line")
def api_output_by_line(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    plan: Optional[str] = None,
):
    return queries.output_by_line(date_from, date_to, plan)


@app.get("/api/output/by-plan")
def api_output_by_plan(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    line: Optional[int] = None,
    plan: Optional[str] = None,
):
    return queries.output_by_plan(date_from, date_to, line, plan)


@app.get("/api/workers")
def api_workers(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    line: Optional[int] = None,
    plan: Optional[str] = None,
):
    return queries.worker_productivity(date_from, date_to, line, plan)


@app.get("/api/stations/final")
def api_final_stations(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    plan: Optional[str] = None,
):
    return queries.final_stations(date_from, date_to, plan)


@app.exception_handler(Exception)
async def unhandled_exc(_request, exc):  # noqa: ANN001
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    """Redirect browser page requests to login while keeping API errors JSON."""
    accepts_html = "text/html" in request.headers.get("accept", "")
    if exc.status_code == 401 and accepts_html:
        destination = request.url.path
        if request.url.query:
            destination += "?" + request.url.query
        return RedirectResponse(
            "/login?next=" + quote(destination, safe=""), status_code=303
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )
