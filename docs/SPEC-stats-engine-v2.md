# SPEC: Stats Engine — Thống Kê Mô Tả XSMB + Candidate Filter v2.0

**Project:** `analysis-rbk-py`
**Date:** 2026-06-21
**Status:** Đã duyệt — implement Phase 1 (Pairs + router swap)

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
5. **Fast** — 1-2 SQL query tối ưu
6. **Module hóa** — mỗi module độc lập

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

## 4. Modules

### Module 1: Pair Analytics (Priority 1)

#### 4.1.1 Mô tả

Phân tích cặp loto:
- **Same-day**: loto X và Y xuất hiện cùng ngày, đo lift so với P(X)×P(Y)
- **Lag-1**: loto X hôm qua → loto Y hôm nay, đo P(Y|X) vs P(Y)
- Filter: min_lift, min_occ, sort

#### 4.1.2 API

```
GET /stats/pairs
```

| Param | Default | Mô tả |
|-------|---------|-------|
| `type` | `same-day` | `same-day` hoặc `lag-1` |
| `min_lift` | 1.05 | Lift tối thiểu so với baseline |
| `min_occ` | 30 | Số lần xuất hiện tối thiểu |
| `limit` | 50 | Số pairs trả về |
| `sort` | `lift` | `lift` / `count` / `prob` |
| `from_date` | 2020-01-01 | Ngày bắt đầu |
| `to_date` | latest | Ngày kết thúc |

#### 4.1.3 Response

```json
{
  "module": "pairs",
  "type": "same-day",
  "params": {
    "min_lift": 1.05,
    "min_occ": 30,
    "date_range": ["2020-01-01", "2026-06-20"],
    "total_days": 2313
  },
  "data": [
    {
      "x": "10",
      "y": "13",
      "co_occurrences": 165,
      "p_xy": 0.0713,
      "p_x": 0.238,
      "p_y": 0.242,
      "baseline": 0.0576,
      "lift": 1.24,
      "significant": true
    }
  ],
  "meta": {
    "query_time_ms": 45,
    "total_pairs": 42,
    "baseline_method": "P(X)*P(Y)",
    "random_expected": 57
  }
}
```

#### 4.1.4 SQL

**Same-day:**
```sql
WITH daily AS (
  SELECT d.draw_date, p.last_two
  FROM draws d JOIN prizes p ON p.draw_id = d.id
  WHERE d.region = 'MB' AND d.draw_date BETWEEN %s AND %s
)
SELECT a.last_two AS x, b.last_two AS y, COUNT(*) AS co_occurrences
FROM daily a JOIN daily b
  ON a.draw_date = b.draw_date AND a.last_two < b.last_two
GROUP BY a.last_two, b.last_two
HAVING COUNT(*) >= %s
ORDER BY COUNT(*) DESC
```

**Lag-1:**
```sql
WITH daily AS (
  SELECT d.draw_date, ARRAY_AGG(DISTINCT p.last_two ORDER BY p.last_two) AS lotos
  FROM draws d JOIN prizes p ON p.draw_id = d.id
  WHERE d.region = 'MB' AND d.draw_date BETWEEN %s AND %s
  GROUP BY d.draw_date
)
SELECT y AS from_loto, t AS to_loto, COUNT(*) AS occurrences
FROM (
  SELECT LAG(lotos) OVER (ORDER BY draw_date) AS yesterday, lotos AS today
  FROM daily
) seq, unnest(seq.yesterday) AS y, unnest(seq.today) AS t
WHERE seq.yesterday IS NOT NULL
GROUP BY y, t
HAVING COUNT(*) >= %s
```

---

### Module 2: Gap & Max Cycle & Nhịp (Priority 2)

Lấy cảm hứng từ `/chu-ky` và `/tan-so-nhip` của mketqua.net.

#### 4.2.1 API

