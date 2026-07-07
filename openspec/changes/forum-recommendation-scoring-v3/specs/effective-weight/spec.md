# Spec: Effective Weight

## ADDED Requirements

### REQ-EW-001: `expert_effective_weight()`

`app/services/expert_scorer.py` SHALL expose:

```python
def expert_effective_weight(
    username: str,
    pick_type: str,
    *,
    mode: str = "blend",
    period_label: str | None = None,
) -> float
```

- `mode` ∈ `{weight, measured, blend}`
- `period_label` default từ `DEFAULT_PERIOD_LABEL` (`rolling_90d`)
- Return value SHALL be in `[0.0, 1.0]` (clamp)

**Scenario: mode=weight**
- GIVEN `expert_weight("T98", "stl") == 0.95`
- WHEN `expert_effective_weight("T98", "stl", mode="weight")`
- THEN return `0.95`

**Scenario: mode=blend, no measured data**
- GIVEN `expert_weight("nhcsxh", "btl") == 1.0`
- AND `expert_performance("nhcsxh", "btl", "rolling_90d")` is `null`
- WHEN `expert_effective_weight("nhcsxh", "btl", mode="blend")`
- THEN return `≤ 1.0 × EXPERT_BLEND_PRIOR` (default `0.35`)
- AND return `< 1.0` (không full manual W)

**Scenario: mode=blend, low sample**
- GIVEN perf `{"hits": 1, "total": 1}`
- WHEN `expert_effective_weight(..., mode="blend")`
- THEN return `< expert_weight(...)` (Wilson shrinkage)

**Scenario: mode=blend, adequate sample**
- GIVEN `himle79` `dan_40s` perf `7/13`, `w_manual=0.94`
- WHEN `expert_effective_weight("himle79", "dan_40s", mode="blend")`
- THEN return `> 0.3` AND `< 0.94`

---

### REQ-EW-002: Wilson lower bound

`wilson_lower(hits, total, z=EXPERT_WILSON_Z)` SHALL be a pure function in `expert_scorer` or `expert_pick_eval`.

| hits/total | wilson_lower (z=1) ≈ |
|------------|----------------------|
| 0/0 | `0.5` (prior) |
| 1/1 | `< 0.25` |
| 7/13 | `0.30 – 0.40` |
| 17/18 | `> 0.80` |

Unit tests SHALL assert bounds, monotonicity (`hits↑ → wilson↑` at fixed total).

---

### REQ-EW-003: Sample ramp

```python
ramp = min(1.0, total / MIN_SAMPLE)  # MIN_SAMPLE default 5
```

- `total = 0` or `perf is null` → `ramp = 0`
- `total = MIN_SAMPLE` → `ramp = 1.0`
- Linear between

---

### REQ-EW-004: measured mode

```python
effective = wilson_lower(hits, total) * ramp + DEFAULT_UNKNOWN * (1 - ramp)
```

Khi `perf is null`: return `DEFAULT_UNKNOWN` (0.3).

**Scenario: measured ignores manual W**
- GIVEN `nhcsxh` `w_manual=1.0`, perf `1/2`
- WHEN `mode="measured"`
- THEN effective ≈ `wilson(1,2) × ramp` << 1.0

---

### REQ-EW-005: blend mode (default)

```python
measured_factor = wilson_lower(hits, total) if perf else 0.5
blend_factor = BLEND_PRIOR + (1 - BLEND_PRIOR) * measured_factor * ramp
effective = w_manual * blend_factor
```

- `BLEND_PRIOR` default `0.35` (env `EXPERT_BLEND_PRIOR`)
- Khi `ramp=0`: `effective = w_manual × BLEND_PRIOR`

**Scenario: nhcsxh gate**
- GIVEN no perf in period, `w_manual=1.0`
- THEN `effective == 0.35` (not 1.0)

---

### REQ-EW-006: Pick type isolation

`expert_effective_weight(user, "stl")` SHALL use `expert_performance(user, "stl", period)` — không borrow dan family row có `total` cao hơn.

Reuse `expert_performance()` lookup chain (first-match, v2).

---

### REQ-EW-007: Canonical username

Mọi lookup SHALL qua `canonical_username()` trước DB/JSON.

---

### REQ-EW-008: Win rate cao ≠ top hiệu lực (blend)

Thứ hạng bảng cao thủ mặc định sort `effective_weight` desc, **không** sort `rate_pct` thuần.

**Scenario: Qtv1 BTL 75% (3/4) không lên top**
- GIVEN `expert_weight("Qtv1", "btl") == 0.53`
- AND `expert_performance("Qtv1", "btl", "rolling_90d")` = `3/4` (75%)
- AND `expert_weight("nhcsxh", "btl") == 1.0` với perf `2/3` (67%)
- WHEN sort `live_experts` mode `blend`
- THEN `nhcsxh.effective_weight` > `Qtv1.effective_weight`
- BECAUSE `effective = w_manual × blend_factor` và Wilson lower bound + `ramp` (total < MIN_SAMPLE) giảm measured contribution

User sort `performance` → Qtv1 lên theo % trúng loại pick tương ứng.
