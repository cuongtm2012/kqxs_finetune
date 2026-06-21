# SPEC: Stats Engine — Thống Kê Mô Tả XSMB + Candidate Filter v4.0

**Project:** `analysis-rbk-py`  
**Date:** 2026-06-21  
**Status:** **Done** — candidate `loto` + `de`, lift-weighted scoring, backtest

> Phiên bản trước: [v3](SPEC-stats-engine-v3.md) · [v2.1](SPEC-stats-engine-v2.1.md)

## 1. Mục tiêu

Thay thế Prediction Engine bằng **Stats Engine** — cung cấp:

1. **Công cụ thống kê mô tả** cho người chơi chuyên
2. **Candidate pool** cho **lô** (2 số cuối mọi giải) và **đề** (2 số cuối giải ĐB)
3. Lift-weighted scoring + lý do thống kê cho mọi candidate

**Không có candidate cho đầu/đít đề** — chỉ giữ endpoint thống kê `/stats/digits/de-dau` (module 3).

---

## 2. Nguyên tắc

1. **Raw data first** — số liệu gốc, baseline luôn đi kèm
2. **Param hóa** — tự filter
3. **Lý do cho mọi candidate**
4. **Fast** — cache hot data
5. **Backtest quality gate** — đo hit rate vs random baseline

---

## 3. Kiến trúc

```
routers/stats.py
services/stats_service.py       ← module stats endpoints + de filter helpers
services/candidate_service.py   ← candidate builder + scorer + backtest
prediction/                     ← code cũ (inactive, giữ DEFAULT_TOP)
```

---

## 4. Modules

### Module 1–6: Giống v3 (Done)

| Module | Endpoint | Status |
|--------|----------|--------|
| 1 | `GET /stats/pairs` | Done |
| 2 | `GET /stats/gap`, `/gap/hot-cold`, `/gap/nhip`, `/gap/max-cycle` | Done |
| 3 | `GET /stats/digits`, `/digits/de-dau` | Done |
| 4 | `GET /stats/lo-roi` | Done |
| 5 | `GET /stats/calendar`, `/calendar/loto-theo-db`, `/calendar/loto-theo-loto` | Done |
| 6 | `GET /stats/max-dan` | Done |

Chi tiết params/response: xem [SPEC v3 §4](SPEC-stats-engine-v3.md).

---

### Module 7: Candidate Pool

#### `GET /stats/candidates`

| Param | Default | Mô tả |
|-------|---------|-------|
| `target_date` | (opt) | Ngày dự đoán; mặc định = ngày sau `as_of_date` |
| `top` | theo `target` | `loto` → **20**, `de` → **10** (từ `DEFAULT_TOP`) |
| `min_filters` | 1 | Số filter tối thiểu mỗi candidate |
| `sort` | `score` | `score` / `filters` / `loto` |
| `target` | `loto` | **`loto` / `de`** |
| `include_reasons` | true | |
| `include_pair_detail` | false | |

**Logic ngày:**

- `as_of_date` = ngày KQXS mới nhất trước `target_date` (hoặc latest draw)
- Context lấy từ `as_of_date`: `yesterday_lotos`, `yesterday_de`, `target_weekday`

#### 7.1 Target types

| Target | Mô tả | Universe | Samples/ngày | Default `top` |
|--------|-------|----------|-------------|---------------|
| `loto` | 2 số cuối bất kỳ giải | 00–99 | 27 | 20 |
| `de` | 2 số cuối giải ĐB | 00–99 | 1 | 10 |

Response field candidate: luôn dùng key **`loto`** (kể cả `target=de`).

#### 7.2 Filters — `target=loto`

| Filter key | Data source | min threshold | Score |
|------------|-------------|---------------|-------|
| `lag-1` | Pairs lag-1 với loto hôm qua | lift ≥ 1.10 | `(lift−1)×2`, cap 0.5 |
| `same-day` | Pairs same-day với loto hôm qua | lift ≥ 1.10 | `(lift−1)×2`, cap 0.5 |
| `max-cycle` | Gap/max cycle loto | pct ≥ 70% | `pct/100` |
| `calendar` | Tần suất loto theo thứ | lift ≥ 1.05 | `(lift−1)×3`, cap 0.5 |
| `lo-roi` | Lô rơi sau đề hôm qua | lift > 1.0 | `(lift−1)×1` |

#### 7.3 Filters — `target=de`

| Filter key | Data source | min threshold | Score |
|------------|-------------|---------------|-------|
| `de-lag1` | Đề hôm qua → đề hôm nay | lift ≥ 1.05 | `(lift−1)×3`, cap 0.5 |
| `de-calendar` | Đề theo thứ | lift ≥ 1.05 | `(lift−1)×3`, cap 0.5 |
| `de-max-cycle` | Gap đề (00–99) | pct ≥ 70% | `pct/100` |
| `de-loto-boost` | Loto hôm qua → đề hôm nay | lift ≥ 1.05, occ ≥ 10 | `(lift−1)×2`, cap 0.3 |

#### 7.4 Response mẫu (`target=de`)

