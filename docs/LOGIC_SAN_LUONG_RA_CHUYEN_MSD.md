# Logic tính "Sản lượng ra chuyền" trên MES (SQL Server `MSD`)

> **Mục đích tài liệu:** Mô tả chính xác, ở mức kỹ thuật, cách hệ thống Dashboard chuyền treo XN2 xác định **sản lượng ra chuyền** (hàng qua trạm chốt KCS/QC) từ database MES `MSD`. Dùng làm đặc tả cho bên IT xây công cụ **đối chiếu sản lượng MSD ↔ dữ liệu nhập Bravo8**.
>
> Nguồn: trích trực tiếp từ code đang chạy (`app/queries.py`, `app/admin.py`, `app/tv.py`).
> Mọi câu lệnh dưới đây chạy **chỉ đọc (read-only)** trên `MSD`.

---

## 1. Tóm tắt một dòng (Quy tắc vàng)

> **Sản lượng ra chuyền = `SUM(tRecentWork.Qty)`** của các bản ghi thoả **đồng thời**:
> ```
> tStation.StRole = 13   AND   tRecentWork.IsLastSeq = 1
> ```

- `StRole = 13` → **trạm chốt sản lượng** (trạm KCS/QC, trạm cuối dây chuyền). Đây là công đoạn đếm "hàng đã ra chuyền".
- `IsLastSeq = 1` → chỉ lấy **lần scan cuối cùng** của một sequence (chống đếm trùng khi một sản phẩm bị scan lại nhiều lần).

**Không bao giờ được bỏ một trong hai điều kiện này.** Đây là nguồn sự thật duy nhất cho sản lượng ra chuyền. Bỏ `StRole = 13` sẽ đếm cả các trạm giữa chuyền; bỏ `IsLastSeq = 1` sẽ nhân bội do scan lặp.

---

## 2. Bảng và cột sử dụng

Toàn bộ logic chỉ chạm **2 bảng** trong `MSD`:

### 2.1. `MSD.dbo.tRecentWork` (bí danh `rw`) — bảng giao dịch scan

| Cột | Kiểu (suy ra) | Ý nghĩa / vai trò trong công thức |
|---|---|---|
| `Station_guid` | GUID | **Khoá join** sang `tStation` để lấy `StRole`. |
| `IsLastSeq` | bit/int | **Điều kiện lọc bắt buộc** = 1 (lần scan cuối của sequence). |
| `Qty` | int | **Số lượng ra chuyền** — đại lượng được `SUM()`. |
| `DefectiveQty` | int | Số lượng lỗi phát hiện tại trạm chốt (dùng cho KPI chất lượng). |
| `MONo` | varchar | Mã lệnh sản xuất (Manufacturing Order). Khoá gộp chính; cũng để parse Tổ/Line. |
| `ShtDate` | date | **Ngày sản xuất (ngày ca làm)** — khoá gộp theo ngày. Dùng để lọc khoảng thời gian. |
| `BeginTime` | datetime | Thời điểm scan — dùng tách **giờ** và **slot ca**. |
| `SeqNo` | int | Số thứ tự sequence (dùng cho năng suất công nhân). |
| `SeqName` | varchar | Tên công đoạn/sequence. |
| `StyleNo` | varchar | Mã hàng (style). |
| `PONo` | varchar | Số PO. |
| `ColorNo` | varchar | Mã màu. |
| `SizeNo` | varchar | Mã cỡ. |
| `EmpID` / `EmpName` | varchar | Mã / tên công nhân (đếm số công nhân, năng suất). |
| `RealMinute` | numeric | Phút thực làm (tính hiệu suất). |
| `SAM` | numeric | SAM chuẩn công đoạn (tính hiệu suất). |

### 2.2. `MSD.dbo.tStation` (bí danh `st`) — danh mục trạm

| Cột | Ý nghĩa |
|---|---|
| `guid` | Khoá chính, join với `tRecentWork.Station_guid`. |
| `StRole` | **Vai trò trạm; = 13 là trạm chốt sản lượng (KCS).** |
| `StNo` | Số hiệu trạm. |
| `RailNo` | Số ray treo. |

### 2.3. Quan hệ join

```sql
FROM MSD.dbo.tRecentWork  rw
INNER JOIN MSD.dbo.tStation st
       ON rw.Station_guid = st.guid
```

> Trong code tên DB được viết qua sentinel `{MES_DB}` và thay bằng `MSD` lúc chạy (`db._expand`). Trong tài liệu này viết thẳng `MSD`.

---

## 3. Công thức chuẩn (canonical) — để đối chiếu

Đây là truy vấn **chuẩn, ít điều kiện nhất** mà bên IT nên dùng làm "con số MSD" khi đối chiếu với Bravo8. Nó khớp với hàm `api_plan_candidate_daily_output()` (`app/admin.py`) và `_output_kcs()` (`app/tv.py`).

### 3.1. Tổng sản lượng ra chuyền theo **MONo × Ngày**

