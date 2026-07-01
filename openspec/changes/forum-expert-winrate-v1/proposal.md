# Proposal: Forum Expert Win Rate v1

## WHY

Tab **Đề xuất** hiển thị cột **Hiệu suất** nhưng luôn `—` vì:

1. `expert_performance()` tính **runtime** từ `forum_user_picks` + `draw_repo` — không có bảng DB riêng
2. DB hiện **0 pick tháng 6/2026** trong `forum_user_picks` (chỉ có KQXS: ~28 ngày)
3. Backtest `GET /forum/experts/backtest` trả `users: {}` → không seed được hiệu suất

Cần pipeline **lưu win rate chính xác vào Postgres**, seed từ **data tháng 6/2026**, và API/extension đọc từ DB thay vì tính tạm mỗi request.

## WHAT

| Thành phần | Mô tả |
|------------|-------|
| Migration `005_expert_win_rates.sql` | Bảng `expert_win_rates` + `expert_pick_results` (audit) |
| `expert_winrate_service.py` | Tính hit/total/win_rate, upsert DB, đọc cache |
| `scripts/backfill_forum_picks_month.py` | Crawl + ingest picks theo tháng (bắt đầu `2026-06`) |
| `scripts/seed_expert_win_rates.py` | Tính & ghi win rate từ picks + KQXS đã có |
| API | `GET /forum/experts/performance`, cập nhật `live_experts.performance` đọc DB |
| Alias | Gộp `LOKHATA 1789` → `nhcsxh` **trước** khi aggregate |

**Ngoài scope v1:**
- Tự crawl Bảng Vàng
- Real-time refresh sau mỗi poll (hook scheduler — follow-up)
- Win rate theo từng số (chỉ theo `(username, pick_type)`)

## SUCCESS

1. Sau chạy backfill tháng 6: `forum_user_picks` có ≥1 row/ngày có quay (Mon–Sat, ~24 ngày)
2. `expert_win_rates` có rows với `period_label = '2026-06'`, `total ≥ 1` cho cao thủ đã chốt
3. `GET /forum/recommendations` → `live_experts[].performance.rate_pct` khác `null` khi đủ mẫu
4. Extension tab Đề xuất hiển thị `65.0% (13/20)` thay vì `—`
5. `GET /forum/experts/performance?period=2026-06` trả JSON đầy đủ để audit

## DEPENDENCIES

- `draw_repo.get_mb_ketqua(date)` — đã có KQXS tháng 6 (~28 ngày)
- `scripts/crawl_forum_picks.py` — thread ID tháng 6/2026 (mở rộng theo ngày)
- `app/data/expert_aliases.json` — alias tài khoản
- `forum_ingest_service.ingest_collect_session()` — ingest chuẩn
