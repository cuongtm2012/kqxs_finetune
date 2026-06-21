# SPEC: Stats Engine — Thống Kê Mô Tả XSMB + Candidate Filter v3.0

**Project:** `analysis-rbk-py`
**Date:** 2026-06-21
**Status:** Hoàn chỉnh — sẵn sàng code phase cuối

## 1. Mục tiêu

Thay thế Prediction Engine (dự đoán dựa trên ensemble lift ~1.02x, gần random) bằng **Stats Engine** — cung cấp:
1. **Công cụ thống kê mô tả** cho người chơi chuyên tự phân tích
2. **Candidate pool** từ multi-factor filtering, mỗi candidate có **lift-weighted score** + lý do thống kê

**Triết lý:** XSMB gần như perfectly random. Không model nào beat random >1.15x. Engine cung cấp data + lý do để người chơi tự quyết định.

---

## 2. Nguyên tắc thiết kế

1. **Raw data first** — mọi endpoint trả về số liệu gốc (count, prob, baseline)
2. **Param hóa** — người dùng tự filter: min_lift, window, sort, limit
3. **Baseline luôn đi kèm** — mọi metric có cột baseline random
4. **Lý do cho mọi candidate** — không chỉ số, phải có lý do thống kê
5. **Fast** — 1-2 SQL query tối ưu, cache hot data
6. **Module hóa** — mỗi module độc lập
7. **Backtest quality gate** — hit rate phải đo và báo cáo

---

## 3. Kiến trúc

```
routers/stats.py              ← 1 router, mỗi module 1 endpoint
services/stats_service.py      ← core logic (SQL + Python processing)
services/candidate_service.py  ← candidate pool + scorer + backtest
prediction/                    ← giữ nguyên code cũ (không xoá)
```

---

## 4. Modules & Endpoints

### Module 1: Pair Analytics

#### GET /stats/pairs

| Param | Default | Mô tả |
|-------|---------|-------|
| `type` | `same-day` | `same-day` / `lag-1` |
| `min_lift` | 1.05 | Lift tối thiểu |
| `min_occ` | 30 | Số lần xuất hiện tối thiểu |
| `limit` | 50 | (max 500) |
| `sort` | `lift` | `lift` / `count` / `prob` |
| `from_date` | 2020-01-01 | |
| `to_date` | latest | |

---

### Module 2: Gap & Max Cycle & Nhịp

| Endpoint | Mô tả |
|----------|-------|
| `GET /stats/gap?loto=88` | Chi tiết gap + max cycle + distribution |
| `GET /stats/gap/hot-cold` | Hot/cold ranking 100 loto |
| `GET /stats/gap/nhip?loto=88` | Tần suất nhịp + vị trí giải |
| `GET /stats/gap/max-cycle` | Top loto gần max cycle nhất |

---

### Module 3: Digit + Đầu Đề Cycle

| Endpoint | Mô tả |
|----------|-------|
| `GET /stats/digits` | Phân phối đầu/đít |
| `GET /stats/digits/de-dau` | Chu kỳ đầu đề (giống /chu-ky-dac-biet) |

---

### Module 4: Lô Rơi

| Param | Default |
|-------|---------|
| `loto` | (opt) |
| `de` | (opt) |
| `window` | 3 |
| `limit` | 20 |

---

### Module 5: Calendar

| Endpoint | Mô tả |
|----------|-------|
| `GET /stats/calendar` | Thống kê theo thứ/ngày/tháng |
| `GET /stats/calendar/loto-theo-db` | Sau ĐB X → loto Y nào |
| `GET /stats/calendar/loto-theo-loto` | Sau loto X → loto Y nào |

---

### Module 6: Max Dàn

| Param | Default |
|-------|---------|
| `size` | 3 |
| `min_co_occur` | 20 |
| `limit` | 20 |

---

### Module 7: Candidate Pool (Multi-Factor)

#### GET /stats/candidates

| Param | Default | Mô tả |
|-------|---------|-------|
| `target_date` | (opt) | Mặc định ngày mai |
| `top` | 20 | Số candidate |
| `min_filters` | 1 | Filters tối thiểu **(default giảm từ 2→1)** |
| `sort` | `score` | `score` / `filters` / `loto` |
| `include_reasons` | true | |
| `include_pair_detail` | false | |

#### 7.1 Filters

