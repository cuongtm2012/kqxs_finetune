# Design: Forum Recommendation Scoring v3

## Vấn đề (root cause)

```
expert_weights.json          expert_win_rates (rolling_90d)
        │                              │
        │ expert_weight()              │ expert_performance()
        ▼                              ▼
   SCORING đề xuất              HIỂN THỊ Hiệu suất
   (lô, BTL, đề top 4)          (cột audit, sort UI)
        │                              │
        └──────── KHÔNG NỐI ───────────┘
```

User thấy top theo W, tưởng đó là form tốt nhất. Thực tế scoring **bỏ qua** measured rate và **bỏ qua** sample size.

## Kiến trúc mục tiêu

```
┌─────────────────────────────────────────────────────────────────┐
│  expert_effective_weight(user, pick_type, mode, period)         │
├─────────────────────────────────────────────────────────────────┤
│  w_manual  ← expert_weight()          (audit, không đổi JSON)   │
│  perf      ← expert_performance()     (DB rolling_90d)            │
│  rate      ← wilson_lower(hits,total) hoặc 0.5 prior nếu null   │
│  ramp      ← min(1, total / MIN_SAMPLE)                         │
│                                                                  │
│  blend:    w_manual × rate × ramp + (1-ramp) × UNKNOWN × w_man  │
│  measured: rate (clamped) × ramp + UNKNOWN × (1-ramp)             │
│  weight:   w_manual (legacy)                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│  forum_recommendation_service                                    │
├─────────────────────────────────────────────────────────────────┤
│  scoring_w(user, pt) = expert_effective_weight(..., mode)       │
│                                                                  │
│  _aggregate_loto_scores      score += scoring_w                   │
│  _aggregate_loto_consensus   weight_sum += scoring_w              │
│  _de_top4                  de_scores += scoring_w (×1.5 btd)    │
│  _best_btl                 max scoring_w per number               │
│  _de_cham_leaders          sort by scoring_w                      │
│  _collect_dan_board        sort by scoring_w (display W giữ)    │
│  _forum_confidence         avg scoring_w                          │
└─────────────────────────────────────────────────────────────────┘
```

## Quyết định thiết kế

### D1 — Ba khái niệm tách biệt

| Field | Nguồn | Dùng cho |
|-------|-------|----------|
| `weight` | `expert_weight()` | Audit, so sánh track record thủ công |
| `performance` | `expert_performance()` | Hiển thị hit/total |
| `effective_weight` | `expert_effective_weight()` | **Scoring đề xuất** (mode-dependent) |

`live_experts`, `dan_board`, `de_by_expert` SHALL trả cả ba khi có data.

### D2 — Wilson lower bound (conservative rate)

Tránh over-trust `1/1 = 100%`:

```python
def wilson_lower(hits: int, total: int, z: float = 1.0) -> float:
    """Wilson score interval lower bound; z=1 ≈ 68% CI."""
    if total <= 0:
        return 0.5  # uninformative prior
    p = hits / total
    n = total
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)
```

Ví dụ: `1/1 → ~0.21`, `7/13 → ~0.35`, `17/18 → ~0.85`.

### D3 — Sample ramp & minimum gate

```python
MIN_SAMPLE = 5          # env EXPERT_MIN_SAMPLE
UNKNOWN = 0.3           # DEFAULT_UNKNOWN
BLEND_PRIOR = 0.35      # khi total=0, blend giữ 35% w_manual

ramp = min(1.0, total / MIN_SAMPLE) if perf else 0.0

# blend mode
measured_factor = wilson_lower(hits, total) if perf else 0.5
effective = w_manual * (BLEND_PRIOR + (1 - BLEND_PRIOR) * measured_factor * ramp)
# Khi ramp=0 (no perf): effective = w_manual * BLEND_PRIOR  (không full W)
```

**Gate cứng:** `total == 0` trong period → `ramp = 0` → effective ≤ `w_manual × BLEND_PRIOR` (không bao giờ full W chỉ từ JSON).

**Gate mềm:** `0 < total < MIN_SAMPLE` → ramp < 1, shrink về prior.

### D4 — Scoring modes