```
GET /stats/gap?loto=88           ← chi tiết gap 1 loto
GET /stats/gap/hot-cold          ← hot/cold ranking
GET /stats/gap/nhip?loto=88      ← tần suất nhịp (giống /tan-so-nhip)
GET /stats/gap/max-cycle         ← top loto gần max cycle lịch sử nhất
```

**GET /stats/gap:**
| Param | Default | Mô tả |
|-------|---------|-------|
| `loto` | (required) | Loto cần tra |
| `window` | 0 (all) | Số ngày gần nhất |

**GET /stats/gap/hot-cold:**
| Param | Default | Mô tả |
|-------|---------|-------|
| `sort` | `gap` | `gap` / `frequency` / `pct_of_max` |
| `limit` | 30 | |
| `min_gap` | 5 | |

**GET /stats/gap/nhip:**
| Param | Default | Mô tả |
|-------|---------|-------|
| `loto` | (required) | |
| `from_date` | 30 ngày trước | |
| `to_date` | latest | |

**GET /stats/gap/max-cycle:**
| Param | Default | Mô tả |
|-------|---------|-------|
| `limit` | 30 | |
| `min_gap` | 5 | |
| `sort` | `pct_of_max` | `pct_of_max` / `gap` / `max_gap` |

#### 4.2.2 Response mẫu

**gap/nhip:**
```json
{
  "module": "gap",
  "type": "nhip",
  "loto": "23",
  "from_date": "2026-05-21",
  "to_date": "2026-06-20",
  "data": [
    {"date": "2026-06-18", "weekday": "Thứ năm", "count": 1, "prizes": ["G4", "G6"], "nhip": 2},
    {"date": "2026-06-16", "weekday": "Thứ ba", "count": 2, "prizes": ["G3", "G5"], "nhip": 1},
    {"date": "2026-06-15", "weekday": "Thứ hai", "count": 1, "prizes": ["G3"], "nhip": 3},
    ...
  ],
  "total_occurrences": 12,
  "avg_nhip": 2.5
}
```

---

### Module 3: Digit Distribution + Đầu Đề Cycle (Priority 3)

#### 4.3.1 API

```
GET /stats/digits
GET /stats/digits/de-dau       ← đầu đề cycle (giống /chu-ky-dac-biet)
```

| Param | Default | Mô tả |
|-------|---------|-------|
| `type` | `both` | `dau` / `dit` / `both` |
| `window` | 0 (all) | |

#### 4.3.2 Response mẫu

**de-dau:**
```json
{
  "module": "digits",
  "type": "de-dau",
  "data": [
    {"digit": "0", "current_gap": 3, "last_seen": "2026-06-17", "max_gap_hist": 61, "de_last": "71203"},
    {"digit": "4", "current_gap": 20, "last_seen": "2026-05-31", "max_gap_hist": 66, "de_last": "24042"},
    ...
  ]
}
```

---

### Module 4: Lô Rơi (Priority 3.5)

#### 4.4.1 API

```
GET /stats/lo-roi
```

| Param | Default | Mô tả |
|-------|---------|-------|
| `loto` | (optional) | Loto cần kiểm tra |
| `de` | (optional) | Đề cần kiểm tra |
| `window` | 3 | Số ngày sau khi đề về để tính "rơi" |
| `limit` | 20 | |

---

### Module 5: Calendar Stats + Loto theo ĐB/Loto (Priority 4)

#### 4.5.1 API

```
GET /stats/calendar
GET /stats/calendar/loto-theo-db    ← sau ĐB X thì loto Y hay về nhất
GET /stats/calendar/loto-theo-loto  ← sau loto X thì loto Y hay về nhất
```

| Param | Default | Mô tả |
|-------|---------|-------|
| `by` | `weekday` | `weekday` / `dom` / `month` |
| `loto` | (optional) | Lọc theo loto |
| `window` | 0 (all) | |

---

### Module 6: Max Dàn Cùng Về (Priority 5)

#### 4.6.1 API

```
GET /stats/max-dan
```

