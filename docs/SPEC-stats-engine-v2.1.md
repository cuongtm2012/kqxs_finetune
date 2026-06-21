# SPEC: Stats Engine — Thống Kê Mô Tả XSMB + Candidate Filter v2.1

**Project:** `analysis-rbk-py`
**Date:** 2026-06-21
**Status:** Code review hoàn tất — apply optimization patches

## 1. Mục tiêu

Thay thế Prediction Engine (dự đoán dựa trên ensemble lift ~1.02x, gần random) bằng **Stats Engine** — cung cấp:
1. **Công cụ thống kê mô tả** cho người chơi chuyên tự phân tích
2. **Candidate pool** từ nhiều filter, kèm lý do chọn, dựa trên multi-factor filtering thay vì 1 score duy nhất

**Triết lý:** XSMB gần như perfectly random. Không model nào beat random >1.15x. Thay vì giả vờ dự đoán, engine cung cấp data + lý do để người chơi tự quyết định.

---

## 2. Nguyên tắc thiết kế

1. **Raw data first** — mọi endpoint trả về số liệu gốc (count, prob, baseline), không normalize/ensemble
2. **Param hóa** — người dùng tự filter: min_count, min_lift, window, sort, limit, date_range
3. **Baseline luôn đi kèm** — mọi metric có cột baseline random để tự đánh giá
4. **Lý do cho mọi candidate** — không chỉ số, phải có lý do thống kê
5. **Fast** — 1-2 SQL query tối ưu, cache hot data
6. **Module hóa** — mỗi module độc lập
7. **Backtest quality gate** — candidate hit rate phải được đo và báo cáo

---

## 3. Kiến trúc

```
routers/stats.py              ← 1 router, mỗi module 1 endpoint
services/stats_service.py      ← core logic (SQL + Python processing)
services/candidate_service.py  ← candidate pool builder (multi-filter)
prediction/                    ← giữ nguyên code cũ (không xoá), chỉ không active
```

Thay router trong `main.py`: `predictions.router` → `stats.router`.

Các file cũ giữ nguyên để tham khảo.

---

## 4. Modules & Endpoints

### Module 1: Pair Analytics

#### GET /stats/pairs

| Param | Default | Mô tả |
|-------|---------|-------|
| `type` | `same-day` | `same-day` hoặc `lag-1` |
| `min_lift` | 1.05 | Lift tối thiểu so với baseline |
| `min_occ` | 30 | Số lần xuất hiện tối thiểu |
| `limit` | 50 | Số pairs trả về (max 500) |
| `sort` | `lift` | `lift` / `count` / `prob` |
| `from_date` | 2020-01-01 | Ngày bắt đầu |
| `to_date` | latest | Ngày kết thúc |

**Response mẫu:**
```json
{
  "module": "pairs",
  "type": "same-day",
  "params": { "min_lift": 1.1, "min_occ": 30, "date_range": ["2020-01-01", "2026-06-20"], "total_days": 2313 },
  "data": [
    {
      "x": "10", "y": "13", "co_occurrences": 165,
      "p_xy": 0.0713, "p_x": 0.238, "p_y": 0.242, "baseline": 0.0576, "lift": 1.24, "significant": true
    }
  ],
  "meta": { "query_time_ms": 42, "total_pairs": 42, "baseline_method": "P(X)*P(Y)", "random_expected": 57 }
}
```

---

### Module 2: Gap & Max Cycle & Nhịp

#### GET /stats/gap?loto=88

Chi tiết gap cho 1 loto: distribution, max cycle, times exceeded current gap.

| Param | Mô tả |
|-------|-------|
| `loto` | Loto cần tra (required) |
| `window` | Số ngày gần nhất (0 = all) |

#### GET /stats/gap/hot-cold

Hot/cold ranking toàn bộ 100 loto.

| Param | Default | Mô tả |
|-------|---------|-------|
| `sort` | `gap` | `gap` / `frequency` / `pct_of_max` |
| `limit` | 30 | |
| `min_gap` | 5 | |

#### GET /stats/gap/nhip?loto=88

Tần suất nhịp — dãy gap + vị trí giải.

| Param | Mô tả |
|-------|-------|
| `loto` | Loto cần tra (required) |
| `from_date` | Mặc định 30 ngày trước |
| `to_date` | Latest |

