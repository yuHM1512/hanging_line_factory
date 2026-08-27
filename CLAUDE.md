# CLAUDE.md — Hanging Conveyor Dashboard (XN2)

Web app trực quan hoá dữ liệu sản xuất hệ chuyền treo MES, triển khai tại xưởng may XN2.

---

## Kiến trúc tổng quan

| Layer | Công nghệ |
|---|---|
| Backend | FastAPI + pyodbc (Python 3.x) |
| Frontend | Jinja2 templates + vanilla JS + Chart.js |
| Database nguồn | SQL Server `MSD` — read-only, Windows Auth |
| Database app | SQL Server `hanging_app` — schema `app.*` |
| Giao thức | HTTP (internal LAN), port **8016** cố định |
| Tích hợp ngoài | App QLCL trung tâm tại `QLCL_API_URL` (mặc định port 8008) |

**Cấu trúc thư mục:**

```
app/
  main.py        — FastAPI instance, routers, auto-sync thread
  db.py          — pyodbc connection helper, query(), _expand()
  auth.py        — cookie auth, require_user / require_admin
  queries.py     — SQL query templates (dashboard data)
  admin.py       — Admin router: kế hoạch, user, QLCL sync (~60KB)
  tv.py          — TV router: TV-1/2/4 dashboards (~42KB)
  entry.py       — Entry router: nhập liệu tổ trưởng
  migrations/    — SQL migration files (001→010)
templates/
  base.html      — base layout
  index.html     — Dashboard chính
  login.html
  admin/         — Admin pages
  entry/         — Entry pages
  tv/            — TV-1, TV-2, TV-4, setup pages
static/          — CSS, JS, assets
scripts/         — apply_migrations.py, create_app_db.py, seed_curve.py
```

---

## Quy tắc vàng — "Hàng ra chuyền"

**Mọi query tính sản lượng đều phải có điều kiện:**

```sql
WHERE st.StRole = 13 AND rw.IsLastSeq = 1
```

- `StRole = 13` → trạm chốt sản lượng (trạm cuối dây chuyền)
- `IsLastSeq = 1` → lần scan cuối cùng của sequence đó

**Không được bỏ hai điều kiện này** khi tính Qty, DefectiveQty, hay bất kỳ KPI nào. Đây là nguồn sự thật duy nhất cho "sản lượng ra chuyền."

---

## Database — hai DB riêng biệt

```python
# db.py
SERVER  = os.environ["HANGING_SQL_SERVER"]   # mặc định: .\SQLEXPRESS
APP_DB  = os.environ["HANGING_APP_DB"]        # mặc định: hanging_app
MES_DB  = os.environ["HANGING_MES_DB"]        # mặc định: MSD
```

- **APP_DB** (`hanging_app`): schema `app.*`, chứa `app.tUser`, `app.tPlanMaster`, `app.tPlanDetail`, v.v.
- **MES_DB** (`MSD`): chứa `dbo.tRecentWork`, `dbo.tStation`, v.v. — **chỉ đọc, không ghi**

Query đọc MES dùng 3-part name: `{MES_DB}.dbo.tRecentWork`. Helper `db._expand(sql)` thay `{MES_DB}` bằng tên DB thực tế. **Luôn dùng sentinel `{MES_DB}` thay vì hardcode `MSD`.**

```python
# Cách dùng db.query()
rows = db.query("SELECT * FROM {MES_DB}.dbo.tRecentWork WHERE ...", params)
```

Connection dùng Windows Authentication (Trusted_Connection=yes), **không có username/password** trong code.

---

## CTE chuẩn — NormalizedWork

Mọi query phân tích dùng CTE `NormalizedWork` (định nghĩa trong `queries.py`). CTE này:
- Join `tRecentWork` + `tStation` để lấy `StRole`
- Parse `logical_line_no` từ `MONo` theo pattern `LINE {n}`
- Parse `plan_key` từ `MONo` (phần sau dấu `#`)

**Khi thêm query mới: tái sử dụng `NORMALIZED_WORK_CTE` + `_base_where()` trong `queries.py` thay vì viết lại CTE.**

---

## Parse MONo → Tổ

`MONo` trong MES có thể có 2 dạng:

| Format | Ví dụ | Tổ |
|---|---|---|
| Cũ — có "LINE" | `LINE 3 #324230-4` | 3 |
| Cũ — có "LINE" | `LINE; 6-#D093-6` | 6 |
| Mới — StyleNo-LineNo | `376556-5` | 5 |
| Mới — với # | `#D093-6` | 6 |
| Mới — lần 2 | `376556-5-2` | 5 |

