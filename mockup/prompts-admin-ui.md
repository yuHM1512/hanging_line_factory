# Prompts tạo Mockup UI — Admin Settings Pages

> Dùng với: **v0.dev**, **Claude Artifacts**, **Stitch (Figma)**, hoặc bất kỳ AI design tool nào.
> Mỗi prompt đã bao gồm đủ context nghiệp vụ + design system để tool tạo mockup sát thực tế.

---

## Shared Design Context (copy vào đầu mỗi prompt nếu tool không nhớ context)

```
DESIGN SYSTEM:
- Layout: Sidebar 280px (trái) + Main content area (phải). Desktop-only, min-width 1200px.
- Sidebar: White background with subtle blue gradient at top-left. Brand "Hanging Conveyor / Admin Setup" ở trên. Navigation links với active state = blue gradient pill. User card + logout ở dưới cùng.
- Colors: Primary = deep navy (#001848), Surface = white/off-white, Error = #b3261e, Success = #16a34a, Warning = #d97706. Material Design 3 tone.
- Typography: Manrope (headings), Inter (body), Roboto Mono (numeric data).
- Cards/Panels: White background, border-radius 1.25rem, subtle shadow (0 18px 48px rgba(21,28,40,0.05)).
- Tables: No borders, rows have light background (#f4f7fb), rounded first/last cells. Header = uppercase 0.75rem, muted color.
- Buttons: Primary = navy gradient, Danger = red, Tertiary = transparent with navy text. Rounded 0.8rem.
- Forms: Grid layout (auto-fit, minmax 220px), inputs have light bg, no border, rounded 0.8rem. Readonly = darker bg.
- Toast: Fixed bottom-right. Confirm modal: centered with backdrop blur.
- Language: Vietnamese UI labels. Technical terms in English where standard.
```

---

## Prompt 1: Trang Tổng quan (Admin Home + Setup Checklist)

```
Design a web admin dashboard home page for a Vietnamese garment factory's hanging conveyor system.

LAYOUT: Sidebar (280px, fixed left) + Main content area.

MAIN CONTENT has 2 sections:

1. SETUP CHECKLIST PANEL (top):
   - Title: "Checklist cài đặt"
   - 6 checklist items in a vertical list, each is a clickable row:
     • Tài khoản (3 bản ghi) — green checkmark icon
     • Lịch nghỉ (12 bản ghi) — green checkmark icon
     • Nhu cầu con (5 bản ghi) — green checkmark icon
     • Nhu cầu mẹ (2 bản ghi) — green checkmark icon
     • 6 cụm theo dõi (0) — yellow dash icon, text "Chưa có dữ liệu"
     • SAM (0) — yellow dash icon, text "Chưa có dữ liệu"
   - Each row: [circle icon 28px] [label bold] [count text right-aligned muted]
   - Done items: green bg icon. Pending: yellow bg icon. Error: red bg icon.

2. QUICK LINKS GRID (below checklist):
   - 6 cards in responsive grid (3 columns):
     • Lịch nghỉ — "Ngày lễ + ngày nghỉ riêng"
     • Nhu cầu con — "Khai báo kế hoạch con: tổ, mã, ngày lên chuyền"
     • Nhu cầu mẹ — "Đăng ký mã hàng + định mức + phân loại"
     • 6 cụm theo dõi — "Chọn 6 trạm/cụm cho TV-2"
     • SAM — "Đồng bộ thời gian SAM từ Google Sheet"
     • Tài khoản — "Quản lý tài khoản tổ trưởng / admin"
   - Cards: hover lift effect, heading in primary color.

SIDEBAR: Brand "Hanging Conveyor / Admin Setup", nav links (Tổng quan = active, Lịch nghỉ, Nhu cầu con, Nhu cầu mẹ, 6 cụm, SAM, Tài khoản), user card at bottom showing "Nguyễn Văn A · admin".

Style: Clean, professional, Material Design 3 inspired. White/light surfaces, deep navy primary, rounded corners (1.25rem), subtle shadows.
```

