"""SQL Server connection helper.

Tách 2 DB:
- APP_DB  (default `hanging_app`) — DB riêng của app, chứa schema `app.*`.
- MES_DB  (default `MSD`)         — DB nguồn của hệ chuyền treo, read-only.

Connection mặc định trỏ vào APP_DB. Mọi query đọc data MES dùng 3-part name
`{MES_DB}.dbo.tXxx`. Backwards-compat: nếu chỉ set `HANGING_SQL_DB` (cũ) thì
dùng nó làm APP_DB.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterable

import pyodbc

SERVER = os.environ.get("HANGING_SQL_SERVER", r".\SQLEXPRESS")
APP_DB = os.environ.get("HANGING_APP_DB") or os.environ.get("HANGING_SQL_DB", "hanging_app")
MES_DB = os.environ.get("HANGING_MES_DB", "MSD")
DRIVER = os.environ.get("HANGING_SQL_DRIVER", "ODBC Driver 17 for SQL Server")
QUERY_TIMEOUT = int(os.environ.get("HANGING_SQL_QUERY_TIMEOUT", "90"))

# Legacy alias — một số chỗ đọc db.DATABASE
DATABASE = APP_DB

_CONN_STR = (
    f"DRIVER={{{DRIVER}}};"
    f"SERVER={SERVER};"
    f"DATABASE={APP_DB};"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)


@contextmanager
def get_conn():
    conn = pyodbc.connect(_CONN_STR, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def _expand(sql: str) -> str:
    """Replace `{MES_DB}` sentinel với tên DB nguồn MES.

    Cho phép SQL string viết `FROM {MES_DB}.dbo.tRecentWork` mà không cần f-string.
    Substitution chạy ở mọi query, an toàn vì SQL khác không có chuỗi đó.
    """
    return sql.replace("{MES_DB}", MES_DB)


def query(sql: str, params: Iterable[Any] | None = None, *, timeout: int | None = None) -> list[dict]:
    """Run a parameterised query and return list of dict rows."""
    with get_conn() as conn:
        conn.timeout = timeout if timeout is not None else QUERY_TIMEOUT
        cur = conn.cursor()
        cur.execute(_expand(sql), tuple(params) if params else ())
        cols = [c[0] for c in cur.description] if cur.description else []
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return rows


def ping() -> dict:
    try:
        rows = query("SELECT @@SERVERNAME AS server, DB_NAME() AS db, GETDATE() AS now")
        return {"ok": True, **rows[0], "app_db": APP_DB, "mes_db": MES_DB}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
