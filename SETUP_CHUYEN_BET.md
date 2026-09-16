# Thiết lập Dashboard chuyền bệt

Dashboard chuyền bệt được mở tại `/tv`, chung bộ chọn và bốn màn TV với chuyền
treo. Kế hoạch chuyền bệt có ký hiệu **(B)** và được tổng hợp theo **Nhu cầu mẹ**.

## Các thông tin cần chuẩn bị

Mỗi xí nghiệp chỉ cần cung cấp các nguồn sau:

| Mục | Cần cung cấp | Ghi chú |
|---|---|---|
| Đơn vị | `XN1`, `XN2`, `XN3` hoặc `XN1-V1` | Phải khớp tên tổ trong Rải chuyền và Data |
| Link kế hoạch | Link file Google Sheets có tab `Rải chuyền` và tab xí nghiệp | Đây là file thông tin mã hàng |
| Link dữ liệu | Link file Google Sheets có tab `Data-Ux` | Đây là data gốc tổ trưởng nhập 2 giờ/lần |
| JSON Google | Đường dẫn file JSON service account | Chia sẻ quyền Viewer cho `client_email` trong JSON |
| Database QLCL | PostgreSQL `DATABASE_URL` của QLCL | TV3 dùng để đọc dữ liệu chất lượng |

Không cần link Dashboard riêng của từng tổ. `gid` trong link cũng không quyết định
tab được đọc; app dùng tên tab được khai báo trong `.env`.

## Vùng cần điền trong `.env`

Tìm hai vùng được đánh dấu trong `.env.example`:

```text
VÙNG A — ĐỔI MÃ XÍ NGHIỆP KHI NHÂN RỘNG
VÙNG B — BẮT ĐẦU CẤU HÌNH NGUỒN CHUYỀN BỆT
```

Sau đó điền block dưới đây. Đây là cấu hình XN2 đang dùng làm mẫu:

```dotenv
# 1. Đơn vị: phải đổi đồng thời với tên tab phía dưới
QLCL_DON_VI=XN2

# 2. File JSON đã được cấp quyền đọc cả hai Google Sheets
FLAT_LINE_GOOGLE_SERVICE_ACCOUNT_FILE="secrets/credentials_m29.json"

# 3. LINK KẾ HOẠCH: file chứa Rải chuyền + tab XN2
FLAT_LINE_PLAN_SPREADSHEET_URL="https://docs.google.com/spreadsheets/d/1HvyqiIuV8gWXRpELT2UuSXoxNYYOuCCuC7ZtbfBBxK0/edit"
FLAT_LINE_PLAN_WORKSHEET="Rải chuyền"
FLAT_LINE_PLAN_RANGE="A2:M"
FLAT_LINE_FACTORY_WORKSHEET="XN2"
FLAT_LINE_FACTORY_RANGE="A1:AE"

# 4. LINK DATA GỐC: file chứa Data-U2
FLAT_LINE_DATA_SPREADSHEET_URL="https://docs.google.com/spreadsheets/d/1CwFMTCavyyPwakm8k83y0WrErDivfI6muzj1vJeYbyc/edit"
FLAT_LINE_DATA_WORKSHEET="Data-U2"
FLAT_LINE_DATA_RANGE="A1:BV"

# 5. Đồng bộ Sheet -> database app
FLAT_LINE_SYNC_ENABLED=true
FLAT_LINE_SYNC_INTERVAL_SECONDS=120

# 6. Kết nối read-only đến database của app QLCL
FLAT_LINE_QLCL_DATABASE_URL="postgresql://USER:PASSWORD@SERVER:5432/DATABASE"
```

Không commit `.env` hoặc JSON lên Git. Thư mục `secrets/` và các tên
`credentials*.json` đã được loại khỏi Git.

## Những giá trị cần đổi khi triển khai xí nghiệp khác

| Biến | XN2 mẫu | Ví dụ khi chuyển XN3 |
|---|---|---|
| `QLCL_DON_VI` | `XN2` | `XN3` |
| `FLAT_LINE_PLAN_SPREADSHEET_URL` | Link file kế hoạch XN2 | Link file kế hoạch XN3 |
| `FLAT_LINE_FACTORY_WORKSHEET` | `XN2` | `XN3` |
| `FLAT_LINE_DATA_SPREADSHEET_URL` | Link file data XN2 | Link file data XN3 |
| `FLAT_LINE_DATA_WORKSHEET` | `Data-U2` | `Data-U3` |
| `FLAT_LINE_GOOGLE_SERVICE_ACCOUNT_FILE` | JSON XN2 đang dùng | JSON được cấp quyền ở XN mới |
| `FLAT_LINE_QLCL_DATABASE_URL` | Database QLCL hiện tại | Database QLCL của môi trường mới |

Các range chỉ giữ nguyên khi cấu trúc file mới giống mẫu:

- `Rải chuyền`: tiêu đề tại hàng 2, phạm vi `A2:M`.
- Tab xí nghiệp: bảng PO/EHD và tên sáu cụm nằm trong `A1:AE`.
- `Data-Ux`: tiêu đề hàng 1, `BP = Quy đổi sản lượng`, `BV = Nhu cầu mẹ`, phạm vi `A1:BV`.

Nếu một trong ba cấu trúc trên thay đổi, cần chỉnh range hoặc logic ánh xạ trước
khi bật đồng bộ.

## Cấp quyền Google Sheets

1. Mở file JSON và lấy giá trị `client_email`.
2. Mở cả file kế hoạch và file data gốc trên Google Sheets.
3. Share hai file cho email đó với quyền **Viewer**.
4. Đặt JSON vào `secrets/` trên máy chạy app.

## Kiểm tra sau triển khai

