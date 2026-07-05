# Tasks: Forum Recommendation Scoring v3

## Phase 1 — Core effective weight
- [ ] **T1.1** `wilson_lower()` in `expert_scorer.py` or `expert_pick_eval.py`
- [ ] **T1.2** `expert_effective_weight()` — modes weight/measured/blend
- [ ] **T1.3** Env config: `EXPERT_SCORING_MODE`, `EXPERT_MIN_SAMPLE`, `EXPERT_BLEND_PRIOR`, `EXPERT_WILSON_Z`
- [ ] **T1.4** `tests/test_effective_weight.py` — Wilson bounds, gate, nhcsxh/himle79 cases

## Phase 2 — Period rolling default
- [ ] **T2.1** `DEFAULT_PERIOD_LABEL = rolling_90d` (+ env `EXPERT_PERF_PERIOD`)
- [ ] **T2.2** Verify `forum_schedule` refreshes `rolling_90d` post-settlement
- [ ] **T2.3** Re-seed `rolling_90d` after deploy
- [ ] **T2.4** Update `PERIOD_DISPLAY_LABELS` for dynamic YYYY-MM

## Phase 3 — Recommendation scoring
- [ ] **T3.1** `_scoring_w()` helper in `forum_recommendation_service.py`
- [ ] **T3.2** Wire `_aggregate_loto_scores`, `_aggregate_loto_consensus`, `_best_btl`
- [ ] **T3.3** Wire `_de_top4`, `_de_cham_leaders`, `_collect_dan_board`, `_forum_confidence`
- [ ] **T3.4** Response: `scoring_mode`, `scoring_period`, `effective_weight` on expert rows
- [ ] **T3.5** Router: query `scoring_mode`, `performance_period` validation
- [ ] **T3.6** `tests/test_reco_scoring_blend.py` — blend vs weight parity

## Phase 4 — Audit & scripts
- [ ] **T4.1** `scripts/audit_reco_scoring.py`
- [ ] **T4.2** Run audit top 10 users `weight` vs `blend` — document deltas
- [ ] **T4.3** Update `scripts/audit_expert_winrate.py` note scoring separate

## Phase 5 — Extension UI
- [ ] **T5.1** `recommendations-api.ts` types + query `scoring_mode`
- [ ] **T5.2** `popup.ts` — mode toggle, Eff. column, sort effective
- [ ] **T5.3** Legend v3 text
- [ ] **T5.4** `storage.ts` — `reco_scoring_mode` persistence
- [ ] **T5.5** Build extension + manual smoke test

## Phase 6 — Docs
- [ ] **T6.1** Link proposal → v2 design (W vs Hiệu suất vs Effective)
- [ ] **T6.2** README snippet: env vars + scoring modes

## Verification

```bash
# Unit
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/test_effective_weight.py \
  tests/test_reco_scoring_blend.py \
  tests/test_expert_performance_lookup.py -q

# Seed rolling
PYTHONPATH=. .venv/bin/python scripts/seed_expert_win_rates.py --period rolling_90d

# Audit scoring
PYTHONPATH=. .venv/bin/python scripts/audit_reco_scoring.py \
  --target-date 2026-07-05 --users nhcsxh,himle79,Qtv1,T98 --modes weight,blend

# API compare modes
curl -s "http://127.0.0.1:18715/forum/recommendations?target_date=2026-07-05&scoring_mode=weight" \
  | jq '{btl: .picks.btl_lo, top: .forum_loto_top10[0]}'
curl -s "http://127.0.0.1:18715/forum/recommendations?target_date=2026-07-05&scoring_mode=blend" \
  | jq '{btl: .picks.btl_lo, top: .forum_loto_top10[0], mode: .scoring_mode}'

# Effective weight spot-check
PYTHONPATH=. .venv/bin/python -c "
from app.services.expert_scorer import expert_effective_weight, expert_weight
for u, pt in [('nhcsxh','btl'),('himle79','dan_40s'),('himle79','stl'),('T98','stl')]:
    print(u, pt, 'w=', expert_weight(u,pt), 'eff=', expert_effective_weight(u,pt,mode='blend'))
"
```

**Pass criteria:**
- `nhcsxh` `effective_weight(btl) < 0.5` khi perf `≤ 1/2` hoặc null
- `himle79` `effective_weight(stl) ≤ 0.15` (gate + unknown category)
- `scoring_mode=weight` API response scores khớp pre-v3 snapshot (hoặc documented diff)
- `scoring_mode=blend` `btl_lo` ≠ weight-only khi nhcsxh W=1 dominates weight mode
- Extension hiển thị 3 cột W / Hiệu suất / Eff. khi blend

## Rollout

1. Deploy backend v3 (default `blend` — behavior thay đổi ngay)
2. Extension update với toggle → user có thể quay `weight` nếu muốn cũ
3. Monitor `audit_reco_scoring.py` weekly top users

## Risk / mitigation

| Risk | Mitigation |
|------|------------|
| User quen top theo W | Default extension toggle `blend`; legend giải thích |
| `rolling_90d` sparse early month | `BLEND_PRIOR` giữ 35% manual; ramp |
| Performance regression | `scoring_mode=weight` preserved |
