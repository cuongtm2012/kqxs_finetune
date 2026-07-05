# Spec Delta: Backtest Alignment

## MODIFIED Requirements

### REQ-ES-004: Backtest (v2)

`GET /forum/experts/backtest?days=90` và `expert_backtest_service.run_backtest()` SHALL dùng **cùng** logic aggregate với `expert_winrate_service.compute_period_stats`:

1. Load `forum_user_picks` trong window `days`
2. Group theo `target_date`
3. Per day: `canonical_username` + dedupe latest `posted_at` per `(user, pick_type)`
4. Skip ngày không có `draw_repo.get_mb_ketqua`
5. `pick_hit(pick_type, numbers, ketqua)` — rules không đổi

**Scenario: Alias không double-count**
- GIVEN cùng ngày `LOKHATA 1789` và `nhcsxh` chốt BTL
- WHEN `run_backtest(90)`
- THEN chỉ 1 evaluation cho canonical `nhcsxh`

**Scenario: Hai post cùng user/type/ngày**
- GIVEN user post BTL 10:00 và 15:00 cùng ngày
- WHEN dedupe
- THEN chỉ evaluate bản `posted_at` mới hơn

**Scenario: Consistency với rolling_90d**
- GIVEN `seed_expert_win_rates --period rolling_90d` sau backfill đủ
- WHEN compare `run_backtest(90).users` vs `GET /forum/experts/performance?period=rolling_90d`
- THEN `hits`, `total`, `rate` khớp cho mọi `(user, pick_type)` có `total > 0`

---

## ADDED Requirements

### REQ-BA-001: Shared module

Logic dedupe + aggregate SHALL live in `app/services/expert_pick_eval.py` (hoặc tên tương đương) và được import bởi:

- `expert_winrate_service`
- `expert_backtest_service`

Không duplicate implementation.

**Scenario: Unit test**
- GIVEN fixture 2 picks cùng user/type/ngày
- WHEN `dedupe_picks_for_eval`
- THEN output length = 1

---

### REQ-BA-002: Backtest endpoint source priority

`GET /forum/experts/backtest` giữ priority v1:

1. `expert_win_rates` period `rolling_90d` nếu `row_count > 0` → `"source": "db"`
2. Else `run_backtest(days)` → `"source": "live"`

Sau v2 seed `rolling_90d`, endpoint SHOULD trả `"source": "db"` trong môi trường production.

**Scenario: Production**
- GIVEN `rolling_90d` seeded
- THEN response includes `"source": "db"` và không recompute full scan mỗi request (đọc snapshot)

---

### REQ-BA-003: Audit script

`scripts/audit_expert_winrate.py` SHALL compare per `(user, pick_type)`:

| Column | Source |
|--------|--------|
| json_weight | `expert_weights.json` |
| db_hits/total | `expert_win_rates` |
| backtest_hits/total | `run_backtest(90)` |
| track_record | optional parse `xsmb_cao_thu_trackrecord.md` |

Exit code 1 nếu `db` vs `backtest` mismatch hits/total khi cùng period window.

**Scenario: CI smoke**
- `audit_expert_winrate.py --users nhcsxh --period 2026-06` → exit 0