---

## Prompt 2: Trang Nhu cầu con (Plan / Child Demand)

```
Design a master data management page for "Nhu cầu con" (Child Production Plan) in a Vietnamese garment factory admin panel.

LAYOUT: Sidebar (280px) + Main. Page title: "Nhu cầu con (Kế hoạch con)" with subtitle explaining the page purpose.

THREE PANELS stacked vertically:

PANEL 1 — "Chọn MONo để khai báo" (Select production order):
- A "Tải lại" refresh button at top-right
- Data table with columns: MONo (full) | Số đơn hàng | Mã hàng | Tổ | [Chọn button]
- Show 4-5 sample rows with realistic Vietnamese garment data:
  • MONo like "MO-2026-0451-BL", Số đơn hàng "DH-2026-0451", StyleNo "ST-8842", Tổ "Tổ 3"
- Each row has a blue "Chọn" primary button
- Muted text state: "Đang tải..." when loading

PANEL 2 — "Khai báo Nhu cầu con" (form, initially hidden, shown after clicking Chọn):
- Grid form (3 columns) with fields:
  • MONo (readonly, gray bg)
  • Số đơn hàng (readonly)
  • Mã hàng (readonly)
  • Tổ (number input, editable)
  • Ngày lên chuyền (date picker)
  • SLKH - sản lượng (number)
  • Customer (text)
  • Ghi chú (full-width text)
- Sub-section: "PO List" with add/remove rows:
  • Each PO row: PONo (text) + Số lượng (number) + [X remove button]
  • "+ Thêm PO" button below
- Form actions: [Huỷ tertiary] [Lưu primary]
- Show inline validation: red border + error text "Bắt buộc nhập" under empty required field

PANEL 3 — "Đã khai báo" (registered plans table):
- Table columns: Số đơn hàng | Mã hàng | Tổ | Ngày bắt đầu | SLKH | Customer | Số PO | Hành động
- Action column: [Sửa] [Xoá red] buttons
- Show 3-4 sample rows
- Delete shows a modal overlay (not browser confirm): "Xoá kế hoạch này? PO list cũng sẽ xoá theo." with [Huỷ] [Xoá] buttons, backdrop blur

Style: Material Design 3, white panels with rounded corners, table rows with light background, no cell borders. Readonly fields visually distinct (darker background).
```

---

## Prompt 3: Trang Nhu cầu mẹ (Parent Demand)

```
Design a "Nhu cầu mẹ" (Parent Demand Registration) page for a garment factory admin panel.

LAYOUT: Sidebar + Main. Title: "Nhu cầu mẹ" with subtitle: "Chọn 1 Nhu cầu con (đã khai báo) làm mẹ. Tổ + Mã hàng auto-lấy từ con."

THREE PANELS:

PANEL 1 — "Chọn Nhu cầu con chưa có mẹ":
- Helper text: "List chỉ hiện các con chưa được gán mẹ. Tạo con trước ở trang Nhu cầu con." with link.
- Table: Số đơn hàng (bold, with MONo as small muted text below) | Mã hàng | Tổ | Ngày bắt đầu | SLKH | Customer | [Chọn làm mẹ] button
- 3-4 sample rows

PANEL 2 — Form "Đăng ký Nhu cầu mẹ" (togglable, also used for Edit mode):
- When in CREATE mode: title = "Đăng ký Nhu cầu mẹ", button = "Lưu Nhu cầu mẹ"
- When in EDIT mode: title = "Sửa Nhu cầu mẹ: DH-2026-0451", button = "Cập nhật"
- Grid form fields:
  • NhuCauMe (readonly) — auto from selected child
  • Mã hàng (readonly)
  • Tổ (readonly)
  • ĐMKT - định mức kỹ thuật (number, required, placeholder "VD: 10.5")
  • Phân loại ĐH (dropdown: Đặc biệt / Mới / Lặp lại / Vest)
  • LĐ biên chế (number, required, placeholder "VD: 65")
  • Ghi chú (full-width text, optional)
- Actions: [Huỷ] [Lưu/Cập nhật]
- Show both modes side by side or as toggle states

PANEL 3 — "Đã đăng ký" (registered list):
- Table: NhuCauMe | Mã | Tổ | SLKH (auto = Σ con) bold | Số con | ĐMKT | Phân loại | LĐ | Hành động
- Action: [Sửa] [Xoá] buttons per row
- Delete modal: "Xoá Nhu cầu mẹ 'DH-2026-0451'? Các con sẽ unlink." with backdrop

Style: Same design system. Emphasize the relationship flow: pick child → fill parent details → save.
```