#### GET /stats/gap/max-cycle

Top loto gần max cycle lịch sử nhất.

| Param | Default | Mô tả |
|-------|---------|-------|
| `sort` | `pct_of_max` | `pct_of_max` / `gap` / `max_gap` |
| `limit` | 30 | |
| `min_gap` | 5 | |

---

### Module 3: Digit Distribution + Đầu Đề Cycle

#### GET /stats/digits

| Param | Default |
|-------|---------|
| `type` | `both` |
| `window` | 0 (all) |

#### GET /stats/digits/de-dau

Chu kỳ đầu đề — giống `/chu-ky-dac-biet`.

---

### Module 4: Lô Rơi

#### GET /stats/lo-roi

| Param | Default | Mô tả |
|-------|---------|-------|
| `loto` | (opt) | Loto cần kiểm tra |
| `de` | (opt) | Đề cần kiểm tra |
| `window` | 3 | Số ngày sau khi đề về để tính "rơi" |
| `limit` | 20 | |

**Lưu ý performance:** với window > 3 và data full ~6000 ngày, cần sliding window optimization.

---

### Module 5: Calendar Stats + Loto theo ĐB/Loto

#### GET /stats/calendar

| Param | Default |
|-------|---------|
| `by` | `weekday` |
| `loto` | (opt) |
| `window` | 0 |

#### GET /stats/calendar/loto-theo-db

#### GET /stats/calendar/loto-theo-loto

---

### Module 6: Max Dàn Cùng Về

#### GET /stats/max-dan

| Param | Default | Mô tả |
|-------|---------|-------|
| `size` | 3 | 3-5 |
| `min_co_occur` | 20 | |
| `limit` | 20 | |

---

### Module 7: Candidate Pool (Multi-Factor)

#### GET /stats/candidates

| Param | Default | Mô tả |
|-------|---------|-------|
| `target_date` | (opt) | Mặc định: ngày mai |
| `top` | 20 | Số candidate |
| `min_filters` | 2 | Filters tối thiểu |
| `include_reasons` | true | |
| `include_pair_detail` | false | |

##### Filters chạy

| Filter | Mô tả | Threshold |
|--------|-------|-----------|
| `lag-1 pair` | Từ loto hôm qua → loto hôm nay có lift > threshold | min_lift=1.10 |
| `same-day pair` | Loto trong top same-day pairs với loto hôm qua | min_lift=1.10 |
| `max-cycle` | Current gap > 70% max cycle lịch sử | min_pct=70 |
| `calendar bias` | Thứ hiện tại có frequency > baseline | min_lift=1.05 |
| `lo-roi` | Lô rơi sau ĐB hôm qua | window=3, lift>1.0 |

##### Response

```json
{
  "endpoint": "candidates",
  "target_date": "2026-06-22",
  "as_of_date": "2026-06-20",
  "disclaimer": "Stats-based candidate pool. Không phải dự đoán.",
  "context": { "yesterday_lotos": [...], "yesterday_de": "60", "target_weekday": 6 },
  "candidates": [
    { "loto": "49", "filters_matched": 3, "reasons": ["...", "..."] }
  ],
  "filters_applied": [
    { "name": "lag-1 pair", "min_lift": 1.10, "matched": 12 }
  ],
  "meta": {
    "total_candidates": 20,
    "total_lotos_scanned": 48,
    "filters_run": 5,
    "avg_filters_per_candidate": 2.3,
    "query_time_ms": 120
  }
}
```

##### Scorer: Multi-Factor Scoring

Candidate score = số filters matched (0-5). Sort descending, tiebreak by loto.

**Không dùng weighted average.** Lý do: mỗi filter là independent signal, không thể so sánh "lag-1 lift 1.2x mạnh hơn calendar lift 1.05x bao nhiêu". Số filters matched là metric đơn giản nhất, dễ giải thích nhất.

---

### Module 8: Backtest Candidate Quality

#### POST /stats/candidates/backtest

Chạy candidate engine trên N ngày đã biết kết quả, đo hit rate @K.

| Param | Default | Mô tả |
|-------|---------|-------|
| `days` | 90 | Số ngày backtest |
| `top` | 20 | Top-K candidate |
| `min_filters` | 2 | |

