# Spec Delta: Score Tab Completeness & Transparency

## ADDED Requirements

### REQ-SC-001: Nguồn Dữ Liệu Minh Bạch

Tab Kết quả SHALL hiển thị rõ pick được chấm từ dữ liệu Thu thập, không phải crawl trực tiếp forum.

**Scenario: Hint mặc định**
- GIVEN score đã load
- THEN hiển thị dòng: `Chấm {total} pick từ Thu thập ({post_count} post). Chỉ tính pick chốt trước 18:00 (ICT).`

---

### REQ-SC-002: Coverage Warning

Khi `coverage.threads` có entry `backfill_complete=false`, tab SHALL hiển thị cảnh báo vàng (không chặn xem kết quả).

**Scenario: Backfill chưa xong**
- GIVEN `thao_luan`: lowest=8, last=17, backfill_complete=false
- WHEN render tab Kết quả
- THEN hiển thị: `Thảo luận: đang backfill (8/17) — có thể thiếu pick đăng sớm.`
- AND link/gợi ý: `Bấm Poll ngay ở tab Thu thập rồi Chấm lại`

**Scenario: Đủ coverage**
- GIVEN mọi daily thread `backfill_complete=true`
- THEN không hiển thị cảnh báo

---

### REQ-SC-003: Chấm Lại Sau Sync

Nút **Chấm lại (mketqua)** SHALL gọi `POST /forum/score/run` và refresh bảng; SHALL không tự sync session.

**Scenario: Workflow đúng**
- GIVEN user vừa Poll + sync ở tab Thu thập
- WHEN bấm Chấm lại
- THEN hits cập nhật theo `forum_user_picks` mới nhất

---

### REQ-SC-004: Collect Tab Backfill Status

Tab Thu thập SHALL hiển thị trạng thái backfill per thread (REQ-CB-005).

**Scenario: User kiểm tra trước khi tin Kết quả**
- GIVEN backfill chưa xong
- WHEN user mở tab Thu thập
- THEN thấy tiến độ trang trước khi sang tab Kết quả

---

### REQ-SC-005: Không Hiển Thị Quote Picks

Sau REQ-PP-003, score tab SHALL NOT show hits từ post chỉ quote người khác (e.g. congtush150i BTL 87 từ quote Tornado).

**Scenario: Reply không thành pick**
- GIVEN post reply parse ra `picks: {}`
- WHEN ingest + score
- THEN user reply không có row trong bảng Kết quả

---

## MODIFIED Requirements

### REQ-ST-001: Tab Kết quả (mở rộng)

Bổ sung:
- `coverage` hint (REQ-SC-002)
- `post_count` từ API
- Giữ `getLatestDrawScoreDate`, cutoff 18:00, TRÚNG/trượt

**Scenario: Chưa chấm**
- THEN message + gợi ý sync Thu thập trước nếu `post_count=0`