| Param | Default | Mô tả |
|-------|---------|-------|
| `size` | 3 | Số lượng loto trong dàn (3-5) |
| `min_co_occur` | 20 | |
| `limit` | 20 | |

---

## 5. Candidate Pool (Multi-Factor Filtering)

### 5.1 Mô tả

Endpoint chính cho người dùng cuối. Thay vì 1 prediction, engine đưa ra candidate pool với lý do từng loto dựa trên các filter đã chọn.

### 5.2 Cách tính

Mỗi loto nhận score = tổng số filters matched (không phải weighted average). Filters:

| Filter | Mô tả | Nguồn |
|--------|-------|-------|
| `lag-1 pair` | Loto xuất hiện trong top pairs với loto hôm qua | Module 1 |
| `same-day pair` | Loto trong top same-day pairs với loto trong candidate | Module 1 |
| `approaching max cycle` | Current gap > 70% max cycle lịch sử | Module 2 |
| `nhip gap` | Nhịp hiện tại > avg nhịp | Module 2 |
| `de-dau approach` | Đầu đề hiện tại > 70% max cycle | Module 3 |
| `digit momentum` | Đầu/đít có frequency > baseline 30 ngày gần | Module 3 |
| `lo-roi` | Lô rơi sau ĐB hôm nay có prob > baseline | Module 4 |
| `calendar bias` | Thứ/ngày có frequency > baseline | Module 5 |

### 5.3 API

```
GET /stats/candidates
```

| Param | Default | Mô tả |
|-------|---------|-------|
| `top` | 20 | Số candidate trả về |
| `min_filters` | 2 | Số filters tối thiểu để vào candidate |
| `include_reasons` | true | Có kèm lý do không |
| `include_pair_detail` | false | Có chi tiết từng filter không |

### 5.4 Response

```json
{
  "endpoint": "candidates",
  "target_date": "2026-06-22",
  "as_of_date": "2026-06-20",
  "disclaimer": "Stats-based candidate pool. Không phải dự đoán. Lift tối đa ~1.15x so với random.",
  "candidates": [
    {
      "loto": "49",
      "filters_matched": 3,
      "reasons": [
        "lag-1: 92 hôm qua → 49 có P=28.4% (lift 1.19x, baseline 23.8%)",
        "same-day: (49,79) cùng về 161/2313 ngày (lift 1.21x)",
        "calendar: thứ 2 loto 49 tần suất 25.8% (lift 1.08x)"
      ]
    },
    {
      "loto": "88",
      "filters_matched": 2,
      "reasons": [
        "max-cycle: current gap 15/20 ngày (75% max cycle, chỉ vượt 2/2103 lần)",
        "digit: đầu 8 tần suất 30 ngày gần 10.5% (baseline 10%)"
      ]
    },
    {
      "loto": "13",
      "filters_matched": 2,
      "reasons": [
        "same-day: (10,13) cùng về 165/2313 ngày (lift 1.24x)",
        "calendar: thứ 2 loto 13 tần suất 26.5% (lift 1.10x)"
      ]
    }
  ],
  "filters_applied": [
    {"name": "lag-1 pair", "min_lift": 1.10, "matched": 12},
    {"name": "same-day pair", "min_lift": 1.10, "matched": 8},
    {"name": "max-cycle", "min_pct": 70, "matched": 5},
    {"name": "calendar bias", "min_lift": 1.05, "matched": 9}
  ],
  "meta": {
    "total_candidates": 20,
    "total_lotos_scanned": 100,
    "filters_run": 5,
    "avg_filters_per_candidate": 2.3,
    "query_time_ms": 120
  }
}
```

### 5.5 Luồng xử lý

```
1. Lấy loto hôm qua (from latest draw)
2. Với mỗi filter module, compute subset of lotos matching
3. Union tất cả subsets → candidate pool
4. Score mỗi candidate = số filters matched
5. Sort descending, trả về top-K
```

Implement: `services/candidate_service.py`