---

## Prompt 4: Trang 6 cụm theo dõi (Cluster Station Config)

```
Design a "6 cụm theo dõi sản lượng" (6-Cluster Monitoring Config) page for a garment factory conveyor system.

CONTEXT: A hanging conveyor line has many stations. The admin picks 6 key checkpoints along the route to monitor on a TV dashboard: 1 input station + 4 middle stations + 1 final QC (KCS) station. Order must follow production flow (ascending).

LAYOUT: Sidebar + Main. Title: "6 cụm theo dõi sản lượng", subtitle explaining the 1+4+1 structure.

TWO PANELS:

PANEL 1 — "Danh sách Nhu cầu mẹ":
- Table: NhuCauMe | Mã hàng | Tổ | Trạng thái cấu hình | [Cấu hình] button
- Status column uses pills/badges:
  • "Đã đủ 6/6" = green pill
  • "3/6" = gray/neutral pill (partially configured)
  • "0/6" = gray pill (not started)
- 3-4 sample rows, mix of complete and incomplete

PANEL 2 — "Cấu hình 6 cụm cho [NhuCauMe]" (shown after clicking Cấu hình):
- Info line: "Route từ MONo MO-2026-0451 · 18 cụm có sẵn"
- 6 CLUSTER CARDS in a 3×2 grid:
  • Card 1: "Cụm 1 — Đầu vào" (special blue-tinted background)
    - Dropdown select with options like "Odr 2 · May thân trước (5 trạm)"
    - Below dropdown: "Trạm vật lý: ST-001, ST-002, ST-003" in muted small text
  • Cards 2-5: "Cụm 2-5 — Giữa" (neutral background)
    - Same dropdown + station hint pattern
  • Card 6: "Cụm 6 — KCS (cuối)" (special teal/green-tinted background)
    - Same pattern
  - Each card: rounded, light background, label uppercase small
  - Dropdowns show route step order + group label
- Actions below grid: [Đóng] [Lưu 6 cụm]
- Validation toast if not all 6 selected: "Cần chọn đủ 6 cụm."
- Validation toast if order wrong: "Cụm 3 (Odr 8) phải đứng SAU cụm 2 (Odr 5)."

VISUAL: The 6-card grid should feel like a pipeline/flow — consider adding subtle arrows or numbering to show the production order from card 1 → 6. Card 1 and 6 visually distinct (colored tint) to emphasize input/output roles.

Style: Material Design 3, same system as other pages.
```

---

## Prompt 5: Trang SAM (Standard Allowed Minutes)

```
Design a "SAM" (Standard Allowed Minutes) management page for a garment factory admin.

CONTEXT: SAM is the standard time to produce one garment, synced from a Google Sheet. Admin can sync all at once or manually edit individual records.

LAYOUT: Sidebar + Main. Title: "SAM", subtitle: "Đồng bộ thời gian SAM từ Google Sheet hoặc nhập tay."

TWO SECTIONS IN ONE PANEL:

TOP SECTION — Sync controls:
- Row with: Search input (filter by style code) + [Đồng bộ Google Sheet] primary button
- Below: status text "Lần sync gần nhất: 30/07/2026 14:22" in muted
- When syncing: button shows spinner + "Đang đồng bộ..."
- After sync: toast "Đã đồng bộ 45 mã hàng." with success color

BOTTOM SECTION — SAM table:
- Table columns: Mã hàng (StyleNo) | SAM (minutes, bold numeric) | Nguồn (pill: "Sheet" or "Thủ công") | Ngày cập nhật | Hành động
- Actions: [Sửa inline] [Xoá]
- Inline edit: clicking Sửa makes the SAM cell editable (number input appears in-place), with [✓ Save] [✗ Cancel] replacing the action buttons
- Show search filtering: when user types "ST-88" in search, table filters to matching rows
- 5-6 sample rows with realistic data

DELETE: Modal confirm "Xoá SAM của mã 'ST-8842'?" with [Huỷ] [Xoá]

Style: Same design system. Numeric SAM values should use monospace font (Roboto Mono). Emphasize the sync workflow as the primary action.
```