| Filter | Threshold | Score contribution |
|--------|-----------|-------------------|
| `lag-1 pair` | lift ≥ 1.10 | `(lift - 1) × 2` — max 0.5 |
| `same-day pair` | lift ≥ 1.10 | `(lift - 1) × 2` — max 0.5 |
| `max-cycle` | pct_of_max ≥ 70% | `pct / 100` — 0.7 to 1.0 |
| `calendar bias` | lift ≥ 1.05 | `(lift - 1) × 3` — max 0.5 |
| `lo-roi` | lift > 1.0 | `(lift - 1) × 1` — unbounded |

#### 7.2 Scorer: Lift-Weighted Score

**Vấn đề v2:** 12 loto cùng có 4 filters, không phân biệt được cái nào mạnh hơn.

**Fix v3:** Mỗi filter đóng góp score dựa trên độ mạnh thực tế của signal:

```python
def _compute_score(filters_matched: dict[str, dict]) -> float:
    score = 0.0
    score += filters_matched.get("lag-1", {}).get("score_contribution", 0)
    score += filters_matched.get("same-day", {}).get("score_contribution", 0)
    score += filters_matched.get("max-cycle", {}).get("score_contribution", 0)
    score += filters_matched.get("calendar", {}).get("score_contribution", 0)
    score += filters_matched.get("lo-roi", {}).get("score_contribution", 0)
    return round(score, 2)
```

**Score contribution từng filter:**

| Filter | Công thức | Range | Ví dụ |
|--------|-----------|-------|-------|
| lag-1 | `(lift - 1) × 2` (cap 0.5) | 0.0–0.5 | lift 1.19 → 0.38 |
| same-day | `(lift - 1) × 2` (cap 0.5) | 0.0–0.5 | lift 1.24 → 0.48 |
| max-cycle | `pct / 100` | 0.0–1.0 | 75% → 0.75 |
| calendar | `(lift - 1) × 3` (cap 0.5) | 0.0–0.5 | lift 1.08 → 0.24 |
| lo-roi | `(lift - 1) × 1` | 0.0–unbounded | lift 2.74 → **1.74** |

**Lý do scale khác nhau:**
- **Lo-roi** ×1 không cap — vì lift có thể rất cao (2.74x), cần phản ánh đúng signal mạnh
- **Lag-1** ×2 cap 0.5 — vì lift dao động 1.10–1.30, cần scale lên để so sánh được
- **Max-cycle** không cap — 70%→0.7, 95%→0.95, gần tới max cycle là signal mạnh nhất
- **Calendar** ×3 cap 0.5 — lift thường rất thấp (1.05–1.15), cần boost để không bị át

#### 7.3 Sort

- Mặc định: score giảm dần
- `sort=filters`: số filters matched giảm dần (giống v2)
- `sort=loto`: alphabet

#### 7.4 Response

```json
{
  "endpoint": "candidates",
  "target_date": "2026-06-22",
  "as_of_date": "2026-06-20",
  "disclaimer": "Stats-based candidate pool. Lift-weighted score. Không phải dự đoán.",
  "context": {
    "yesterday_lotos": ["03","05","06",...],
    "yesterday_de": "60",
    "target_weekday": "Chủ nhật"
  },
  "candidates": [
    {
      "loto": "07",
      "score": 1.74,
      "filters_matched": 1,
      "score_breakdown": {
        "lo-roi": 1.74
      },
      "reasons": [
        "lô rơi: sau đề 60 loto 07 rơi 64.8% (lift 2.74x)"
      ]
    },
    {
      "loto": "00",
      "score": 2.15,
      "filters_matched": 4,
      "score_breakdown": {
        "lag-1": 0.38,
        "same-day": 0.48,
        "calendar": 0.24,
        "lo-roi": 1.05
      },
      "reasons": [
        "lag-1: 13 hôm qua → 00 có P=... (lift 1.19x)",
        "same-day: (00,41) cùng về ... (lift 1.24x)",
        "calendar: chủ nhật loto 00 tần suất ... (lift 1.08x)",
        "lô rơi: sau đề 60 loto 00 rơi ... (lift 2.05x)"
      ]
    },
    {
      "loto": "88",
      "score": 1.95,
      "filters_matched": 4,
      "score_breakdown": {
        "lag-1": 0.42,
        "same-day": 0.38,
        "max-cycle": 0.75,
        "calendar": 0.24,
        "lo-roi": 0.16
      },
      "reasons": [
        "lag-1: 79 hôm qua → 88 có P=... (lift 1.21x)",
        "same-day: (88,89) cùng về ... (lift 1.19x)",
        "max-cycle: current gap 15/20 ngày (75%)",
        "calendar: chủ nhật loto 88 tần suất ... (lift 1.08x)",
        "lô rơi: sau đề 60 loto 88 rơi ... (lift 1.16x)"
      ]
    }
  ],
  "filters_applied": [
    {"name": "lag-1 pair", "min_lift": 1.10, "matched": 15},
    {"name": "same-day pair", "min_lift": 1.10, "matched": 12},
    {"name": "max-cycle", "min_pct": 70, "matched": 5},
    {"name": "calendar bias", "min_lift": 1.05, "matched": 18},
    {"name": "lo-roi", "window": 3, "matched": 8}
  ],
  "meta": {
    "total_candidates": 20,
    "total_lotos_scanned": 58,
    "filters_run": 5,
    "avg_filters_per_candidate": 2.3,
    "avg_score": 1.45,
    "scoring_method": "lift-weighted (mỗi filter scale khác nhau)",
    "query_time_ms": 120
  }
}
```

