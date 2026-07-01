# Design: Forum Intelligence v1

## Architecture

```
extension (finalize 18:15)
    │ POST /forum/picks (full CollectSession)
    ▼
app/routers/forum.py
    ├── forum_ingest_service.py   → normalize picks, dedupe latest/user/type
    └── forum_repo.py             → forum_sessions, forum_user_picks

app/services/
    ├── expert_scorer.py          → weight(user, pick_type) from JSON
    ├── expert_backtest_service.py → pick vs draw, suggest weights
    └── forum_recommendation_service.py
            ├── build_recommendations()  → forum-only (v1.1)
            └── compute_hybrid_*()       → giữ cho tái sử dụng / daily report

extension popup (tab Đề xuất)
    └── recommendations-api.ts → GET /forum/recommendations (fetch trực tiếp)

scripts/xsmb_daily_report.py
    └── --source api | crawl — hybrid engine+forum (riêng API recommendations)
scripts/backtest_expert_picks.py
    └── CLI backtest + optional --write weights
```

## Database

```sql
forum_sessions (
  target_date DATE PK,
  window_start, window_end, finalized_at TIMESTAMPTZ,
  payload JSONB,          -- full CollectSession
  updated_at TIMESTAMPTZ
)

forum_user_picks (
  id BIGSERIAL PK,
  target_date DATE,
  username TEXT,
  pick_type TEXT,         -- stl|btl|de_cham|de_tong|de_dau|dan_de|muc_lo
  numbers TEXT[],
  forum TEXT,
  post_id TEXT,
  posted_at TIMESTAMPTZ,
  raw_excerpt TEXT,
  UNIQUE(target_date, username, pick_type)  -- latest only per user/type/day
)
```

## Ingest Rules

1. Nhận body = extension `CollectSession` (có `posts` dict + `summary`)
2. Với mỗi `(username, pick_type)`: giữ post **mới nhất** (`posted_at_ms` max)
3. Upsert `forum_sessions.payload` + replace `forum_user_picks` rows cho `target_date`

## Expert Scoring

`app/data/expert_weights.json`:

```json
{
  "LangThang1977": {"default": 1.0, "stl": 1.0},
  "T98": {"default": 0.95, "stl": 0.95},
  "himle79": {"default": 0.94, "dan_de": 0.94}
}
```

`weight(user, pick_type)` → lookup type-specific hoặc `default`. Unknown user → `0.3`.

**Weighted score** cho lô `n`:
```
score(n) = Σ weight(user)  for each user picking n (stl|btl|muc_lo)
```

## Forum-Only Recommendations (API)

`build_recommendations(target_date)` — **không** gọi `build_candidates`.

| Output | Logic |
|--------|-------|
| `btl_lo` | BTL cao thủ có weight cao nhất; fallback top lô weighted |
| `bao_lo_9` | Top 9 lô theo tổng weight cao thủ |
| `xien_2` | Ghép cặp từ top 6 lô weighted |
| `de_top_4` | Top 4 từ `dan_de` picks weighted; fallback `forum_summary.dan_de` |
| `forum_loto_top10` | `{loto, score, users[], types[], reasons[]}` |
| `live_experts` | Mọi pick đã chốt, sort weight desc |
| `confidence` | Hàm forum: `f(expert_count, avg_weight)` — không dùng engine |
| `source` | Luôn `"forum"` |

**Hybrid** (engine + forum bonus) chỉ trong `scripts/xsmb_daily_report.py` và các hàm `compute_hybrid_*` (không qua API).

## Backtest

`expert_backtest_service.py`:
- So `forum_user_picks` vs `draw_repo.get_mb_ketqua(date)`
- Hit rules: stl/btl/muc_lo → lô trong `kqAr`; dan_de → đề; de_cham → chạm đuôi đề
- `suggest_weights()` blend 35% backtest + 65% JSON cũ (≥3 picks/loại)

## Port

Default API `18715` (`app/config.py`). Override: `APP_PORT` env (không phải `PORT`).

Extension `host_permissions`: `localhost` + `127.0.0.1` cho `:18715` và `:8081` (fallback).

## Files

| File | Status |
|------|--------|
| `db/migrations/004_forum_intelligence.sql` | ✅ |
| `app/data/expert_weights.json` | ✅ |
| `app/repositories/forum_repo.py` | ✅ |
| `app/services/forum_ingest_service.py` | ✅ |
| `app/services/expert_scorer.py` | ✅ |
| `app/services/forum_recommendation_service.py` | ✅ forum-only API |
| `app/services/expert_backtest_service.py` | ✅ |
| `app/routers/forum.py` | ✅ |
| `app/main.py` | ✅ mount router |
| `scripts/xsmb_daily_report.py` | ✅ `--source api` |
| `scripts/backtest_expert_picks.py` | ✅ |