Hàm `admin.parse_mono(mono)` xử lý cả hai format. Trong SQL, `NORMALIZED_WORK_CTE` dùng `PATINDEX('%LINE%')` để extract logical_line_no.

---

## Authentication

- Cookie-based, không dùng JWT/OAuth
- Cookie name: `hc_user` (chứa `UserID`)
- Không có password — chỉ cần `UserID` tồn tại trong `app.tUser`
- Cookie max_age: 12 giờ

**Roles:**

| Role | Quyền | Home |
|---|---|---|
| `admin` | Toàn quyền + Admin panel | `/admin` |
| user/tổ trưởng | Nhập liệu tổ của mình | `/entry` |

Middleware helper:
- `auth.require_user(request)` — redirect 401 nếu chưa login
- `auth.require_admin(request)` — 403 nếu không phải admin

---

## Các router chính

### `/` → main.py
Redirect: nếu đã login → role_home, chưa login → `/login`

### `/admin` → admin.py
- Requires `Role == admin`
- Quản lý kế hoạch (tPlanMaster/tPlanDetail), users, demand_flow
- Tích hợp QLCL: push kế hoạch sang app QLCL qua HTTP + `X-API-Key`
- Parse danh sách kế hoạch từ MES, auto-populate từ MONo

### `/entry` → entry.py
- Requires login (bất kỳ role)
- Tổ trưởng nhập số liệu hàng ngày: output, defect KCS, v.v.
- Lọc kế hoạch theo `user.Dept` (= số tổ của tổ trưởng)

### `/tv` → tv.py
- Không yêu cầu login (màn hình TV nhà xưởng)
- **TV-1**: Dashboard sản lượng chính + KPI slot
- **TV-2**: Biểu đồ tiến độ theo giờ
- **TV-4**: Tổng hợp chất lượng (lấy data từ QLCL qua `/api/tv3/qc-data`)
- `/tv` (setup): cấu hình gallery + rotation (localStorage)
- Thời gian làm việc: 492 phút/ngày (8h12m, đã trừ break)
- 5 slot: 07:30-09:30, 09:30-11:30, 12:30-14:30, 14:30-16:30, Sau 16:30

### Dashboard chính → `/dashboard`
- API endpoints `/api/*` trong main.py
- Filter: date range (from/to), line_no (optional), plan_key (optional)

---

## API Endpoints quan trọng

```
GET /api/health                   — DB ping
GET /api/filters/lines            — Danh sách tổ: [{line_no: 1}, {line_no: 6}]
GET /api/filters/plans?from&to    — MONo list trong khoảng
GET /api/filters/bounds           — min/max ngày có dữ liệu
GET /api/summary?from&to          — KPI: output, defect, lines, plans, days, workers
GET /api/output/by-day            — Sản lượng theo ngày × tổ
GET /api/output/by-hour           — Throughput theo giờ
GET /api/output/by-slot           — Throughput theo 5 slot ca
GET /api/output/by-line           — Phân bố theo tổ
GET /api/output/by-plan           — Plan × Tổ × Màu × Cỡ
GET /api/workers                  — Năng suất công nhân (MAX(qty_per_seq) per EmpID × StNo)
GET /api/stations/final           — Trạm chốt sản lượng
```

**Lưu ý `worker_productivity`**: dùng `MAX(qty_per_seq)` chứ không `SUM` để tránh nhân bội khi 1 trạm có nhiều SeqNo gộp.

---

## Schema app.* (APP_DB)

Từ migration files:

| Bảng | Mô tả |
|---|---|
| `app.tUser` | UserID, DisplayName, Unit, Dept (số tổ), Role |
| `app.tPlanMaster` | MONo, LineNo, ngày bắt đầu/kết thúc |
| `app.tPlanDetail` | Chi tiết kế hoạch theo ngày |
| `app.tDemandFlow` | Demand flow / mục tiêu sản lượng |
| `app.tProductionCurve` | Đường cong sản xuất chuẩn |
| `app.tHoliday` | Ngày nghỉ lễ |
| `app.tDefectMachine` | Lỗi máy móc |
| `app.tPlanPhanLoai` | Phân loại kế hoạch |
| `app.tPlanAdjustment` | Điều chỉnh kế hoạch |
| `app.tPlanEmployeeAssignment` | Phân công nhân cho kế hoạch |

---

## Tích hợp QLCL

App này push kế hoạch sang **app QLCL trung tâm** (hachibavn.com) để tracking chất lượng:

```
QLCL_API_URL=http://localhost:8008      # local dev
QLCL_API_URL=https://qlcl.hachibavn.com # production
QLCL_API_KEY=<bearer token>
QLCL_DON_VI=XN2                         # đơn vị xưởng này
```

