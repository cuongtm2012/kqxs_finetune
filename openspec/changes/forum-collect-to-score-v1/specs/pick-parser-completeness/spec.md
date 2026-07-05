# Spec Delta: Pick Parser Completeness

## ADDED Requirements

### REQ-PP-001: STL Dot Separator

Parser SHALL chuẩn hóa `STL : A.B` (một dấu chấm giữa hai số 2 chữ số) thành hai số lô tách biệt.

**Scenario: 36QueToi format**
- GIVEN raw `04/07/2026 STL : 27.72 ĐB : 02,20,...`
- WHEN `parsePicksFromContent` / `parse_picks`
- THEN `stl: ['27', '72']`

**Scenario: Không nhầm số thập phân khác**
- GIVEN `STL : 27,72` (comma)
- THEN `stl: ['27', '72']` (hành vi cũ giữ nguyên)

---

### REQ-PP-002: Đề 4 Số / To Bộ

Parser SHALL extract pick đề từ pattern `4 số : N1,N2,N3,N4` và `1 số : N`.

**Scenario: Akaza03**
- GIVEN `4 số : 14,41,78,87` và `1 số : 14`
- WHEN parse
- THEN có pick type đề với numbers `['14','41','78','87']` (map vào `std_de` hoặc type đề chuẩn hiện có)
- AND `1 số : 14` → `btd_de: ['14']` hoặc tương đương

**Scenario: Chấm đề 87**
- GIVEN KQXS đề = `87`
- AND pick `4 số` chứa `87`
- WHEN `pick_hit` chạy
- THEN `hit=true` cho pick đề tương ứng

---

### REQ-PP-003: Strip Quote Blocks

Parser SHALL loại nội dung quote/reply trước khi extract pick.

**Scenario: Reply chúc mừng (page 10)**
- GIVEN `Tornado6789 nói: ↑ ... BTL :87 ... Click to expand`
- AND user reply là `congtush150i` (không có pick riêng)
- WHEN parse
- THEN `picks: {}` cho post reply

**Scenario: Post gốc vẫn parse**
- GIVEN post gốc `BTL :87` không nằm trong quote
- WHEN parse
- THEN `btl: ['87']`

---

### REQ-PP-004: Parity Extension ↔ Python

`extension/src/lib/pick-parser.ts` và `app/services/forum_crawl_service.py` SHALL cho cùng output với cùng `raw_content` cho các case REQ-PP-001–003.

**Scenario: Regression test**
- GIVEN fixture từ post `3920151`, `3920142`, `3920181`
- WHEN parse cả hai phía
- THEN JSON picks khớp nhau

---

### REQ-PP-005: Multi-Day Post (giữ fix DaiLoan)

Parser SHALL chỉ lấy section `Ngày DD/M` khớp `target_date` và BTL từ dòng BTL cuối section đó (hành vi đã fix — regression).

**Scenario: Không merge ngày khác**
- GIVEN post có `Ngày 04/7` và `Ngày 05/7` với BTL khác nhau
- WHEN parse cho thread ngày 04/7
- THEN chỉ picks ngày 04/7

---

## MODIFIED Requirements

### REQ-PE-001: Minimum Content Length (mở rộng)

Sau strip quote, nếu `raw.length < 15` post SHALL bị bỏ qua (không extract).

**Scenario: Quote-only post**
- GIVEN content chỉ còn quote 40 ký tự nhưng không có pick của author
- WHEN extract
- THEN post không tạo pick rows