```python
def build_candidates(target_date, top=20, min_filters=2):
    yesterday_lotos = get_yesterday_lotos(target_date)
    yesterday_de = get_yesterday_de(target_date)
    today_weekday = target_date.weekday()
    
    filters = [
        {"name": "lag-1 pair",  "fn": lambda: lag1_pairs(yesterday_lotos, min_lift=1.10)},
        {"name": "same-day pair", "fn": lambda: same_day_pairs(yesterday_lotos, min_lift=1.10)},
        {"name": "max-cycle",   "fn": lambda: approaching_max_cycle(min_pct=70)},
        {"name": "calender",    "fn": lambda: calendar_bias(today_weekday, min_lift=1.05)},
        {"name": "lo-roi",     "fn": lambda: lo_roi(yesterday_de, window=3)},
    ]
    
    candidate_scores = defaultdict(list)
    for filter_def in filters:
        matched = filter_def["fn"]()
        for loto in matched:
            candidate_scores[loto].append(filter_def["name"])
    
    # Filter by min_filters
    candidates = [(loto, reasons) for loto, reasons in candidate_scores.items()
                  if len(reasons) >= min_filters]
    candidates.sort(key=lambda x: -len(x[1]))
    
    return candidates[:top]
```

---

## 6. API Router (routers/stats.py)

| Endpoint | Module | Method |
|----------|--------|--------|
| `/stats/pairs` | 1 | GET |
| `/stats/gap` | 2 | GET |
| `/stats/gap/hot-cold` | 2 | GET |
| `/stats/gap/nhip` | 2 | GET |
| `/stats/gap/max-cycle` | 2 | GET |
| `/stats/digits` | 3 | GET |
| `/stats/digits/de-dau` | 3 | GET |
| `/stats/lo-roi` | 4 | GET |
| `/stats/calendar` | 5 | GET |
| `/stats/calendar/loto-theo-db` | 5 | GET |
| `/stats/calendar/loto-theo-loto` | 5 | GET |
| `/stats/max-dan` | 6 | GET |
| `/stats/candidates` | Candidate | GET |

---

## 7. Implementation Plan

### Phase 1 — Module 1: Pairs + router swap (ước lượng: 2-3h)
- [ ] `services/stats_service.py` — pairs (same-day + lag-1)
- [ ] `routers/stats.py` — 1 endpoint /stats/pairs
- [ ] Sửa `main.py` — swap router
- [ ] Test pairs endpoint với data thật
- [ ] Kiểm tra performance (~2000 ngày, 100×100 pairs)

### Phase 2 — Module 2: Gap/Max Cycle/Nhip (ước lượng: 3-4h)
- [ ] Gap detail + hot-cold
- [ ] Max cycle tracking
- [ ] Nhịp tần suất
- [ ] Vị trí giải

### Phase 3 — Module 3: Digit + Lô Rơi (ước lượng: 2-3h)
- [ ] Digit distribution
- [ ] Đầu đề cycle
- [ ] Lô rơi

### Phase 4 — Module 4 + 5: Calendar + Candidate (ước lượng: 3-4h)
- [ ] Calendar stats
- [ ] Loto theo ĐB / theo loto
- [ ] `candidate_service.py` — multi-filter pool builder
- [ ] `/stats/candidates` endpoint
- [ ] Kiểm tra candidate quality (top-K trúng bao nhiêu %)

### Phase 5 — Module 6 + Cleanup (ước lượng: 1-2h)
- [ ] Max dàn cùng về
- [ ] Vô hiệu hóa prediction scheduler
- [ ] Cập nhật README
- [ ] Remove prediction tables (optional)

---

## 8. Disclaimer mẫu (dùng trong mọi response)

```
"disclaimer": "Thống kê dựa trên dữ liệu lịch sử XSMB. "
              "KQXS dựa trên quay số ngẫu nhiên. "
              "Không có mô hình thống kê nào beat random >1.15x liên tục. "
              "Thông tin mang tính tham khảo, không đảm bảo kết quả."
```
