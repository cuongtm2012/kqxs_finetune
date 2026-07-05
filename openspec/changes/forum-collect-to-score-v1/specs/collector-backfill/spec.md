# Spec Delta: Collector Backfill Completeness

## ADDED Requirements

### REQ-CB-001: Refresh Last Page Mỗi Cycle

Collector SHALL re-parse `last_page` từ HTML mỗi lần `crawlThreadPage`, không chỉ dựa vào cache cũ.

**Scenario: Thread tăng trang sau giờ quay**
- GIVEN thread có 10 trang lúc poll đầu
- AND sau 19:00 forum thêm post → thread thành 17 trang
- WHEN poll cycle chạy
- THEN `last_page_fetched` cập nhật thành 17
- AND page 17 được fetch trong cycle đó

---

### REQ-CB-002: Backfill Ngược Đến Đủ

Với thread daily (`thao_luan`, `mo_bat`), collector SHALL tiếp tục backfill từ `lowest_page_fetched - 1` xuống cho đến khi `backfill_complete=true`.

**Scenario: Hoàn tất khi chạm page 1**
- GIVEN `lowest_page_fetched` = 2 sau cycle trước
- WHEN backfill cycle fetch page 1
- THEN `lowest_page_fetched` = 1
- AND `backfill_complete` = true

**Scenario: Hoàn tất sớm — post ngoài cửa sổ**
- GIVEN `collect_window_start` = `2026-07-03 18:30` ICT
- AND page 4 có `min(posted_at)` = `2026-07-03 12:00` ICT
- WHEN backfill fetch page 4
- THEN `backfill_complete` = true
- AND không bắt buộc fetch pages 1–3

**Scenario: Audit 04/07 — pick page 3 và 7**
- GIVEN thread `thao-luan-du-doan-xsmb-thu-7-ngay-04-7-2026.101405`
- AND post `3919403` (page 3), `3919872` (page 7) trong cửa sổ collect
- WHEN backfill hoàn tất và sync
- THEN cả hai `post_id` có trong `session.posts`

---

### REQ-CB-003: Giới Hạn Trang Mỗi Cycle

Collector SHALL giới hạn số trang fetch mỗi cycle (`MAX_PAGES_PER_CYCLE`, default 25) để tránh rate limit; cycle sau tiếp tục từ `lowest_page_fetched`.

**Scenario: Thread 17 trang — nhiều cycle**
- GIVEN `last_page` = 17, `lowest_page_fetched` = 17 (mới bắt đầu)
- AND `MAX_PAGES_PER_CYCLE` = 25
- WHEN một cycle hoàn tất
- THEN có thể đạt `backfill_complete` trong một cycle
- AND nếu chưa xong, cycle kế `lowest_page_fetched` giảm tiếp

**Scenario: Force poll**
- GIVEN user bấm "Poll ngay" / `force: true`
- THEN `MAX_PAGES_PER_CYCLE` = 999 (hoặc tương đương)
- AND `backfill_complete` reset false để crawl lại đầy đủ

---

### REQ-CB-004: Finalize Gate

Collector SHALL NOT finalize session khi còn daily thread `backfill_complete=false`, trừ khi quá `BACKFILL_FINALIZE_GRACE_MS` sau 18:30 ICT.

**Scenario: Defer finalize để backfill**
- GIVEN 18:30 ICT, `thao_luan.backfill_complete` = false
- WHEN `shouldFinalize` = true
- THEN session KHÔNG set `finalized_at`
- AND `collect_status` = `backfilling`
- AND poll tiếp tục ưu tiên backfill

**Scenario: Grace timeout**
- GIVEN 19:00 ICT (30 phút sau 18:30)
- AND vẫn `backfill_complete` = false
- WHEN finalize gate kiểm tra
- THEN finalize được phép
- AND session metadata `coverage_warning` = true

---

### REQ-CB-005: Runtime Status Backfill

`patchRuntimeStatus` SHALL expose backfill progress cho popup.

**Scenario: Hiển thị tiến độ**
- GIVEN `thao_luan`: `lowest_page_fetched`=8, `last_page_fetched`=17
- WHEN popup render tab Thu thập
- THEN hiển thị `thao_luan: 8/17 ↓` hoặc tương đương

**Scenario: Hoàn tất**
- GIVEN `backfill_complete` = true
- THEN hiển thị `✓ đủ` cho thread đó

---

## MODIFIED Requirements

### REQ-CW-003: Draw Finalize (mở rộng)

Finalize lúc 18:30 ICT SHALL chỉ chạy khi REQ-CB-004 thỏa (backfill gate), không chỉ dựa vào thời gian.

**Scenario: Finalize sau backfill**
- GIVEN 18:35 ICT và mọi daily thread `backfill_complete` = true
- WHEN alarm trigger
- THEN `finalized_at` set
- AND auto-sync nếu bật