| Mode | Công thức | Khi dùng |
|------|-----------|----------|
| `weight` | `w_manual` | Backward compat, so sánh v1 |
| `measured` | `clamp(wilson × ramp + UNKNOWN × (1-ramp))` | Chỉ tin data đo được |
| `blend` | D3 | **Default** — cân bằng track record + measured |

Query: `GET /forum/recommendations?scoring_mode=blend`  
Env: `EXPERT_SCORING_MODE=blend`  
Extension: `chrome.storage.local` key `reco_scoring_mode`.

### D5 — Period mặc định `rolling_90d`

```python
DEFAULT_PERIOD_LABEL = os.getenv("EXPERT_PERF_PERIOD", "rolling_90d")
```

- Performance lookup và effective weight dùng cùng period.
- Calendar month (`2026-06`) vẫn qua `?performance_period=2026-06` hoặc audit.
- Cron/settlement refresh `rolling_90d` sau ingest (đã có hook v2).

### D6 — Category gate (giữ từ v2)

`expert_weight()` vẫn chặn dan→STL leak. `expert_effective_weight()` gọi `expert_performance(user, pick_type)` **đúng pick_type** — không merge dan family theo `total` lớn nhất (đã fix v2 first-match).

### D7 — Consensus panel

`_aggregate_loto_consensus` tie-break `weight_sum` đổi thành `effective_weight_sum` khi `scoring_mode != weight`.

Logic phiếu (+1/user/số) **không đổi** — chỉ tie-break khi hòa phiếu.

### D8 — Backward compatibility

- `scoring_mode=weight` → response giống v2 (score values khớp ±0.001).
- Field `weight` trên mọi object **không đổi** semantics.
- `effective_weight` field mới, optional null khi mode=weight và không expose (hoặc = weight).

## Hằng số (config)

| Env | Default | Mô tả |
|-----|---------|-------|
| `EXPERT_SCORING_MODE` | `blend` | `weight` \| `measured` \| `blend` |
| `EXPERT_PERF_PERIOD` | `rolling_90d` | Period cho perf + effective |
| `EXPERT_MIN_SAMPLE` | `5` | Ramp full confidence |
| `EXPERT_BLEND_PRIOR` | `0.35` | Giữ % W manual khi chưa đủ mẫu |
| `EXPERT_WILSON_Z` | `1.0` | Conservative factor |

## File thay đổi dự kiến

| File | Thay đổi |
|------|----------|
| `app/services/expert_scorer.py` | `expert_effective_weight()`, `wilson_lower()` |
| `app/services/expert_winrate_service.py` | `DEFAULT_PERIOD_LABEL` → rolling_90d |
| `app/services/forum_recommendation_service.py` | `scoring_w()` wrapper; inject mode/period |
| `app/routers/forum.py` | Query `scoring_mode`, `performance_period` |
| `extension/src/popup/popup.ts` | Legend, sort effective, mode toggle |
| `extension/src/lib/recommendations-api.ts` | Types `effective_weight`, `scoring_mode` |
| `tests/test_effective_weight.py` | NEW |
| `tests/test_reco_scoring_blend.py` | NEW |
| `scripts/audit_reco_scoring.py` | NEW |

## Ví dụ sau v3 (blend, rolling_90d)

| User | pick | w_manual | perf | wilson | ramp | effective |
|------|------|----------|------|--------|------|-----------|
| nhcsxh | btl | 1.0 | 1/2 | 0.12 | 0.4 | ~0.38 |
| himle79 | dan_40s | 0.94 | 7/13 | 0.35 | 1.0 | ~0.55 |
| himle79 | stl | 0.3 | — | 0.5 | 0 | ~0.10 |
| T98 | stl | 0.95 | 0/2 | 0.0 | 0.4 | ~0.13 |
| VIPER12A | stl | 0.3 | 1/1 | 0.21 | 0.2 | ~0.09 |

`nhcsxh` không còn dominate BTL chỉ vì W=1.0.

## Phase 4 (v4 — không làm trong v3)

- Time decay: `effective × exp(-λ × days_since_last_pick)`
- Per-number dan hit rate
- Auto-suggest weight file từ rolling backtest
