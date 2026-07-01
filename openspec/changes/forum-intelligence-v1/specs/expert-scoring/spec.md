# Spec Delta: Expert Scoring

## ADDED Requirements

### REQ-ES-001: Expert Weights

Hệ thống SHALL load weights từ `app/data/expert_weights.json` (cached, `reload_weights()` sau ghi file).

`weight(username, pick_type)`:
- Lookup `pick_type` key (`stl`, `btl`, `dan_de`, `de_cham`, `default`)
- Unknown user → `0.3`

**Scenario: T98 STL**
- GIVEN `T98` có `{"stl": 0.95, "default": 0.95}`
- WHEN `weight("T98", "stl")`
- THEN `0.95`

---

### REQ-ES-002: Live Experts

`GET /forum/experts/live?target_date=D` SHALL return users đã chốt trong session D:

```json
{
  "target_date": "2026-07-01",
  "experts": [
    {
      "user": "T98",
      "pick_type": "stl",
      "numbers": ["68", "86"],
      "weight": 0.95,
      "posted_at": "..."
    }
  ],
  "count": 1
}
```

Sorted by `weight` desc.

**Scenario: Chưa có session**
- THEN HTTP 404 `no forum data for date`

---

### REQ-ES-003: Weights API

`GET /forum/experts/weights` SHALL return `{"weights": {...}}` — nội dung `expert_weights.json`.

---

### REQ-ES-004: Backtest

`GET /forum/experts/backtest?days=90` SHALL compare `forum_user_picks` vs MB draw results.

Per `(username, pick_type)`:
```json
{
  "hits": 8,
  "total": 10,
  "rate": 0.8,
  "suggested_weight": 0.8
}
```

Hit rules:
- `stl`, `btl`, `muc_lo`: any number ∈ draw `kqAr`
- `dan_de`: đề (last 2 of `kq0`) ∈ numbers
- `de_cham`: đuôi đề ∈ cham digits

`POST /forum/experts/weights/refresh?days=90&blend=0.35&dry_run=true`:
- `dry_run=true` (default): trả `suggested` + `backtest`, không ghi file
- `dry_run=false`: ghi `expert_weights.json` và `reload_weights()`

CLI: `scripts/backtest_expert_picks.py [--write] [--days N]`
