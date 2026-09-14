# Nâng cấp từ bản 774d145 (database đã có migration 001–012)

Dừng app/service và backup database ứng dụng bằng SSMS trước khi nâng cấp. Giữ nguyên `.env` production. Chạy PowerShell tại thư mục project.

```powershell
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw 'Pull failed' }
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Install failed' }
.\.venv\Scripts\python.exe scripts/apply_migrations.py --from-version 13 --to-version 15
if ($LASTEXITCODE -ne 0) { throw 'Migration failed; do not start app' }
.\run.ps1 -BindHost 0.0.0.0
```

`origin` phải trỏ tới GitHub; kiểm tra `git remote -v`, thay bằng `github` nếu đó là tên remote trên máy này. Nếu chạy bằng Windows service/Task Scheduler, dùng cơ chế đó để khởi động thay cho dòng run.ps1. Không chạy thêm bản app song song.

Không dùng `run.ps1 -Migrate` cho đợt nâng cấp này: migration 006 chạy lại sẽ xoá và nạp lại bảng lộ trình. Lệnh có giới hạn phiên bản ở trên chỉ chạy 013–015. Không chạy setup_flat_line_demo.py trên production.

Sau khởi động, mở `/api/health`; Ctrl+F5 các màn hình. Trong Admin → Nhu cầu mẹ, khai báo luỹ kế chuyển tiếp khi cần; phần Theo dõi chuyền bệt cho phép chọn nhu cầu và thêm công đoạn. Admin → Phân bổ ngày cũ: khai báo tỷ lệ ngoài giờ. Admin → Tài khoản: tạo tổ trưởng Role=user, Unit=XN2, Dept đúng tổ. Admin → 6 cụm: chọn công đoạn có nhãn Chuyền bệt rồi lưu đủ 6 vị trí.

Tổ trưởng vào `/entry` để chọn Báo chuyền bệt hoặc Nguyên nhân/HĐKP. Kiểm tra báo số, sửa báo số, ngày cũ, nội dung TV-1 và sản lượng TV-2. Các giá trị cấu hình và báo cáo trên database dev không tự chuyển sang production bằng Git; cần khai báo giá trị thực tế trên production.