**Response mẫu:**
```json
{
  "module": "candidates",
  "type": "backtest",
  "params": { "days": 90, "top": 20, "min_filters": 2 },
  "results": [
    { "model": "candidates (min_filters=2)", "hit_rate@20": 0.998, "recall@20": 0.204, "lift": 1.02 },
    { "model": "candidates (min_filters=3)", "hit_rate@20": 0.995, "recall@20": 0.198, "lift": 0.99 },
    { "model": "random_baseline", "hit_rate@20": 0.997, "recall@20": 0.200, "lift": 1.0 }
  ]
}
```

---

## 5. Optimizations (từ code review)

### 5.1 Cache `_all_loto_hits`

**Vấn đề:** `get_gap_hot_cold`, `get_gap_max_cycle`, `approaching_max_cycle_matches` đều fetch toàn bộ 6213 ngày × 100 loto từ DB độc lập.

**Fix:** Dùng `functools.lru_cache` với maxsize=1 và clear sau khi import KQXS mới.

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def _cached_all_loto_hits() -> dict[str, list[str]]:
    # Fetch all, cache cho tới khi có import mới
```

Gọi `_cached_all_loto_hits.cache_clear()` trong `clear_feature_cache()` hoặc sau scheduler import.

### 5.2 Lag-1 matches: elif → 2 if

**Vấn đề:** `_lag1_matches` và `_same_day_matches` dùng `elif` — nếu cả x và y đều trong yesterday_lotos, chỉ add 1.

**Fix:** Dùng 2 if riêng:

```python
for row in result["data"]:
    if row["x"] in yesterday_lotos and row["y"] not in seen:
        ...
        seen.add(row["y"])
    if row["y"] in yesterday_lotos and row["x"] not in seen:
        ...
        seen.add(row["x"])
```

### 5.3 Lo-roi sliding window

**Vấn đề:** Loop rebuild `window_lotos` set mỗi lần i → O(n×w).

**Fix:** Sliding window: thêm ngày mới, bỏ ngày cũ.

```python
window_lotos: set[str] = set()
for i in range(1, window + 1):
    window_lotos |= days[i]["loto_set"]

for i in range(len(days) - window):
    # process i with current window_lotos
    if i + window + 1 < len(days):
        window_lotos -= days[i + 1]["loto_set"]
        window_lotos |= days[i + window + 1]["loto_set"]
```

### 5.4 Pair query performance

Pairs SQL dùng self-join trên ~2300 ngày × 27 prizes = ~62K rows → self-join cho 310M combinations.

**Tối ưu:** MySQL/Postgres sẽ optimize hash join. Với 62K rows thường <500ms. Nếu chậm:
- Thêm composite index: `(draw_id, last_two)` 
- Hoặc materialize pair_counts table update nightly

### 5.5 Candidate performance monitoring

Thêm metric trong response: `query_time_ms`. Nếu >1000ms → auto-log warning.

---

## 6. Implementation Status

| Module | Endpoint | Status |
|--------|----------|--------|
| 1 | `/stats/pairs` | Done |
| 2 | `/stats/gap` | Done |
| 2 | `/stats/gap/hot-cold` | Done |
| 2 | `/stats/gap/nhip` | Done |
| 2 | `/stats/gap/max-cycle` | Done |
| 3 | `/stats/digits` | Done |
| 3 | `/stats/digits/de-dau` | Done |
| 4 | `/stats/lo-roi` | Done |
| 5 | `/stats/calendar` | Done |
| 5 | `/stats/calendar/loto-theo-db` | Done |
| 5 | `/stats/calendar/loto-theo-loto` | Done |
| 6 | `/stats/max-dan` | Done |
| 7 | `/stats/candidates` | Done |
| 8 | `/stats/candidates/backtest` | **TODO** |

**Optimization patches cần apply:**
- [ ] Cache `_all_loto_hits` với lru_cache
- [ ] Fix elif → 2 if trong lag-1 và same-day matches
- [ ] Lo-roi sliding window optimization
- [ ] Backtest candidate quality endpoint

---

## 7. Disclaimer (mọi response)

```
"disclaimer": "Thống kê dựa trên dữ liệu lịch sử XSMB. "
              "KQXS dựa trên quay số ngẫu nhiên. "
              "Không có mô hình thống kê nào beat random >1.15x liên tục. "
              "Thông tin mang tính tham khảo, không đảm bảo kết quả."
```
