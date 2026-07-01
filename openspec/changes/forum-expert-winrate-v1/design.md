# Design: Forum Expert Win Rate v1

## Vấn đề hiện tại

```
extension poll → forum_user_picks (chỉ ngày hiện tại)
                      ↓
expert_backtest_service.run_backtest()  ← tính mỗi request, không persist
                      ↓
expert_scorer.expert_performance()    ← cache 90d in-memory, thường rỗng
                      ↓
extension "Hiệu suất" → "—"
```

**Root cause:** thiếu (a) lịch sử pick tháng 6 trong DB, (b) bảng aggregate win rate.

## Kiến trúc mới

```
scripts/backfill_forum_picks_month.py  (--month 2026-06)
    │ crawl forumketqua (daily + chăn nuôi tháng 6)
    │ build CollectSession / pick rows per target_date
    ▼
forum_ingest_service.ingest_collect_session()
    ▼
forum_user_picks                    (per day, per user, per pick_type)

scripts/seed_expert_win_rates.py    (--period 2026-06)
    │ join draw_repo.get_mb_ketqua(D)
    │ canonical_username + dedupe_picks_by_user
    │ pick_hit() — cùng rules backtest hiện tại
    ▼
expert_pick_results                 (optional audit: 1 row / day / user / type)
expert_win_rates                    (aggregate: hits, total, win_rate)

expert_winrate_service.get_performance(user, pick_type, period)
    ▼
forum_recommendation_service / live_experts / extension UI
```

## Database

### `expert_win_rates` (aggregate — nguồn chính cho UI)

```sql
CREATE TABLE expert_win_rates (
    username      TEXT NOT NULL,
    pick_type     TEXT NOT NULL,
    period_label  TEXT NOT NULL,       -- '2026-06' | 'rolling_90d' | 'all_time'
    period_start  DATE NOT NULL,
    period_end    DATE NOT NULL,
    hits          INT NOT NULL DEFAULT 0,
    total         INT NOT NULL DEFAULT 0,
    win_rate      NUMERIC(7,4) NOT NULL,  -- hits::float / total, 4 decimal
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (username, pick_type, period_label)
);

CREATE INDEX idx_expert_win_rates_period ON expert_win_rates (period_label);
CREATE INDEX idx_expert_win_rates_user ON expert_win_rates (username);
```

**Ràng buộc:** `total = 0` → không insert. `win_rate = ROUND(hits::numeric / total, 4)`.

### `expert_pick_results` (audit — optional nhưng khuyến nghị)

```sql
CREATE TABLE expert_pick_results (
    target_date   DATE NOT NULL,
    username      TEXT NOT NULL,
    pick_type     TEXT NOT NULL,
    numbers       TEXT[] NOT NULL DEFAULT '{}',
    hit           BOOLEAN NOT NULL,
    draw_de       TEXT,
    evaluated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (target_date, username, pick_type)
);
```

Cho phép debug: *"ngày 15/6 nhcsxh BTL hit hay miss?"*

## Hit rules (giữ nguyên `expert_backtest_service.pick_hit`)

| pick_type | Hit khi |
|-----------|---------|
| `stl`, `btl`, `muc_lo` | ∃ số ∈ `numbers` nằm trong `kqAr` |
| `dan_de`, `dan_40s`, `dan_36s`, `dan_64s` | đề (`kq0` 2 số cuối) ∈ `numbers` |
| `de_cham` | đuôi đề ∈ `cham` |
| `de_tong` | tổng 2 số đề mod 10 ∈ picks |
| `de_dau` | đầu đề ∈ picks |

Chủ nhật: **không** tạo `target_date` (không quay XSMB).

## Canonical username

Trước mọi bước aggregate:

```python
from app.services.expert_scorer import canonical_username, dedupe_picks_by_user
user = canonical_username(raw_user)  # LOKHATA 1789 → nhcsxh
```

Per `(target_date, canonical_user, pick_type)`: giữ **một** pick (posted_at mới nhất) — tránh double-count.

## Period labels

| `period_label` | Ý nghĩa | `period_start` / `period_end` |
|----------------|---------|-------------------------------|
| `2026-06` | Benchmark seed tháng 6 | `2026-06-01` … `2026-06-30` |
| `rolling_90d` | Cửa sổ trượt 90 ngày | `today-90` … `today` |
| `all_time` | Toàn bộ picks trong DB | min/max `target_date` |

