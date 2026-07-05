# Proposal: Forum Collect → Score Pipeline v1

## WHY

Luồng nghiệp vụ đã được thiết kế tách **Thu thập** (input) và **Kết quả** (so KQXS với input), nhưng thực tế vận hành ngày **2026-07-04** cho thấy tab Kết quả **thiếu user trúng** dù forum có bài chốt hợp lệ.

**Triệu chứng đã verify:**

| User | Pick (forum) | Trúng | Tab Kết quả |
|------|--------------|-------|-------------|
| Duong145 | STL 55,87 (page 3) | Lô 55 + 87 | Không có |
| Tornado6789 | BTL 87 (page 7) | BTL 87 | Không có |
| 36QueToi | STL 27.72 (page 9) | Lô 27 | Có nhưng chỉ đề 52 (miss) |

**Nguyên nhân gốc (không phải logic chấm):**

1. **Collector backfill chưa xong** — thread `thao_luan` dừng ở `lowest_page_fetched: 8`, thiếu pages 1–7; session chỉ giữ ~35 post cuối thread.
2. **Finalize sớm** — poll dừng lúc 18:30 trong khi `backfill_complete: false`.
3. **Parser thiếu format** — `STL : 27.72`, `4 số : 14,41,78,87` không extract.
4. **Parser đọc quote** — reply quote BTL/đề người khác → false positive nếu ingest nhầm.
5. **Tab Kết quả không báo độ phủ** — user tưởng đã chấm đủ forum.

**Mục tiêu v1:** Hoàn thiện pipeline end-to-end để **mọi pick hợp lệ trong cửa sổ collect** được thu thập → ingest → chấm → hiển thị; tab Kết quả phản ánh đúng phạm vi đã thu thập.

## WHAT

| # | Thành phần | Mô tả |
|---|------------|-------|
| 1 | **Backfill đủ trang** | Tiếp tục crawl ngược đến page 1 hoặc post cũ hơn cửa sổ; refresh `last_page` khi thread tăng trang |
| 2 | **Finalize có điều kiện** | Không finalize/sync “đóng băng” khi `backfill_complete=false` (trừ timeout an toàn) |
| 3 | **Parser bổ sung** | Dot separator STL; `4 số` / `To bộ`; bỏ quote block |
| 4 | **Ingest ↔ Score contract** | Sync → `forum_user_picks` → `run_daily_settlement`; idempotent re-chấm |
| 5 | **Coverage metadata** | Session + API + UI báo % thread đã backfill, post count, `backfill_complete` |
| 6 | **Score tab minh bạch** | Hiển thị nguồn pick = DB từ Thu thập; cảnh báo nếu coverage thấp |
| 7 | **Audit script** | So thread forum vs `forum_user_picks` vs score — phát hiện winner thiếu |

**Ngoài scope v1:**

- Tab Kết quả tự crawl forum (giữ mô hình input từ Thu thập)
- Real-time crawl mọi trang mỗi lần mở Kết quả
- Chấm pick sau 18:00 ICT
- Win-rate / recommendation scoring (đã có v2/v3)

## SUCCESS

1. Re-poll + sync ngày `2026-07-04`: Duong145 STL, Tornado6789 BTL, 36QueToi STL xuất hiện tab Kết quả với `hit=true` đúng KQXS.
2. Thread 17 trang: `backfill_complete=true` trước finalize (hoặc UI cảnh báo rõ nếu timeout).
3. Parser: `STL : 27.72` → `['27','72']`; `4 số : 14,41,78,87` → pick đề phù hợp; quote-only post → `picks: {}`.
4. `GET /forum/score` trả thêm `coverage` (posts ingested, threads incomplete).
5. Extension tab Thu thập hiển thị trạng thái backfill từng thread; tab Kết quả hiển thị hint coverage.
6. `scripts/audit_collect_score.py` exit 0 cho ngày audit hoặc liệt kê gap có post_id.

## DEPENDENCIES

- `forum-intelligence-v1` — ingest API, `forum_user_picks`
- `extension/forum-collector-v1` — collector, score tab baseline
- `forum-expert-winrate-v2` — `pick_hit`, settlement

## RELATED

- `extension/openspec/changes/forum-collector-v1/specs/score-tab/`
- `extension/openspec/changes/forum-collector-v1/specs/collection-window/`
- `openspec/changes/forum-intelligence-v1/specs/forum-ingest/`
- Audit thực tế: thread `thao-luan-du-doan-xsmb-thu-7-ngay-04-7-2026.101405`
