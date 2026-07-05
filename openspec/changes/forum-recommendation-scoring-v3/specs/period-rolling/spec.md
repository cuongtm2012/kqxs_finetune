# Spec: Rolling Period Default

## MODIFIED Requirements

### REQ-RP-001: Default period

`expert_winrate_service.DEFAULT_PERIOD_LABEL` SHALL default to `rolling_90d`.

Override order:
1. Query `performance_period` on recommendations API
2. Env `EXPERT_PERF_PERIOD`
3. `rolling_90d`

Calendar month (`2026-06`) SHALL remain supported for audit/backfill scripts.

**Scenario: July active user**
- GIVEN `Qtv1` có BTL picks tháng 7, không có tháng 6
- WHEN `GET /forum/recommendations` (default period)
- THEN `expert_performance("Qtv1", "btl")` reflects July-inclusive 90d window
- AND `effective_weight` uses same period

---

### REQ-RP-002: Period display labels

```python
PERIOD_DISPLAY_LABELS = {
    "rolling_90d": "90 ngày gần nhất",
    "2026-06": "Tháng 6/2026",
    # YYYY-MM → "Tháng M/YYYY"
}
```

Extension legend SHALL use `scoring_period_label` from API.

---

### REQ-RP-003: Auto-refresh rolling_90d

Sau daily settlement / ingest (existing `forum_schedule` hook v2):

1. `refresh_period("rolling_90d")` — purge + recompute
2. Log `rows_upserted`

Cron failure SHALL NOT block recommendations API (stale rolling data OK ≤24h).

**Scenario: post-ingest**
- WHEN extension ingest completes for `target_date=D`
- AND settlement runs for `D-1`
- THEN `rolling_90d` `computed_at` within 1h of settlement

---

### REQ-RP-004: Calendar month purge (giữ v2)

`refresh_period("2026-06")` SHALL `delete_period` before upsert (v2 behavior retained).

Scripts `seed_expert_win_rates.py --period 2026-06` vẫn dùng cho audit cố định.

---

### REQ-RP-005: No backtest fallback for calendar period

Giữ quy tắc v2: `expert_performance(..., "2026-06")` không fallback `run_backtest(90)`.

`rolling_90d` MAY fallback backtest khi DB row missing (optional — document in implementation; prefer re-seed).