---

## Prompt 6: Trang Tài khoản (User Management)

```
Design a "Tài khoản" (User Account Management) page for a garment factory admin panel.

LAYOUT: Sidebar + Main. Title: "Tài khoản", subtitle: "Quản lý tài khoản tổ trưởng / admin. Đăng nhập bằng employee code."

TWO PANELS:

PANEL 1 — "Thêm tài khoản" (Add user form):
- Compact grid form (3 columns in one row):
  • Mã nhân viên (UserID, text input, required)
  • Tên hiển thị (DisplayName, text)
  • Vai trò (Role, dropdown: "admin" / "lead" / "viewer")
- [Thêm] primary button inline
- In EDIT mode: form title changes to "Sửa tài khoản: NV001", UserID readonly, button = "Cập nhật", extra [Huỷ] button

PANEL 2 — "Danh sách tài khoản":
- Table: Mã NV | Tên hiển thị | Vai trò (with colored badge) | Ngày tạo | Hành động
- Role badges: "admin" = navy pill, "lead" = blue pill, "viewer" = gray pill
- Actions: [Sửa] [Xoá]
- Show 4-5 sample rows
- Delete modal: "Xoá tài khoản NV001?"

Style: Same system. Keep it simple — this is the lightest page. Focus on clean table layout and quick inline editing.
```

---

## Prompt 7: Trang Lịch nghỉ (Holiday Calendar)

```
Design a "Lịch nghỉ" (Holiday/Off-day Calendar) page for a garment factory admin.

LAYOUT: Sidebar + Main. Title: "Lịch nghỉ", subtitle: "Ngày lễ + ngày nghỉ riêng của tổ. Dùng để tính ngày kết thúc kế hoạch dự kiến."

TWO PANELS:

PANEL 1 — "Thêm ngày nghỉ":
- Simple row form: Date picker + Ghi chú (text) + [Thêm] button
- Validation: duplicate date shows inline error

PANEL 2 — "Danh sách ngày nghỉ":
- Table: Ngày | Thứ (auto-calculated, e.g. "Thứ 2") | Ghi chú | [Xoá] button
- Rows sorted by date ascending
- Show 8-10 sample rows mixing:
  • National holidays: "Quốc khánh 2/9", "Tết Dương lịch"
  • Factory-specific: "Nghỉ bù", "Team building"
- Past dates slightly muted, upcoming dates normal
- Optional enhancement: mini calendar view showing highlighted off-days

DELETE: Modal "Xoá ngày 02/09/2026?"

Style: Same system. This is a simple page — keep it clean and scannable. Consider a visual calendar widget alongside or instead of the table for better overview.
```

---

## Tips khi dùng prompt

1. **v0.dev**: Paste nguyên prompt, thêm "Use React + Tailwind CSS + shadcn/ui" ở đầu.
2. **Claude Artifacts**: Paste prompt + thêm "Create a React component mockup with sample data."
3. **Stitch (Figma)**: Paste prompt, Stitch sẽ tạo frame. Có thể cần chia nhỏ từng panel.
4. **Chỉnh sửa**: Sau khi có mockup, dùng follow-up prompt như:
   - "Make the table more compact"
   - "Add empty state illustration when no data"
   - "Show the edit mode of the form"
   - "Add loading skeleton animation"
