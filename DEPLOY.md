# DEPLOY.md — App Chuyền Treo (hanging_line_factory)

Hướng dẫn triển khai app chuyền treo cho từng XN từ đầu đến khi chạy được.

---

## Yêu cầu hệ thống

| Thành phần | Phiên bản |
|---|---|
| Python | 3.12+ |
| SQL Server | Express hoặc Standard (đã có sẵn — dùng chung với MES) |
| ODBC Driver | ODBC Driver 17 hoặc 18 for SQL Server |
| Windows | 10 / 11 / Server 2019+ |

---

## Bước 1 — Lấy code

```powershell
# Clone lần đầu
git clone https://github.com/<org>/hanging_line_factory.git
cd hanging_line_factory

# Hoặc nếu đã clone, cập nhật code mới nhất
git pull origin main
```

---

## Bước 2 — Tạo virtual environment & cài thư viện

```powershell
# Tạo venv (chỉ cần làm 1 lần)
python -m venv .venv

# Kích hoạt venv (phải làm mỗi lần mở terminal mới)
.\.venv\Scripts\Activate.ps1

# Cài dependencies
pip install -r requirements.txt
```

> **Lưu ý**: Nếu PowerShell báo lỗi "execution policy", chạy trước:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

## Bước 3 — Cấu hình môi trường (.env)

```powershell
# Copy file mẫu
Copy-Item .env.example .env

# Mở và chỉnh sửa
notepad .env
```

Các biến **bắt buộc** phải điền đúng:

```env
# SQL Server — thay theo máy thực tế
HANGING_SQL_SERVER=.\SQLEXPRESS       # hoặc TENMAY\INSTANCE
HANGING_APP_DB=hanging_app
HANGING_MES_DB=MSD
HANGING_SQL_DRIVER=ODBC Driver 17 for SQL Server

# Đơn vị XN — mỗi xưởng đặt khác nhau
QLCL_DON_VI=XN3                       # XN1, XN2, XN3, XN1-V1 ...

# URL QLCL server
QLCL_API_URL=https://qlcl.hachibavn.com

# API key — lấy từ quản trị QLCL server (phải trùng với key bên QLCL)
QLCL_API_KEY=<key_do_admin_QLCL_cung_cap>
```

**Kiểm tra SQL Server instance**:
```powershell
Get-Service -Name 'MSSQL*' | Select-Object Name, Status
# Ví dụ kết quả: MSSQLSERVER, SQLEXPRESS, MSD ...
```

**Kiểm tra ODBC Driver**:
```powershell
Get-OdbcDriver | Where-Object Name -like "ODBC Driver*SQL Server*"
```

---

## Bước 4 — Tạo database & chạy migration

```powershell
# Script này tự CREATE DATABASE hanging_app nếu chưa có
# Sau đó áp dụng tất cả migration trong app/migrations/
.\run.ps1 -Migrate
```

Nếu thành công sẽ thấy: `✓ Migration 007 applied`.

> **Lần đầu chạy** sẽ tạo database từ đầu — không mất dữ liệu MES vì chỉ tạo schema `app.*`.

---

## Bước 5 — Khởi động app

```powershell
# Chạy bình thường (production)
.\run.ps1

# Chạy dev mode (tự reload khi sửa code)
.\run.ps1 -Reload
```

App chạy tại: **http://127.0.0.1:8016**

TV Dashboards:
- http://127.0.0.1:8016/tv/1 — Sản lượng theo giờ
- http://127.0.0.1:8016/tv/2 — 6 cụm máy
- http://127.0.0.1:8016/tv/3 — Chất lượng QC
- http://127.0.0.1:8016/tv/4 — Tiến độ kế hoạch

---

## Bước 6 — Đồng bộ kế hoạch sang QLCL

Sau khi đã nhập kế hoạch sản xuất vào app:

1. Mở Admin: http://127.0.0.1:8016/admin
2. Đăng nhập bằng tài khoản admin
3. Trang Tổng quan → nhấn **"Đồng bộ ngay"**
4. Kiểm tra kết quả: inserted / updated / skipped

> TV-3 sẽ tự động lấy dữ liệu QC từ QLCL server sau khi kế hoạch được đồng bộ.

---

## Cập nhật code (pull mới)

```powershell
# 1. Backup .env (giữ lại cấu hình)
Copy-Item .env .env.bak

# 2. Pull code mới
git pull origin main

# 3. Cài thêm thư viện mới (nếu có thay đổi requirements.txt)
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 4. Chạy migration mới (idempotent — an toàn chạy nhiều lần)
.\run.ps1 -Migrate

# 5. Khởi động lại app
.\run.ps1
```

---

## Chạy như Windows Service (tùy chọn, cho production)

Nếu muốn app tự khởi động cùng Windows, dùng NSSM:

```powershell
# Tải NSSM từ https://nssm.cc/download
# Đặt nssm.exe vào C:\Windows\System32

nssm install HangingLineApp "D:\hanging_line_factory\.venv\Scripts\python.exe"
nssm set HangingLineApp AppParameters "-m uvicorn app.main:app --host 0.0.0.0 --port 8016"
nssm set HangingLineApp AppDirectory "D:\hanging_line_factory"
nssm set HangingLineApp AppEnvironmentExtra "PYTHONDONTWRITEBYTECODE=1"
nssm start HangingLineApp
```

---

## Xử lý sự cố thường gặp

**Lỗi kết nối SQL Server**
```
pyodbc.OperationalError: ('08001', ...)
```
→ Kiểm tra `HANGING_SQL_SERVER` trong `.env`. Chạy thử:
```powershell
sqlcmd -S .\SQLEXPRESS -Q "SELECT @@VERSION"
```

**Lỗi ODBC Driver không tìm thấy**
```
('IM002', 'Data source name not found ...')
```
→ Cài ODBC Driver: https://aka.ms/downloadmsodbcsql

**TV-3 không hiện dữ liệu QC**
→ Kiểm tra `QLCL_API_URL` và `QLCL_API_KEY` trong `.env`.
→ Thử gọi thủ công: `curl http://127.0.0.1:8016/tv/api/tv3`