```json
{
  "endpoint": "candidates",
  "target": "de",
  "target_date": "2026-06-21",
  "as_of_date": "2026-06-20",
  "disclaimer": "Stats-based candidate pool. Lift-weighted score. Không phải dự đoán.",
  "context": {
    "yesterday_de": "60",
    "yesterday_lotos": ["03", "05", "..."],
    "target_weekday": "Chủ nhật"
  },
  "candidates": [
    {
      "loto": "98",
      "score": 1.49,
      "filters_matched": 2,
      "score_breakdown": {
        "de-lag1": 0.5,
        "de-max-cycle": 0.99
      },
      "reasons": [
        "de-lag1: đề 60 hôm qua → 98 có P=1.4% (lift 1.35x)",
        "de-max-cycle: đề 98 gan 484/489 ngày (99%)"
      ]
    }
  ],
  "filters_applied": [
    {"name": "de-lag1", "min_lift": 1.05, "matched": 8},
    {"name": "de-calendar", "min_lift": 1.05, "matched": 12},
    {"name": "de-max-cycle", "min_pct": 70, "matched": 3},
    {"name": "de-loto-boost", "min_lift": 1.05, "matched": 15}
  ],
  "meta": {
    "total_candidates": 10,
    "target": "de",
    "total_de_scanned": 42,
    "filters_run": 4,
    "avg_score": 1.12,
    "scoring_method": "lift-weighted",
    "warning": "Đề chỉ 1 sample/ngày — noise cao...",
    "query_time_ms": 1076
  }
}
```

**Scoring:** `score` = tổng `score_breakdown` (làm tròn 2 chữ số).

---

### Module 8: Backtest

#### `POST /stats/candidates/backtest`

| Param | Default | Mô tả |
|-------|---------|-------|
| `days` | 90 | Số ngày gần nhất |
| `top` | theo `target` | `loto` → 20, `de` → 10 |
| `min_filters` | 1 | |
| `target` | `loto` | `loto` / `de` |

Chạy candidate builder lùi theo từng ngày, so với random baseline của target đó.

**Baseline:**

| Target | Random baseline | Ghi chú |
|--------|-----------------|---------|
| `loto` | Monte Carlo 5000 trials | hit@k ~95.5% (@10), ~99.7% (@20) |
| `de` | `top / 100` | hit@10 = 10%, hit@20 = 20% |

**Configs test:** `min_filters` ∈ {1, 2, 3} + `random_baseline`.

**De quality gate:** nếu best model lift < 1.0 → `meta.target_enabled = false` + `warnings[]`.

```json
{
  "module": "candidates",
  "type": "backtest",
  "target": "de",
  "results": [
    {
      "model": "candidates (min_filters=1, sort=score)",
      "hit_rate@10": 0.1,
      "recall@10": 0.1,
      "lift": 1.0,
      "days_evaluated": 90
    },
    {"model": "random_baseline", "hit_rate@10": 0.1, "recall@10": 0.1, "lift": 1.0}
  ],
  "meta": {"target_enabled": true, "query_time_ms": 28000}
}
```

---

## 5. Cache & performance

| Cache | File | Clear khi |
|-------|------|-----------|
| `_cached_all_loto_hits` | `stats_service.py` | import KQXS, `refresh-views` |
| `_cached_de_slot_days` | `stats_service.py` | import KQXS, `refresh-views` |

`clear_stats_cache()` gọi từ `scheduler` (sau import) và `analytics/refresh-views`.

Query candidates > 1000ms → log warning.

---

## 6. Implementation status

| Module | Endpoint | Status |
|--------|----------|--------|
| 1–6 | Stats cơ bản | **Done** |
| 7 | `GET /stats/candidates?target=loto` | **Done** |
| 7 | `GET /stats/candidates?target=de` | **Done** |
| 8 | `POST /stats/candidates/backtest` | **Done** |

**Code chính:**

- `app/services/stats_service.py` — `de_lag1_matches`, `de_calendar_matches`, `de_max_cycle_matches`, `de_loto_boost_matches`
- `app/services/candidate_service.py` — `build_candidates`, `run_candidates_backtest`
- `app/routers/stats.py` — mount endpoints

---

## 7. Rủi ro & giới hạn

### Đề (`target=de`)

| Vấn đề | Mức độ |
|--------|--------|
| 1 sample/ngày → noise cao | ⚠️ |
| Backtest dễ ≤ random | 🔴 |
| Baseline @10 = 10% | Không kỳ vọng > 12% |

**Mitigation:** `meta.warning` trên response; backtest trả `warnings` nếu lift < 1.0.

### Candidates không persist

Output chỉ tính on-the-fly qua API — **không lưu DB**. Muốn lịch sử → cần thêm persistence (future work).

---

## 8. Ví dụ gọi API

```bash
# Loto — default top 20
curl "http://localhost:8081/stats/candidates"

# Đề — default top 10
curl "http://localhost:8081/stats/candidates?target=de"

# Đề — override top
curl "http://localhost:8081/stats/candidates?target=de&top=15&min_filters=2"

# Backtest đề 90 ngày
curl -X POST http://localhost:8081/stats/candidates/backtest \
  -H 'Content-Type: application/json' \
  -d '{"days": 90, "target": "de"}'
```