**UI mặc định:** `2026-06` cho đến khi đủ `rolling_90d` (≥30 ngày có pick + draw).

## Backfill tháng 6/2026

### Nguồn crawl

Tái sử dụng logic `scripts/crawl_forum_picks.py`:

| Forum | Thread (tháng 6/2026) |
|-------|------------------------|
| STL K2N | `nuoi-song-thu-lo-khung-2-ngay-thang-6-2026.101198` |
| BTL K3N | `topic-chan-nuoi-xsmb-btl-k3n-thang-6-2026.101208` |
| BTL K5N | `topic-chan-nuoi-xsmb-btl-k5n-thang-6-2026.101183` |
| Dàn 40s | `chan-dan-dac-biet-xsmb-40s-khung-4-thang-6-2026.101212` |
| Dàn 64s | `dan-dac-biet-xsmb-64s-thang-6-2026.101209` |
| Thảo luận ngày D | Discover từ listing hoặc `KNOWN_DAILY_IDS` (đã có 22–27/6) |
| Mở bát ngày D | Listing `khu-mo-bat.13` |

### Cửa sổ pick theo ngày D

Giống extension (`collection-window` spec):

- **Start:** `D-1 18:30` ICT  
- **End:** `D 18:00` ICT  

Chỉ ingest post có `posted_at` trong cửa sổ.

### Pipeline CLI

```bash
# 1. Backfill picks tháng 6
PYTHONPATH=. .venv/bin/python scripts/backfill_forum_picks_month.py \
  --month 2026-06 --dry-run
PYTHONPATH=. .venv/bin/python scripts/backfill_forum_picks_month.py \
  --month 2026-06

# 2. Tính & lưu win rate
PYTHONPATH=. .venv/bin/python scripts/seed_expert_win_rates.py \
  --period 2026-06 --write-pick-results

# 3. Verify
curl "http://localhost:18715/forum/experts/performance?period=2026-06"
```

### Kỳ vọng số liệu tháng 6

| Metric | Target |
|--------|--------|
| Ngày có pick ingested | ≥ 22 (Mon–Sat, trừ ngày forum chưa mở thread) |
| Rows `forum_user_picks` | ≥ 80 (ước ~4 pick/user/ngày × target users) |
| Rows `expert_win_rates` period `2026-06` | ≥ 15 `(user, pick_type)` |
| Ngày skip (no draw) | log rõ trong script output |

## Service API

### `expert_winrate_service.py`

```python
def compute_period_stats(period_start, period_end, period_label) -> dict
def upsert_win_rates(stats: dict, period_label, period_start, period_end) -> int
def get_performance(username, pick_type, period_label="2026-06") -> dict | None
def refresh_rolling_90d() -> int
```

### Router (`forum.py`)

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/forum/experts/performance?period=2026-06` | Toàn bộ bảng win rate kỳ |
| POST | `/forum/experts/performance/refresh?period=2026-06` | Recompute từ picks (admin/cron) |

### `expert_scorer.expert_performance()` — thay đổi

1. Đọc `expert_win_rates` (period `2026-06` hoặc query param)
2. Fallback `run_backtest()` in-memory nếu DB trống
3. Return `{hits, total, rate_pct}` — format extension đã có

## Files mới / sửa

| File | Action |
|------|--------|
| `db/migrations/005_expert_win_rates.sql` | NEW |
| `app/repositories/expert_winrate_repo.py` | NEW |
| `app/services/expert_winrate_service.py` | NEW |
| `app/services/expert_scorer.py` | READ from DB |
| `app/routers/forum.py` | +performance endpoints |
| `scripts/backfill_forum_picks_month.py` | NEW |
| `scripts/seed_expert_win_rates.py` | NEW |
| `scripts/crawl_forum_picks.py` | REFACTOR shared parsers (optional) |

## Rủi ro & giảm thiểu

| Rủi ro | Giảm thiểu |
|--------|------------|
| Thread tháng 6 đã khóa / URL đổi | Log skip; manual `KNOWN_DAILY_IDS` map |
| Pick parse sai → win rate lệch | `expert_pick_results` audit + spot-check 5 ngày |
| Alias chưa map | `expert_aliases.json` + test nhcsxh/LOKHATA |
| Chủ nhật trong range | Script skip + không tính hit |
