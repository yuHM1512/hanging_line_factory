"""Shared cookie-based authentication for admin and entry flows."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from . import db

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

COOKIE_NAME = "hc_user"

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_id: str = Field(..., alias="UserID", min_length=1, max_length=50)


def get_user_by_id(user_id: str) -> dict:
    rows = db.query(
        "SELECT UserID, DisplayName, Unit, Dept, Role "
        "FROM app.tUser WHERE UserID = ?",
        (user_id.strip(),),
    )
    if not rows:
        raise HTTPException(401, "Tài khoản không tồn tại")
    return rows[0]


def get_session_user(request: Request) -> Optional[dict]:
    user_id = request.cookies.get(COOKIE_NAME)
    if not user_id:
        return None
    try:
        return get_user_by_id(user_id)
    except HTTPException:
        return None


def role_home(user: dict) -> str:
    return "/admin" if (user.get("Role") or "").lower() == "admin" else "/entry"


def safe_next_url(value: Optional[str]) -> Optional[str]:
    """Accept only an internal absolute path for post-login redirects."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return None


def require_user(request: Request) -> dict:
    user = get_session_user(request)
    if not user:
        raise HTTPException(401, "Chưa đăng nhập")
    request.state.current_user = user
    return user


def require_admin(request: Request) -> dict:
    user = require_user(request)
    if (user.get("Role") or "").lower() != "admin":
        raise HTTPException(403, "Bạn không có quyền vào khu vực quản trị")
    return user


def attach_session(response: Response, user: dict) -> None:
    response.set_cookie(
        COOKIE_NAME,
        user["UserID"],
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
        max_age=60 * 60 * 12,
    )


@router.get("/login")
def page_login(request: Request):
    next_url = safe_next_url(request.query_params.get("next"))
    user = get_session_user(request)
    if user:
        return RedirectResponse(next_url or role_home(user), status_code=303)
    return templates.TemplateResponse(
        "login.html", {"request": request, "next_url": next_url or ""}
    )


@router.post("/auth/api/login")
def api_login(body: LoginIn, next_url: Optional[str] = Query(None)):
    user = get_user_by_id(body.user_id)
    destination = safe_next_url(next_url) or role_home(user)
    response = JSONResponse({"ok": True, "user": user, "next_url": destination})
    attach_session(response, user)
    return response


@router.post("/auth/api/logout")
def api_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/auth/api/me")
def api_me(request: Request):
    return require_user(request)
