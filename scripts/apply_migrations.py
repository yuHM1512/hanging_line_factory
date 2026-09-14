"""Apply all SQL migrations in app/migrations/ to the APP database.

Usage (from project root):
    .venv/Scripts/python.exe scripts/apply_migrations.py

Or via run.ps1:
    .\run.ps1 -Migrate

Steps:
1. Connect to `master` → CREATE DATABASE [APP_DB] nếu chưa có
2. Connect to APP_DB → chạy 7 file SQL trong app/migrations/ theo thứ tự

Tất cả migration phải idempotent (dùng IF NOT EXISTS). Splits mỗi file theo dòng
chỉ chứa `GO` vì pyodbc không hiểu batch separator của sqlcmd.
"""
from __future__ import annotations

import re
import argparse
import sys
from pathlib import Path

import pyodbc

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from app import db  # noqa: E402  — triggers .env load

GO_RE = re.compile(r"^\s*GO\s*(?:--.*)?$", re.IGNORECASE | re.MULTILINE)
MIG_DIR = PROJECT / "app" / "migrations"


def _master_conn_str() -> str:
    return (
        f"DRIVER={{{db.DRIVER}}};"
        f"SERVER={db.SERVER};"
        f"DATABASE=master;"
        "Trusted_Connection=yes;TrustServerCertificate=yes;"
    )


def ensure_app_db_exists() -> None:
    """CREATE DATABASE nếu chưa có, dùng collation khớp MES_DB. Idempotent.

    Khớp collation rất quan trọng — cross-DB string compare (vd MONo)
    sẽ fail với "collation conflict" nếu hai DB khác collation.
    """
    conn = pyodbc.connect(_master_conn_str(), autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sys.databases WHERE name = ?", (db.APP_DB,))
    if cur.fetchone() is not None:
        print(f"  Database [{db.APP_DB}] đã có sẵn")
        conn.close()
        return

    # Lấy collation của MES_DB để khớp
    cur.execute(
        "SELECT collation_name FROM sys.databases WHERE name = ?", (db.MES_DB,)
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            f"MES database [{db.MES_DB}] không tồn tại — sửa HANGING_MES_DB trong .env."
        )
    mes_collation = row[0]
    print(f"  MES collation = {mes_collation}")

    safe_db = db.APP_DB.replace("]", "]]")
    safe_collation = mes_collation.replace("'", "''")
    print(f"  Database [{db.APP_DB}] chưa tồn tại → CREATE DATABASE … COLLATE {mes_collation}")
    cur.execute(f"CREATE DATABASE [{safe_db}] COLLATE {safe_collation}")
    conn.close()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Apply SQL migrations to the app database.')
    parser.add_argument('--from-version', type=int, default=1)
    parser.add_argument('--to-version', type=int, default=999)
    args = parser.parse_args()
    files = sorted(MIG_DIR.glob("*.sql"))
    files = [f for f in files if args.from_version <= int(f.name.split('_')[0]) <= args.to_version]
    if not files:
        print(f"No migrations found in {MIG_DIR}")
        return 1

    print(f"Server : {db.SERVER}")
    print(f"App DB : {db.APP_DB}")
    print(f"MES DB : {db.MES_DB}")
    print()

    # Safety: REFUSE nếu app DB trùng MES DB — sẽ pollute schema `app.*` vào DB
    # nguồn của hệ chuyền treo, đúng cái lỗi mà refactor này nhằm tránh.
    if db.APP_DB.strip().lower() == db.MES_DB.strip().lower():
        print(
            f"ERROR: HANGING_APP_DB == HANGING_MES_DB ('{db.APP_DB}').\n"
            f"App DB phải KHÁC MES DB để không ghi schema app.* vào database MES.\n"
            f"Sửa .env: đặt HANGING_APP_DB thành tên khác (vd 'hanging_app').",
            file=sys.stderr,
        )
        return 2

    print("[1/2] Ensure app database exists ...")
    try:
        ensure_app_db_exists()
    except Exception as exc:
        print(f"  FAILED: {exc}", file=sys.stderr)
        return 2

    print(f"\n[2/2] Apply {len(files)} migrations từ {MIG_DIR}\n")
    with db.get_conn() as conn:
        cur = conn.cursor()
        for f in files:
            print(f"  {f.name}")
            sql = f.read_text(encoding="utf-8")
            batches = [b.strip() for b in GO_RE.split(sql) if b.strip()]
            for i, batch in enumerate(batches, 1):
                try:
                    cur.execute(batch)
                    while cur.nextset():
                        pass
                except Exception as exc:
                    print(f"    batch {i} FAILED: {exc}", file=sys.stderr)
                    print("    --- batch preview ---", file=sys.stderr)
                    print(batch[:400], file=sys.stderr)
                    return 2

    print("\nAll migrations applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
