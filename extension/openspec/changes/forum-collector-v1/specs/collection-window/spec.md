# Spec Delta: Collection Window

## ADDED Requirements

### REQ-CW-001: Target Date Resolution

Hệ thống SHALL xác định `target_date` (ngày quay XSMB) dựa trên thời điểm hiện tại và múi giờ cấu hình.

**Scenario: Sau 18:30 — target là ngày mai**
- GIVEN thời gian hiện tại là `2026-06-30 19:00` (Asia/Ho_Chi_Minh)
- WHEN `getTargetDate()` được gọi
- THEN `target_date` = `2026-07-01`

**Scenario: Trước 18:30 — target là hôm nay**
- GIVEN thời gian hiện tại là `2026-06-30 17:00` (Asia/Ho_Chi_Minh)
- WHEN `getTargetDate()` được gọi
- THEN `target_date` = `2026-06-30`

**Scenario: Chủ nhật — không collect**
- GIVEN `target_date` rơi vào Chủ nhật
- WHEN scheduler kiểm tra
- THEN collect bị skip AND popup hiển thị "XSMB nghỉ Chủ nhật"

---

### REQ-CW-002: Collection Window

Cửa sổ collect cho `target_date` D SHALL là **[18:30 ngày D−1, 18:00 ngày D]** (inclusive start, exclusive end của poll sau 18:00).

**Scenario: Post trong cửa sổ được ghi nhận**
- GIVEN `target_date` = `2026-07-01`
- AND post có `posted_at` = `2026-06-30 20:15` ICT
- WHEN post được ingest
- THEN post được lưu vào session `2026-07-01`

**Scenario: Post trước cửa sổ bị bỏ qua**
- GIVEN `target_date` = `2026-07-01`
- AND post có `posted_at` = `2026-06-30 18:00` ICT
- WHEN post được ingest
- THEN post bị discard (trước `collect_start` 18:30)

**Scenario: Post sau 18:00 ngày D bị bỏ qua**
- GIVEN `target_date` = `2026-07-01`
- AND post có `posted_at` = `2026-07-01 18:05` ICT
- WHEN post được ingest
- THEN post bị discard (sau `collect_end`)

---

### REQ-CW-003: Draw Finalize

Lúc **18:15 ngày D**, hệ thống SHALL finalize session: ngừng poll, đóng băng `summary`, đánh dấu `finalized_at`.

**Scenario: Finalize đúng giờ**
- GIVEN `target_date` = `2026-07-01`
- AND thời gian = `2026-07-01 18:15` ICT
- WHEN alarm trigger
- THEN `session.finalized_at` được set
- AND poll interval chuyển sang idle
- AND optional auto-sync JSON/API chạy nếu bật

**Scenario: Poll trước finalize**
- GIVEN trong cửa sổ collect, chưa đến 18:15
- WHEN alarm 5 phút trigger
- THEN extension tiếp tục fetch threads và merge posts mới

---

### REQ-CW-004: Timezone Configuration

User SHALL có thể đổi timezone trong settings (default `Asia/Ho_Chi_Minh`).

**Scenario: Override timezone**
- GIVEN user set timezone = `UTC`
- WHEN tính `collect_start` cho target `2026-07-01`
- THEN `collect_start` = `2026-06-30 18:30 UTC`
