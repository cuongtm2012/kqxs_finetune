# Spec Delta: Expert Win Rate Storage

## ADDED Requirements

### REQ-WR-001: Schema `expert_win_rates`

Hệ thống SHALL persist aggregated win rate trong Postgres.

```sql
PRIMARY KEY (username, pick_type, period_label)
```

Columns bắt buộc: `hits`, `total`, `win_rate`, `period_start`, `period_end`, `computed_at`.

**Invariant:**
- `total > 0`
- `win_rate = hits / total` (4 chữ số thập phân)
- `username` = `canonical_username(username)` trước khi ghi

**Scenario: Upsert nhcsxh BTL tháng 6**
- GIVEN nhcsxh có 8 hit / 10 ngày BTL trong tháng 6
- WHEN `seed_expert_win_rates --period 2026-06`
- THEN row `(nhcsxh, btl, 2026-06)` có `hits=8`, `total=10`, `win_rate=0.8000`

---

### REQ-WR-002: Schema `expert_pick_results` (audit)

Hệ thống SHOULD lưu kết quả từng ngày để audit.

```sql
PRIMARY KEY (target_date, username, pick_type)
```

Columns: `numbers`, `hit` (boolean), `draw_de`, `evaluated_at`.

**Scenario: Trace miss**
- GIVEN ngày `2026-06-15`, user `T98`, pick_type `stl`, numbers `['68','86']`
- AND KQXS đề/lô không chứa 68 hay 86
- THEN `expert_pick_results.hit = false`

---

### REQ-WR-003: Hit evaluation

Win rate SHALL dùng **cùng** `pick_hit()` như `expert_backtest_service` — không định nghĩa rule mới.

**Scenario: STL hit**
- GIVEN `kqAr` chứa `35`
- AND pick `stl` numbers `['35','53']`
- THEN `hit = true`

**Scenario: Dàn đề hit**
- GIVEN `kq0` kết thúc `...47`
- AND `dan_40s` numbers chứa `47`
- THEN `hit = true`

---

### REQ-WR-004: Dedup trước aggregate

Trước khi tính win rate cho period:

1. Load `forum_user_picks` trong `[period_start, period_end]`
2. `dedupe_picks_by_user()` — alias + latest per `(user, pick_type)` **per day** (đã unique trong DB)
3. Skip row nếu `draw_repo.get_mb_ketqua(target_date)` = null

**Scenario: Alias không double-count**
- GIVEN `nhcsxh` và `LOKHATA 1789` cùng BTL ngày D
- WHEN compute period
- THEN chỉ 1 evaluation cho canonical `nhcsxh`

---

### REQ-WR-005: Period `2026-06` (seed)

Hệ thống SHALL hỗ trợ `period_label = '2026-06'`:
- `period_start = 2026-06-01`
- `period_end = 2026-06-30`
- Chỉ tính ngày có draw **và** có pick

**Scenario: Seed tháng 6**
- GIVEN `forum_user_picks` đã backfill tháng 6
- AND `draw_repo` có KQXS tháng 6
- WHEN `seed_expert_win_rates --period 2026-06`
- THEN `expert_win_rates` có ≥1 row với `period_label='2026-06'`

---

### REQ-WR-006: Minimum sample (hiển thị)

Extension/API SHALL trả `performance = null` khi `total < 1`.

Optional (khuyến nghị UI): hiển thị `*` khi `total < 3` (mẫu nhỏ).

**Scenario: Đủ mẫu**
- GIVEN `total = 5`, `hits = 3`
- WHEN `get_performance("T98", "stl", "2026-06")`
- THEN `{hits: 3, total: 5, rate_pct: 60.0}`

**Scenario: Chưa có data**
- GIVEN không có row trong `expert_win_rates`
- THEN `performance = null` (UI hiển thị `—`)

---

### REQ-WR-007: Rolling window `rolling_90d`

Hệ thống SHOULD hỗ trợ recompute `period_label = 'rolling_90d'` từ picks 90 ngày gần nhất (cron/manual).

**Scenario: Refresh rolling**
- WHEN `refresh_rolling_90d()` sau ngày có đủ 30+ ngày pick
- THEN upsert rows `rolling_90d` cho mọi `(user, pick_type)` có `total ≥ 1`
