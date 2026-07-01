# Tasks: Forum Intelligence v1

## Phase 1 — Database & Repo
- [x] **T1.1** `db/migrations/004_forum_intelligence.sql`
- [x] **T1.2** `app/repositories/forum_repo.py`

## Phase 2 — Ingest
- [x] **T2.1** `app/services/forum_ingest_service.py`
- [x] **T2.2** `POST /forum/picks`, `GET /forum/picks/{date}`

## Phase 3 — Expert & Recommendations
- [x] **T3.1** `app/data/expert_weights.json`
- [x] **T3.2** `app/services/expert_scorer.py`
- [x] **T3.3** `app/services/forum_recommendation_service.py`
- [x] **T3.4** `GET /forum/experts/live`, `GET /forum/recommendations`
- [x] **T3.5** Chuyển `/forum/recommendations` sang **forum-only** (bỏ engine hybrid)

## Phase 4 — Integration
- [x] **T4.1** Mount `forum.router` in `main.py`
- [x] **T4.2** `xsmb_daily_report.py --source api`
- [x] **T4.3** Migration script `scripts/apply_migration.py` + smoke test
- [x] **T4.4** Extension sync full `CollectSession` (not summary only)

## Phase 5 — Backtest & Weights
- [x] **T5.1** `app/services/expert_backtest_service.py`
- [x] **T5.2** `scripts/backtest_expert_picks.py`
- [x] **T5.3** `GET /forum/experts/weights`, `/experts/backtest`, `POST /experts/weights/refresh`

## Phase 6 — Extension Đề xuất (cross-repo)
- [x] **T6.1** `extension/src/lib/recommendations-api.ts`
- [x] **T6.2** Popup tab Đề xuất (forum-only UI)
- [x] **T6.3** API fallback ports + `APP_PORT=18715` default

## Follow-up (chưa làm)
- [x] **T7.1** `de_cham` trong forum-only `de_top_4` + `de_cham_leaders` response
- [ ] **T7.2** Auto backtest refresh weights sau finalize (scheduler hook)
- [x] **T7.3** Dọn `compute_hybrid_*` khỏi `forum_recommendation_service.py`
- [x] **T7.4** Align `.env.example` + README (`APP_PORT=18715`)
- [x] **T7.5** `xsmb_daily_report.py --mode forum`