#### 7.5 min_filters default = 1

Cho phép loto chỉ match 1 filter nhưng score rất cao (vd: lô rơi lift 2.74x) vẫn vào candidate pool. Trước đây min_filters=2 sẽ loại bỏ 07 dù signal rất mạnh.

---

### Module 8: Backtest

#### POST /stats/candidates/backtest

| Param | Default |
|-------|---------|
| `days` | 90 |
| `top` | 20 |
| `min_filters` | 1 |

Chạy với cả min_filters=1,2,3 so sánh với random baseline.

**Response mở rộng:**
```json
{
  "module": "candidates",
  "type": "backtest",
  "results": [
    {
      "model": "candidates (min_filters=1, sort=score)",
      "hit_rate@20": 0.998,
      "recall@20": 0.206,
      "lift": 1.03
    },
    {
      "model": "candidates (min_filters=2, sort=filters)",
      "hit_rate@20": 0.997,
      "recall@20": 0.204,
      "lift": 1.02
    },
    {
      "model": "candidates (min_filters=3, sort=filters)",
      "hit_rate@20": 0.995,
      "recall@20": 0.195,
      "lift": 0.98
    },
    {"model": "random_baseline", "hit_rate@20": 0.997, "recall@20": 0.200, "lift": 1.0}
  ]
}
```

---

## 5. Optimizations

### 5.1 Cache `_cached_all_loto_hits`
- `@lru_cache(maxsize=1)`
- `clear_stats_cache()` gọi từ scheduler import + refresh-views + clear_feature_cache
- ✅ Applied

### 5.2 elif → 2 if trong lag-1 và same-day matches
- ✅ Applied

### 5.3 Lo-roi sliding window
- O(n×w) → O(n)
- ✅ Applied

### 5.4 Candidate performance >1000ms → auto warn
- ✅ Applied

---

## 6. Implementation Status

| Module | Endpoint | Status |
|--------|----------|--------|
| 1 | `/stats/pairs` | Done |
| 2 | `/stats/gap/*` | Done |
| 3 | `/stats/digits/*` | Done |
| 4 | `/stats/lo-roi` | Done |
| 5 | `/stats/calendar/*` | Done |
| 6 | `/stats/max-dan` | Done |
| 7 | `/stats/candidates` | **Cần update scorer** |
| 8 | `/stats/candidates/backtest` | **Cần update** |

---

## 7. Thay đổi từ v2.1 → v3.0

| Thay đổi | Lý do |
|----------|-------|
| **Scorer mới**: lift-weighted thay vì đếm filters | 12 loto cùng 4 filters không phân biệt được |
| **score_breakdown** trong candidate response | User thấy điểm đến từ đâu |
| **min_filters default = 1** | Lot 07 (lo-roi lift 2.74x) chỉ 1 filter nhưng signal cực mạnh |
| **sort param**: `score` / `filters` / `loto` | Linh hoạt cho người chơi |
| **score formula cho mỗi filter scale khác nhau** | Vì mỗi filter có phân phối lift khác nhau |
| **avg_score** trong meta | So sánh quality giữa các ngày |
