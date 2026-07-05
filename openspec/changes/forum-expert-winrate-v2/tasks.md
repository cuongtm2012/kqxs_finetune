# Tasks: Forum Expert Win Rate v2

## Phase 1 — Shared eval module
- [x] **T1.1** `app/services/expert_pick_eval.py` — `dedupe_picks_for_eval`, `aggregate_hit_stats`
- [x] **T1.2** Refactor `expert_winrate_service.compute_period_stats` dùng shared module
- [x] **T1.3** Refactor `expert_backtest_service.run_backtest` dùng shared module
- [x] **T1.4** `tests/test_expert_pick_eval.py` — dedupe alias + per-day latest

## Phase 2 — Lookup & weight fixes
- [x] **T2.1** `expert_performance()` — dan family fallback chain (spec `performance-lookup`)
- [x] **T2.2** `expert_weight()` — chặn cross-category default (spec `weight-pick-type`)
- [x] **T2.3** `forum_recommendation_service._collect_dan_board` — performance theo `resolved` pick_type
- [x] **T2.4** `tests/test_expert_performance_lookup.py` — himle79 dan_40s vs dan_de
- [x] **T2.5** `tests/test_expert_weight_category.py` — himle79 stl → 0.3

## Phase 3 — Data backfill & seed
- [x] **T3.1** Mở rộng `backfill_forum_picks_month.py` — parse `Lần N` từ topic chăn nuôi + snap Chủ nhật → T7
- [x] **T3.2** Chạy backfill `--month 2026-06` (26/26 ngày, 2988 posts, 26 lan-days)
- [x] **T3.3** Re-seed `2026-06` + `rolling_90d`
- [x] **T3.4** himle79 `dan_40s` 7/13 (53.8%) — 13/18 lanz có dàn đủ parse; W=0.94 vẫn từ JSON thủ công

## Phase 4 — Audit & API
- [x] **T4.1** `scripts/audit_expert_winrate.py`
- [ ] **T4.2** Spot-check 5 ngày `expert_pick_results` vs manual (himle79 dan_40s)
- [x] **T4.3** Document period default trong API response (`performance_period` field)

## Phase 5 — Extension UI
- [x] **T5.1** Legend W vs Hiệu suất + period hint (spec `extension-ui`)
- [x] **T5.2** Toggle sort bảng cao thủ: W (default) | Hiệu suất
- [x] **T5.3** `dan_board` hiển thị perf khi có data

## Phase 6 — Docs
- [ ] **T6.1** README — backfill, seed, audit workflow
- [ ] **T6.2** Link từ `xsmb_cao_thu_trackrecord.md` → openspec v2

## Verification

```bash
# 1. Unit tests
PYTHONPATH=. .venv/bin/python -m pytest tests/test_expert_performance_lookup.py tests/test_expert_weight_category.py tests/test_expert_pick_eval.py -q

# 2. Backfill + seed
PYTHONPATH=. .venv/bin/python scripts/backfill_forum_picks_month.py --month 2026-06
PYTHONPATH=. .venv/bin/python scripts/seed_expert_win_rates.py --period 2026-06 --write-pick-results
PYTHONPATH=. .venv/bin/python scripts/seed_expert_win_rates.py --period rolling_90d

# 3. Audit
PYTHONPATH=. .venv/bin/python scripts/audit_expert_winrate.py --users himle79,Xuannd,Binhrau1 --period 2026-06

# 4. API
curl -s "http://127.0.0.1:18715/forum/experts/performance?period=2026-06" | jq '.users.himle79'
curl -s "http://127.0.0.1:18715/forum/recommendations?target_date=2026-07-04" | jq '[.dan_board[] | select(.user=="himle79") | .performance]'

# 5. Weight isolation
PYTHONPATH=. .venv/bin/python -c "from app.services.expert_scorer import expert_weight; print(expert_weight('himle79','stl'), expert_weight('himle79','dan_40s'))"
# Expected: 0.3, 0.94
```

**Pass criteria:**
- himle79 `dan_40s` DB rate_pct ≈ 94% ±2% (nếu đủ backfill) hoặc audit ghi rõ lý do lệch
- `expert_weight('himle79','stl') == 0.3`
- `dan_board[].performance` không null cho himle79 khi `total ≥ 3`
- `run_backtest(90)` hits/total khớp `rolling_90d` DB cho ≥10 user ngẫu nhiên
