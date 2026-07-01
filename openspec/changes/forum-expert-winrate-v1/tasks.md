# Tasks: Forum Expert Win Rate v1

## Phase 1 — Database
- [x] **T1.1** `db/migrations/005_expert_win_rates.sql` — `expert_win_rates`, `expert_pick_results`
- [x] **T1.2** `app/repositories/expert_winrate_repo.py`

## Phase 2 — Compute service
- [x] **T2.1** `app/services/expert_winrate_service.py`
- [x] **T2.2** Canonical username + per-day dedupe + `pick_hit()`
- [x] **T2.3** `expert_scorer.expert_performance()` đọc DB trước

## Phase 3 — June backfill
- [x] **T3.1** `scripts/backfill_forum_picks_month.py` — `--month 2026-06`
- [x] **T3.2** `app/services/forum_crawl_service.py` — thread tháng 6 + daily discover
- [x] **T3.3** Cửa sổ 18:30 D−1 → 18:00 D ICT
- [x] **T3.4** `--dry-run`, `--skip-existing`
- [x] **T3.5** Chạy backfill tháng 6 (5 ngày có posts, 229 pick rows — cần mở rộng discover ngày 1–21)

## Phase 4 — Seed win rates
- [x] **T4.1** `scripts/seed_expert_win_rates.py`
- [x] **T4.2** Seed `2026-06` → 127 rows `expert_win_rates`
- [ ] **T4.3** Spot-check 5 ngày audit (manual)

## Phase 5 — API & UI
- [x] **T5.1** `GET /forum/experts/performance?period=2026-06`
- [x] **T5.2** `POST /forum/experts/performance/refresh`
- [x] **T5.3** `live_experts.performance` từ DB
- [ ] **T5.4** Extension verify Hiệu suất sau reload API

## Phase 6 — Docs
- [ ] **T6.1** README section backfill + seed
- [ ] **T6.2** Mở rộng backfill discover thread ngày 1–21/6

## Verification checklist (tháng 6)

```bash
# 1. Migration
PYTHONPATH=. .venv/bin/python scripts/apply_migration.py

# 2. Backfill picks
PYTHONPATH=. .venv/bin/python scripts/backfill_forum_picks_month.py --month 2026-06 --dry-run
PYTHONPATH=. .venv/bin/python scripts/backfill_forum_picks_month.py --month 2026-06

# 3. Seed win rates
PYTHONPATH=. .venv/bin/python scripts/seed_expert_win_rates.py --period 2026-06 --write-pick-results

# 4. API
curl "http://localhost:18715/forum/experts/performance?period=2026-06" | jq '.row_count'
curl "http://localhost:18715/forum/recommendations?target_date=2026-07-01" | jq '.live_experts[0].performance'
```

**Pass criteria:**
- `row_count` ≥ 15
- Extension Hiệu suất ≠ `—` cho ≥3 cao thủ có `total ≥ 3`
