# Hanging Conveyor Dashboard

Web app trực quan hoá dữ liệu từ hệ chuyền treo MES. Đọc data từ database MES (vd `MSD`) và lưu app data riêng trong `hanging_app` để không can thiệp DB nguồn.

- **Backend**: FastAPI + pyodbc (SQL Server, Windows Auth)
- **Frontend**: Jinja2 + vanilla JS + Chart.js
- **Design**: "The Digital Curator" (xem `DESIGN.md`)

## Quick start

```powershell
copy .env.example .env       # sửa HANGING_MES_DB, HANGING_APP_DB, server
.\run.ps1 -Setup             # tạo venv + cài deps
.\run.ps1 -Migrate           # CREATE hanging_app + schema + seed
.\run.ps1                    # chạy server tại http://127.0.0.1:8016
```

→ Đăng nhập tại `/login` với UserID `admin`. Toàn bộ hướng dẫn deploy + setup operational xem **[SETUP.md](SETUP.md)**.

App chỉ chạy port **8016**. Đừng chạy bản sao trên port khác.

## Cấu hình `.env`

| Biến | Mặc định | Ghi chú |
|---|---|---|
| `HANGING_SQL_SERVER` | `.\SQLEXPRESS` | Tên server / instance |
| `HANGING_APP_DB` | `hanging_app` | DB riêng cho app, migration tự tạo |
| `HANGING_MES_DB` | `MSD` | DB nguồn MES, app chỉ đọc |
| `HANGING_SQL_DRIVER` | `ODBC Driver 17 for SQL Server` | Phải cài driver trước |

## API endpoints

| Endpoint | Mô tả |
|---|---|
| `GET /` | Dashboard HTML |
| `GET /api/health` | Kiểm tra kết nối DB |
| `GET /api/filters/lines` | Danh sách tổ vật lý (LineNo) |
| `GET /api/filters/plans?from&to[&line]` | Danh sách MO trong khoảng |
| `GET /api/filters/bounds` | min/max ngày có dữ liệu |
| `GET /api/summary?from&to[&line]` | KPI tổng hợp |
| `GET /api/output/by-day?from&to[&line]` | Sản lượng / ngày × tổ |
| `GET /api/output/by-hour?from&to[&line]` | Throughput theo giờ |
| `GET /api/output/by-line?from&to` | Phân bố theo tổ |
| `GET /api/output/by-plan?from&to[&line]` | Plan × Tổ × Màu × Cỡ (khớp Excel) |
| `GET /api/workers?from&to[&line]` | Năng suất công nhân × Số trạm |
| `GET /api/stations/final?from&to` | Trạm chốt sản lượng (StRole=13, IsLastSeq=1) |

## Dashboard chuyền bệt

Mở `/tv`, chọn tổ và kế hoạch có ký hiệu **(B)** để xem 4 TV theo **Nhu cầu mẹ**.
Chuyền bệt dùng chung template, preview và xoay vòng TV1–TV4 với chuyền treo.
Các link `/tv/flat/1?demand=...&day=...` cũ chuyển về màn hình chung.
App đồng bộ định kỳ hai Google
Sheets được khai báo bằng nhóm biến `FLAT_LINE_*` trong `.env`, lưu bản dữ liệu
đã kiểm tra vào `hanging_app`, rồi giao diện chỉ đọc database. Chạy migration 016
trước khi bật `FLAT_LINE_SYNC_ENABLED=true`.

Xem [hướng dẫn thiết lập và vùng điền link chuyền bệt](SETUP_CHUYEN_BET.md) để
nhân rộng cấu hình sang xí nghiệp khác.

- TV1: sản lượng quy đổi BP, nhịp độ, OWE và PO/EHD.
- TV2: 6 cụm; tên cụm lấy từ tab `XN2`, cụm 6 dùng BP.
- TV3: QC theo kế hoạch mẹ trong QLCL.
- TV4: tiến độ mẹ theo đường cong năng suất.

Tất cả endpoint sản lượng dùng công thức vàng:

```sql
WHERE st.StRole = 13 AND rw.IsLastSeq = 1
```

Năng suất công nhân tính `OutputQty = MAX(QtyPerSeq)` để khỏi nhân theo số SeqNo gộp tại 1 trạm.

## Cấu trúc

Xem chi tiết trong [SETUP.md §10](SETUP.md#10-cấu-trúc-thư-mục).

## Bổ sung sau (gợi ý)

- [ ] Filter theo MO (kế hoạch) ngoài Tổ
- [ ] Trang chi tiết 1 plan (sơ đồ tuyến, trạm chốt)
- [ ] So sánh tổ × tổ (cùng MO)
- [ ] Heatmap throughput theo giờ × ngày
- [ ] Export CSV/Excel cho từng bảng
- [ ] Tổng hợp lỗi theo công đoạn / công nhân
- [ ] Real-time refresh (websocket khi có scan mới)