- Push: `POST /api/prod-plan/upsert-batch` với header `X-API-Key`
- Pull (TV-4): `GET /api/tv3/qc-data?mono=...&date=...`
- Timeout TV: 5 giây (TV không chờ lâu)
- Auto-sync: background thread, interval cấu hình bởi `QLCL_AUTO_SYNC_INTERVAL_MINUTES`

---

## Design System — "The Digital Curator"

Định nghĩa đầy đủ trong `DESIGN.md`. Tóm tắt quy tắc bắt buộc:

**The "No-Line" Rule**: **Không dùng 1px solid border** để phân chia layout. Ranh giới chỉ tạo bằng chênh lệch màu nền (`surface-container-low` trên nền `surface`).

**Màu sắc chính:**
- Background: `#f8f9fa`
- Primary brand: `#001848` (navy) / `#0056d2` (blue)
- Cards: `#ffffff` (surface-container-lowest)
- Text: `#191c1d` / `#424654` (variant)

**Typography:**
- Headlines: **Manrope** (700/600)
- Body text: **Inter** (400)

**Glassmorphism**: Navigation bars dùng 80% opacity + `backdrop-blur: 24px`.

**Border radius**: buttons/cards `0.5rem`, large containers `1rem`–`1.5rem`.

---

## Conventions

### Python
- `from __future__ import annotations` ở mọi file
- Type hints đầy đủ
- Params SQL luôn dùng `?` placeholder (pyodbc), không f-string với user input
- Không có ORM — raw SQL qua `db.query()`
- Error handling: exception handler global trong main.py trả JSON 500

### SQL
- Dùng `{MES_DB}` sentinel thay vì hardcode DB name
- Parameterised queries — không string interpolate user input
- CTE pattern: `WITH NormalizedWork AS (...)` rồi query từ CTE

### JavaScript (frontend)
- Vanilla JS, không framework
- Chart.js cho biểu đồ
- Fetch API cho AJAX calls

---

## Chạy local

```powershell
# 1. Tạo .env
copy .env.example .env       # Sửa HANGING_SQL_SERVER, HANGING_MES_DB

# 2. Setup môi trường
.\run.ps1 -Setup             # Tạo .venv + pip install

# 3. Chạy migrations
.\run.ps1 -Migrate           # Tạo hanging_app + schema + seed data

# 4. Chạy server
.\run.ps1                    # http://127.0.0.1:8016

# Login: /login → nhập UserID "admin"
```

App chỉ chạy port **8016**. Không chạy bản sao trên port khác.

---

## Migrations

Chạy theo thứ tự, không skip:

| File | Nội dung |
|---|---|
| 001 | Init schema app.* (tUser, tPlanMaster, tPlanDetail, tDemandFlow) |
| 002 | Demand flow adjustments |
| 003 | SAM / owe / target columns |
| 004 | Defect + machine schema |
| 005 | Drop tUser.IsActive |
| 006 | Seed production curve |
| 007 | Seed holidays |
| 008 | Plan phân loại |
| 009 | Plan adjustments + setup root |
| 010 | Plan employee assignment |

Thêm migration mới: tạo file `0NN_<tên>.sql`, chạy `.\run.ps1 -Migrate`.

---

## Điểm cần chú ý khi sửa code

1. **Không dùng QLCL_APP_DB trực tiếp trong query** — chỉ đọc qua HTTP API.
2. **Không ghi vào MES_DB** — đó là DB nguồn của hệ thống nhà máy.
3. **Admin router** (`admin.py`) rất lớn (~1700 dòng) — khi sửa, chú ý không làm vỡ `_do_sync_to_qlcl()` vì auto-sync thread dùng trực tiếp hàm này.
4. **TV pages** không có authentication — đừng đưa thông tin nhạy cảm lên TV endpoints.
5. **list_lines()** hardcode `[1, 6]` — nếu xưởng thêm tổ mới phải sửa hàm này và regex parse trong CTE.
6. **PLAN_CANDIDATE_START_DATE** trong admin.py hardcode `2026-04-18` — đây là ngày bắt đầu có dữ liệu thực tế của xưởng.

---

## Roadmap (ghi trong README)

- [ ] Filter theo MO ngoài Tổ
- [ ] Trang chi tiết 1 plan (sơ đồ tuyến, trạm chốt)
- [ ] So sánh tổ × tổ cùng MO
- [ ] Heatmap throughput theo giờ × ngày
- [ ] Export CSV/Excel
- [ ] Tổng hợp lỗi theo công đoạn / công nhân
- [ ] Real-time refresh (WebSocket khi có scan mới)