1. Khởi động lại app để nạp `.env` và chạy đồng bộ đầu tiên.
2. Mở `/tv/api/plans/lines`; tổ chuyền bệt phải xuất hiện trong danh sách.
3. Mở `/tv`, chọn tổ; nhu cầu mẹ chuyền bệt phải có tiền tố **(B)**.
4. Chọn ngày và bấm **Áp dụng**; cả TV1–TV4 phải tải được.
5. Kiểm tra chân màn hình có ngày báo cáo và mốc mới nhất, ví dụ
   `Báo cáo 12/09/2026 · Sau 16H30`.

Muốn cập nhật ngay mà không chờ chu kỳ tự động, bấm **Sync ngay · Chuyền bệt**
trong khối cấu hình tại `/tv`. Nút hiển thị thời điểm đồng bộ gần nhất và tự tải
lại danh sách kế hoạch sau khi hoàn tất.

## Trao đổi sản lượng và lỗi với QLCL

Mỗi lượt sync thành công từ Sheet sẽ gửi toàn bộ sản lượng theo nhu cầu mẹ/ngày
và 5 mốc BP sang `QLCL_API_URL`, dùng `QLCL_API_KEY` như luồng chuyền treo.
Số sửa giảm, số 0, mốc chưa nhập và ngày đã xóa trên nguồn được cập nhật lại;
gửi nhiều lần không cộng dồn sản lượng. Trạng thái gửi QLCL xuất hiện cạnh nút Sync.

QLCL cần triển khai cả `flat_output.py`, thay đổi trong `main.py` và
`templates/qc_input_sp.html` ở dự án QLCL. Khởi động lại QLCL để tự tạo bảng
`public.qc_flat_output`, sau đó khởi động lại hanging app và bấm Sync ngay.
Endpoint nhận là `POST /api/qc/flat-output/push`.

`QLCL_API_KEY` bắt buộc có giá trị và giống nhau trong `.env` của hai app.
QLCL phiên bản phân quyền mới từ chối API push nếu key trống; TV chuyền treo
cũng gửi key này khi đọc QC. Không đưa key vào Git hoặc mã JavaScript.

## Nâng cấp production sau khi pull

Dừng app/service và backup database ứng dụng trước khi nâng cấp. Giữ nguyên
`.env` production, bổ sung các biến ở trên và chép JSON đã cấp quyền vào máy chạy.
Pull QLCL, cài `requirements.txt` và khởi động lại QLCL trước hanging app.

Với hanging app đã có migration 001–012, chạy PowerShell tại thư mục repo:

```powershell
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw 'Pull failed' }
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Install failed' }
.\.venv\Scripts\python.exe scripts/apply_migrations.py --from-version 13 --to-version 16
if ($LASTEXITCODE -ne 0) { throw 'Migration failed; do not start app' }
.\run.ps1 -BindHost 0.0.0.0
```

Kiểm tra `git remote -v`: thay `origin` bằng `github` nếu remote GitHub tên là
`github`. Nếu đã chạy migration 015, có thể dùng `--from-version 16 --to-version 16`.
Không dùng `run.ps1 -Migrate` để nâng cấp: migration 006 chạy lại sẽ xóa và nạp lại
bảng lộ trình. Nếu app chạy bằng service, khởi động lại service thay dòng `run.ps1`.

Sau khởi động, mở `/tv`, bấm **Sync ngay · Chuyền bệt** và kiểm tra cả trạng thái
Sheet lẫn gửi QLCL. Migration 016 tạo `app.tFlatSheetSnapshot`; dữ liệu và `.env`
của máy phát triển không tự chuyển qua production khi pull Git.

## Đối chiếu dữ liệu QLCL

Kế hoạch mẹ phải được sync ở QLCL bằng chức năng Chuyền bệt, với
`source_system=flat_line_sheet` và `source_record_id=<XN>:<Nhu cầu mẹ>`.
Trạng thái gửi sẽ báo số nhu cầu chưa khai báo nếu chưa tìm được kế hoạch.

Trang nhập QC tự lấy BP của đúng ngày, ẩn nút cộng sản lượng đạt thủ công.
Tỷ lệ lỗi của chuyền bệt = số sản phẩm lỗi / BP × 100; BP bằng 0 hoặc chưa có
thì không đánh giá tỷ lệ. QLCL đọc lại sản lượng mỗi 30 giây và sau khi lưu lỗi.
TV3 đọc lỗi từ QLCL qua kết nối chỉ đọc `FLAT_LINE_QLCL_DATABASE_URL`;
phân mốc theo giờ ghi sản phẩm lỗi tại Việt Nam. Nhiều mã lỗi trên cùng một
sản phẩm không làm tăng số sản phẩm lỗi trong mốc. Ngày hiển thị trên TV là
ngày báo cáo thực tế ở chân màn hình.

Trạm QC dùng cho ra chuyền bệt là **Trạm cuối chuyền** (`station`). Tổng lỗi,
lỗi theo mốc, phân tích bộ phận/mã lỗi và cảnh báo trên TV3 chỉ lấy trạm này.
QLCL dùng cùng bộ lọc khi tính tỷ lệ lỗi theo BP; lỗi các trạm khác không cộng
vào chỉ số ra chuyền.

Nếu không gửi được QLCL, dữ liệu Sheet đã lưu vẫn phục vụ TV; lượt sync tiếp
theo sẽ gửi lại. Khi triển khai nhiều XN, mỗi app gửi dữ liệu của đúng đơn vị
đã cấu hình để tránh thay thế dữ liệu giữa các xí nghiệp.

Nếu Google Sheets tạm lỗi, TV tiếp tục dùng snapshot hợp lệ gần nhất trong
database. Thông tin lỗi đồng bộ được gắn ở phần cập nhật dưới chân màn hình.
