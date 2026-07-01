# Proposal: Forum Intelligence v1

## WHY

Chrome extension **Forum Collector** đã poll thành công picks từ forumketqua.net (mở bát, thảo luận, chăn nuôi). Data cần pipeline để lưu, chấm cao thủ và đề xuất số.

Cần backend để:
1. **Nhận & lưu** session từ extension (`POST /forum/picks`)
2. **Đánh giá cao thủ** — trọng số theo track record + pick hôm nay
3. **Đề xuất số** — **chỉ từ cao thủ chốt** (forum-only, không dùng engine)

Logic hybrid Engine+Forum vẫn tồn tại trong `scripts/xsmb_daily_report.py` (CLI báo cáo hàng ngày), tách biệt với API `/forum/recommendations`.

## WHAT

Module **Forum Intelligence** trên FastAPI (`analysis-rbk-py`):

| API | Mô tả |
|-----|-------|
| `POST /forum/picks` | Ingest full `CollectSession` từ extension |
| `GET /forum/picks/{date}` | Lấy session đã lưu |
| `GET /forum/experts/live` | Cao thủ đang chốt hôm nay + weight |
| `GET /forum/recommendations` | Đề xuất lô/đề **forum-only** |
| `GET /forum/experts/weights` | Trọng số cao thủ hiện tại |
| `GET /forum/experts/backtest` | Backtest pick vs KQ XSMB |
| `POST /forum/experts/weights/refresh` | Gợi ý / ghi weights (blend backtest) |

**Phạm vi v1 (đã ship):**
- Postgres: `forum_sessions`, `forum_user_picks`
- Expert weights từ `app/data/expert_weights.json` (seed từ track record)
- Recommendation = tổng hợp trọng số cao thủ (STL/BTL/dàn đề)
- `xsmb_daily_report.py --source api` đọc forum session từ API
- Extension popup tab **Đề xuất** gọi `GET /forum/recommendations`
- Backtest CLI: `scripts/backtest_expert_picks.py`

**Ngoài scope v1:**
- Crawl Bảng Vàng tự động
- Hybrid recommendations qua API (giữ trong daily report script)
- Auto-refresh weights sau mỗi sync (chưa hook scheduler)

## SUCCESS

1. Extension `auto_sync` → `POST /forum/picks` (full session) → DB có data ngày D
2. `GET /forum/recommendations?target_date=D` trả picks + `forum_loto_top10` + `live_experts`
3. `GET /forum/experts/live` liệt kê user đã chốt + weight
4. Extension tab Đề xuất hiển thị picks forum-only (không engine)
5. `xsmb_daily_report.py --source api` chạy không cần crawl