```sql
SELECT
    rw.MONo                               AS MONo,
    CONVERT(varchar(10), rw.ShtDate, 120) AS ShtDate,   -- yyyy-mm-dd
    SUM(rw.Qty)                           AS SanLuongRaChuyen,
    SUM(rw.DefectiveQty)                  AS SoLuongLoi
FROM MSD.dbo.tRecentWork  rw
INNER JOIN MSD.dbo.tStation st
        ON rw.Station_guid = st.guid
WHERE st.StRole   = 13           -- trạm chốt KCS
  AND rw.IsLastSeq = 1           -- lần scan cuối của sequence
  AND CAST(rw.BeginTime AS DATE) = rw.ShtDate   -- xem mục 4
  AND rw.ShtDate BETWEEN ? AND ?                -- khoảng đối chiếu
GROUP BY rw.MONo, rw.ShtDate
ORDER BY rw.MONo, rw.ShtDate;
```

### 3.2. Tổng luỹ kế cho **1 MONo** (toàn kỳ hoặc đến 1 ngày)

```sql
SELECT ISNULL(SUM(rw.Qty), 0)          AS SanLuongRaChuyen,
       ISNULL(SUM(rw.DefectiveQty), 0) AS SoLuongLoi
FROM MSD.dbo.tRecentWork  rw
INNER JOIN MSD.dbo.tStation st
        ON rw.Station_guid = st.guid
WHERE rw.MONo    = ?
  AND st.StRole   = 13
  AND rw.IsLastSeq = 1
  AND CAST(rw.BeginTime AS DATE) = rw.ShtDate
  AND rw.ShtDate <= ?;     -- hoặc BETWEEN ? AND ?
```

> **`SUM(Qty)` chính là định nghĩa sản lượng ra chuyền.** Không dùng `COUNT(*)` ở mức tổng (xem cảnh báo mục 5 về năng suất công nhân).

---

## 4. Điều kiện bảo vệ ngày: `CAST(BeginTime AS DATE) = ShtDate`

Mọi truy vấn sản lượng cấp MONo và CTE `NormalizedWork` đều thêm:

```sql
AND CAST(rw.BeginTime AS DATE) = rw.ShtDate
```

- **Mục đích:** đảm bảo thời điểm scan (`BeginTime`) rơi đúng vào ngày ca được ghi nhận (`ShtDate`), loại các bản ghi scan lệch ngày (ví dụ ca đêm/điều chỉnh thủ công) khỏi phép đếm.
- **Khi đối chiếu với Bravo8:** nếu Bravo8 tính theo *ngày scan thực tế* thay vì *ngày ca*, hai bên có thể lệch ở các bản ghi quanh nửa đêm. Nên thống nhất trước **mốc ngày nào là chuẩn** (`ShtDate` = ngày ca là mốc Dashboard đang dùng).

---

## 5. ⚠️ Các biến thể dễ gây hiểu nhầm — KHÔNG dùng để đối chiếu tổng sản lượng

Trong hệ thống có vài chỗ đếm **khác** với công thức chuẩn, phục vụ mục đích riêng. Khi làm công cụ đối chiếu, **đừng lấy nhầm các con số này** làm "sản lượng ra chuyền":

### 5.1. Năng suất công nhân (`worker_productivity` trong `queries.py`)
- Gộp theo từng `SeqNo` rồi dùng `COUNT(*) AS qty_per_seq`, sau đó lấy `MAX(qty_per_seq)` cho mỗi (công nhân × trạm).
- Lý do: tránh nhân bội khi 1 trạm có nhiều `SeqNo` gộp. **Đây là sản lượng quy cho công nhân, KHÔNG phải tổng sản lượng ra chuyền.** Tổng ra chuyền luôn là `SUM(Qty)`.

### 5.2. Ứng viên kế hoạch (`api_plan_candidates` trong `admin.py`)
- Dùng `SUM(rw.Qty) > 0` nhưng **KHÔNG lọc `StRole = 13`** — chỉ để phát hiện "MONo đã có hoạt động sản xuất ở bất kỳ trạm nào". Không phải sản lượng ra chuyền.

### 5.3. Màn hình TV
- TV-1/TV-2 (`tv.py`) đếm `SUM(Qty)` theo giờ/slot ca với **đúng** filter vàng `StRole=13 AND IsLastSeq=1` → khớp công thức chuẩn, chỉ khác ở cách chia khung giờ.

---

## 6. Bối cảnh: "Tổ" và `MONo` (không ảnh hưởng con số tổng, chỉ ảnh hưởng nhóm)

Dashboard quy sản lượng về **Tổ (logical line)** bằng cách parse số tổ từ `MONo`. **Việc này chỉ phục vụ gom nhóm hiển thị, không thay đổi tổng `SUM(Qty)`.** Nếu công cụ đối chiếu làm ở cấp `MONo` thì **không cần** quan tâm bước parse này.

Các định dạng `MONo` gặp trong MES:

