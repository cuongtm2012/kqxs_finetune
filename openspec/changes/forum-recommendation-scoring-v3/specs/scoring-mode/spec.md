# Spec: Scoring Mode API

## ADDED Requirements

### REQ-SM-001: Query parameter

`GET /forum/recommendations` SHALL accept:

| Param | Default | Values |
|-------|---------|--------|
| `scoring_mode` | env `EXPERT_SCORING_MODE` or `blend` | `weight`, `measured`, `blend` |
| `performance_period` | env `EXPERT_PERF_PERIOD` or `rolling_90d` | `rolling_90d`, `YYYY-MM` |

Invalid `scoring_mode` → `422` với message rõ.

**Scenario: backward compat**
- WHEN `scoring_mode=weight`
- THEN `forum_loto_top10[].score` khớp implementation v2 (±0.001)

---

### REQ-SM-002: Response metadata

Response SHALL include:

```json
{
  "scoring_mode": "blend",
  "scoring_period": "rolling_90d",
  "scoring_period_label": "90 ngày gần nhất",
  "performance_period": "rolling_90d",
  "performance_period_label": "90 ngày gần nhất"
}
```

`scoring_period` và `performance_period` SHALL cùng giá trị khi client không override riêng.

---

### REQ-SM-003: `effective_weight` on expert rows

`live_experts[]`, `dan_board[]`, `de_by_expert[]` SHALL include:

```json
{
  "user": "himle79",
  "pick_type": "dan_40s",
  "weight": 0.94,
  "effective_weight": 0.55,
  "performance": {"hits": 7, "total": 13, "rate_pct": 53.8}
}
```

Rules:
- `weight` = `expert_weight()` — **không đổi**
- `effective_weight` = `expert_effective_weight(..., mode=scoring_mode)`
- Khi `scoring_mode=weight`: `effective_weight` MAY equal `weight` hoặc omit (extension treats missing as `weight`)

`de_cham_leaders[]` SHALL add `effective_weight` alongside `weight`.

---

### REQ-SM-004: Loto top10 score semantics

`forum_loto_top10[].score` và `consensus.loto_top10[].weight_sum` SHALL reflect scoring mode:

| Mode | `score` / `weight_sum` |
|------|------------------------|
| `weight` | Σ `expert_weight` |
| `blend` / `measured` | Σ `expert_effective_weight` |

`reasons[]` text không đổi (vẫn list username).

---

### REQ-SM-005: POST refresh không đổi weights JSON

`POST /forum/experts/performance/refresh` và scoring v3 SHALL NOT mutate `expert_weights.json`.

Measured data chỉ đọc từ `expert_win_rates`.

---

### REQ-SM-006: Experts performance endpoint

`GET /forum/experts/performance?period=rolling_90d` — không đổi schema v2.

Optional future: `?include_effective=true` — **ngoài scope v3** (effective chỉ trên recommendations).