| Định dạng | Ví dụ | Tổ |
|---|---|---|
| Cũ, có "LINE" | `LINE 3 #324230-4` | 3 |
| Cũ, có "LINE" | `LINE; 6-#D093-6` | 6 |
| Mới, StyleNo-LineNo | `376556-5` | 5 |
| Mới, có `#` | `#D093-6` | 6 |
| Mới, lần 2 | `376556-5-2` | 5 |

- `plan_key` = phần chuỗi từ dấu `#` trở đi của `MONo` (ví dụ `#324230-4`).
- Trong CTE `NormalizedWork`, tổ được tách bằng `PATINDEX('%LINE%')` + lấy cụm số đầu tiên phía sau.
- Dashboard chỉ liệt kê Tổ `[1, 6]` (hardcode trong `list_lines()`); nếu đối chiếu toàn xưởng thì **bỏ qua** giới hạn này và đi theo `MONo`.

---

## 7. Mức độ gom (grain) có thể dùng khi đối chiếu

Cùng một bộ filter vàng, Dashboard gom ở các mức sau — IT chọn mức khớp với Bravo8:

| Mức gom | GROUP BY | Hàm | Dùng ở |
|---|---|---|---|
| MONo × Ngày | `MONo, ShtDate` | `SUM(Qty)` | `admin.daily-output` |
| MONo (luỹ kế) | `MONo` | `SUM(Qty)` | `tv._output_kcs` |
| Ngày × Tổ | `ShtDate, logical_line_no` | `SUM(Qty)` | `output_by_day` |
| Giờ | `DATEPART(HOUR, BeginTime)` | `SUM(Qty)` | `output_by_hour` |
| Slot ca (5 khung) | theo giờ scan | `SUM(Qty)` | `output_by_slot` |
| Kế hoạch × Màu × Cỡ | `plan_key, MONo, Color, Size,...` | `SUM(Qty)` | `output_by_plan` |

5 slot ca: `07:30–09:30`, `09:30–11:30`, `12:30–14:30`, `14:30–16:30`, `Sau 16:30`. (Thời gian làm chuẩn 492 phút/ngày.)

---

## 8. Mẫu truy vấn đối chiếu gợi ý cho IT

Ý tưởng: lấy số MSD theo công thức chuẩn ở cấp `MONo × Ngày`, rồi `FULL OUTER JOIN` với số Bravo8 cùng khoá, đánh dấu chênh lệch.

```sql
;WITH MES AS (
    SELECT
        rw.MONo,
        rw.ShtDate,
        SUM(rw.Qty)          AS Qty_MES,
        SUM(rw.DefectiveQty) AS Def_MES
    FROM MSD.dbo.tRecentWork  rw
    INNER JOIN MSD.dbo.tStation st
            ON rw.Station_guid = st.guid
    WHERE st.StRole   = 13
      AND rw.IsLastSeq = 1
      AND CAST(rw.BeginTime AS DATE) = rw.ShtDate
      AND rw.ShtDate BETWEEN @From AND @To
    GROUP BY rw.MONo, rw.ShtDate
)
SELECT
    COALESCE(m.MONo, b.MONo)       AS MONo,
    COALESCE(m.ShtDate, b.NgayNhap) AS Ngay,
    m.Qty_MES,
    b.Qty_Bravo,
    m.Qty_MES - b.Qty_Bravo        AS ChenhLech
FROM MES m
FULL OUTER JOIN <nguon_Bravo8> b
    ON  b.MONo    = m.MONo
    AND b.NgayNhap = m.ShtDate
WHERE ISNULL(m.Qty_MES, 0) <> ISNULL(b.Qty_Bravo, 0)   -- chỉ hiện dòng lệch
ORDER BY Ngay, MONo;
```

**Điểm cần thống nhất giữa 2 hệ trước khi đối chiếu:**
1. **Khoá ghép:** `MONo` của MES có tiền tố `LINE`/`#` — cần chuẩn hoá để map đúng mã lệnh Bravo8.
2. **Mốc ngày:** `ShtDate` (ngày ca) của MES vs ngày nhập/ghi nhận của Bravo8 (xem mục 4).
3. **Phạm vi trạm:** MES chỉ đếm trạm `StRole = 13`; cần chắc Bravo8 cũng chỉ ghi nhận "hàng ra chuyền", không phải bán thành phẩm giữa chuyền.
4. **Lỗi (`DefectiveQty`):** nếu Bravo8 ghi "sản lượng đạt = ra chuyền − lỗi" thì phải điều chỉnh cho đồng nhất; MES ở đây `Qty` và `DefectiveQty` là 2 cột tách biệt.

---

## 9. Ghi chú vận hành

- Kết nối MES dùng **Windows Authentication** (`Trusted_Connection=yes`), chỉ đọc, không user/password trong code.
- Tên DB nguồn cấu hình qua biến môi trường `HANGING_MES_DB` (mặc định `MSD`).
- Dữ liệu thực tế của xưởng bắt đầu từ `2026-04-18` (`PLAN_CANDIDATE_START_DATE`).
- Tham số luôn dùng placeholder `?` (parameterized), không nối chuỗi.
