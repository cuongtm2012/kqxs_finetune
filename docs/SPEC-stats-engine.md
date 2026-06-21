# SPEC: Stats Engine — Thống Kê Mô Tả XSMB v1.1

**Project:** `analysis-rbk-py`
**Date:** 2026-06-21
**Status:** Draft — chờ duyệt từng module

## 1. Mục tiêu

Thay thế Prediction Engine (dự đoán gần random) bằng **Stats Engine** — cung cấp công cụ thống kê mô tả cho người chơi chuyên tự phân tích. Dữ liệu xác suất thống kê thực tế cho thấy XSMB gần như perfectly random, nên thay vì "dự đoán", engine cung cấp:

- Significant pairs (same-day + lag-1) với lift vs baseline
- Gap distribution + hot/cold ranking + max cycle history
- Digit (đầu/đít) phân phối theo thời gian
- Calendar-based stats (thứ, ngày tháng, tháng)
- Lô rơi (conditional probability trên ĐB)
- Loto theo ĐB / theo loto
- Max dàn cùng về (cluster >2 số)
- Baseline so sánh vs random cho mọi số liệu

Các page tham khảo từ mketqua.net cho thấy thị trường có nhu cầu rất lớn về thống kê mô tả dạng này.

## 2. Nguyên tắc thiết kế

1. **Raw data first** — mọi endpoint trả về số liệu gốc (count, prob, baseline), không normalize/ensemble
2. **Param hóa** — người dùng tự filter: min_count, min_lift, window, sort, limit, date_range
3. **Baseline luôn đi kèm** — mọi metric có cột baseline random để tự đánh giá
4. **Fast** — 1-2 SQL query tối ưu, không compute on-the-fly phức tạp
5. **Có thể sort theo nhiều tiêu chí**: lift / count / prob / gap / frequency
6. **Module hóa** — mỗi module độc lập, có thể bật/tắt

## 3. Kiến trúc

```
routers/stats.py         ← 1 router, mỗi module 1 endpoint
services/stats_service.py ← core logic (SQL + Python processing)
prediction/              ← giữ nguyên code cũ (không xoá), chỉ không active
```

Thay router trong `main.py`: `predictions.router` → `stats.router`.

Các file cũ (`prediction/models/*`, `ensemble.py`, `backtest.py`) giữ nguyên để tham khảo, không active.

---

## Module 1: Pair Analytics (Priority 1)

### 1.1 Mô tả

Phân tích cặp loto:
- **Same-day co-occurrence**: loto X và Y xuất hiện cùng ngày, đo lift so với P(X)×P(Y)
- **Lag-1 sequence**: loto X hôm qua → loto Y hôm nay, đo P(Y|X) vs P(Y)
- **Significance filter**: chỉ giữ pairs có lift > threshold và min occurrences

### 1.2 API

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

### 1.3 Response

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

### 1.4 SQL

**Same-day:**
```sql
WITH daily AS (
  SELECT d.draw_date, p.last_two
  FROM draws d JOIN prizes p ON p.draw_id = d.id
  WHERE d.region = 'MB' AND d.draw_date BETWEEN %s AND %s
)
SELECT
  a.last_two AS x, b.last_two AS y,
  COUNT(*) AS co_occurrences
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
SELECT
  y AS from_loto, t AS to_loto,
  COUNT(*) AS occurrences
FROM (
  SELECT
    LAG(lotos) OVER (ORDER BY draw_date) AS yesterday,
    lotos AS today
  FROM daily
) seq, unnest(seq.yesterday) AS y, unnest(seq.today) AS t
WHERE seq.yesterday IS NOT NULL
GROUP BY y, t
HAVING COUNT(*) >= %s
```

---

## Module 2: Gap & Max Cycle Analytics (Priority 2)

### 2.1 Mô tả

Lấy cảm hứng từ `/chu-ky` và `/tan-so-nhip` của mketqua.net.
- **Gap distribution**: histogram gaps giữa các lần về của 1 loto
- **Max cycle**: chu kỳ dài nhất không về, kèm ngày bắt đầu/kết thúc
- **Nhịp**: dãy gap (nhịp) giữa 2 lần về gần nhất
- **Hot/Cold**: sắp xếp loto theo gap hiện tại hoặc frequency
- **Vị trí giải**: loto về ở giải nào (G0, G1, G2,...)

### 2.2 API

```
GET /stats/gap?loto=88
GET /stats/gap/hot-cold
GET /stats/gap/nhip?loto=88        ← tần suất nhịp (giống /tan-so-nhip)
GET /stats/gap/max-cycle            ← top loto gần max cycle lịch sử nhất
```

#### GET /stats/gap

| Param | Default | Mô tả |
|-------|---------|-------|
| `loto` | (required) | Loto cần tra |
| `window` | 0 (all) | Số ngày gần nhất |

#### GET /stats/gap/hot-cold

| Param | Default | Mô tả |
|-------|---------|-------|
| `sort` | `gap` | `gap` (gan nhất) / `frequency` / `pct_of_max` |
| `limit` | 30 | |
| `min_gap` | 5 | Gap tối thiểu để có mặt trong danh sách |

#### GET /stats/gap/nhip

| Param | Default | Mô tả |
|-------|---------|-------|
| `loto` | (required) | Loto cần tra |
| `from_date` | 30 ngày trước | |
| `to_date` | latest | |

#### GET /stats/gap/max-cycle

| Param | Default | Mô tả |
|-------|---------|-------|
| `limit` | 30 | |
| `min_gap` | 5 | |
| `sort` | `pct_of_max` | `pct_of_max` / `gap` / `max_gap` |

### 2.3 Response

**gap?loto=88:**
```json
{
  "module": "gap",
  "type": "detail",
  "loto": "88",
  "current_gap": 15,
  "last_seen": "2026-06-06",
  "history": {
    "max_gap": 20,
    "min_gap": 0,
    "avg_gap": 3.2,
    "median_gap": 2,
    "max_cycle": {
      "value": 20,
      "from_date": "2005-11-15",
      "to_date": "2005-12-05"
    },
    "gap_distribution": [
      {"range": "0-2", "count": 1245},
      {"range": "3-5", "count": 567},
      {"range": "6-10", "count": 234},
      {"range": "11-15", "count": 45},
      {"range": "16-20", "count": 12}
    ],
    "total_occurrences": 2103,
    "times_exceeded_current_gap": 2
  },
  "meta": {
    "total_days": 6213,
    "disclaimer": "Gap analysis dựa trên lịch sử. Không có cơ sở xác suất cho việc 'càng gan càng dễ về'."
  }
}
```

**gap/nhip?loto=23:**
```json
{
  "module": "gap",
  "type": "nhip",
  "loto": "23",
  "from_date": "2026-05-21",
  "to_date": "2026-06-20",
  "data": [
    {"date": "2026-06-18", "weekday": 3, "count": 1, "prizes": ["G4", "G6"], "nhip": 2},
    {"date": "2026-06-16", "weekday": 1, "count": 2, "prizes": ["G3", "G5"], "nhip": 1},
    {"date": "2026-06-15", "weekday": 0, "count": 1, "prizes": ["G3"], "nhip": 3},
    ...
  ],
  "total_occurrences": 12,
  "avg_nhip": 2.5
}
```

**gap/max-cycle:**
```json
{
  "module": "gap",
  "type": "max-cycle",
  "data": [
    {"loto": "88", "current_gap": 15, "max_gap_hist": 20, "pct_of_max": 75, "frequency": 0.238},
    {"loto": "45", "current_gap": 12, "max_gap_hist": 18, "pct_of_max": 66, "frequency": 0.241},
    ...
  ]
}
```

---

## Module 3: Digit Distribution (Priority 3)

### 3.1 Mô tả

Phân phối chữ số đầu (hàng chục) và đít (hàng đơn vị) của các loto — tương tự `/dau-duoi-loto` của mketqua.
Bổ sung: **chu kỳ ĐB** — đầu đề gan bao nhiêu ngày, với max cycle lịch sử.

### 3.2 API

```
GET /stats/digits
GET /stats/digits/de-dau           ← đầu đề (giống /chu-ky-dac-biet)
```

| Param | Default | Mô tả |
|-------|---------|-------|
| `type` | `both` | `dau` / `dit` / `both` |
| `window` | 0 (all) | Số ngày gần nhất |

### 3.3 Response

```json
{
  "module": "digits",
  "type": "both",
  "data": {
    "dau": [
      {"digit": "0", "count": 12345, "prob": 0.099, "baseline": 0.1, "lift": 0.99},
      ...
    ],
    "dit": [...]
  },
  "pairs": [
    {"dau": "3", "dit": "7", "count": 567, "prob": 0.045, "baseline": 0.01, "lift": 4.5}
  ]
}
```

**de-dau:**
```json
{
  "module": "digits",
  "type": "de-dau",
  "data": [
    {"digit": "0", "current_gap": 3, "last_seen": "2026-06-17", "max_gap_hist": 61},
    {"digit": "4", "current_gap": 20, "last_seen": "2026-05-31", "max_gap_hist": 66},
    ...
  ]
}
```

---

## Module 4: Calendar Stats (Priority 4)

### 4.1 Mô tả

Thống kê theo thời gian: thứ, ngày trong tháng, tháng trong năm.
Tương tự `/loto-theo-db`, `/loto-theo-loto`.

### 4.2 API

```
GET /stats/calendar
GET /stats/calendar/loto-theo-db   ← sau ĐB X thì loto Y hay về nhất
GET /stats/calendar/loto-theo-loto ← sau loto X thì loto Y hay về nhất
```

| Param | Default | Mô tả |
|-------|---------|-------|
| `by` | `weekday` | `weekday` / `dom` / `month` |
| `loto` | (optional) | Lọc theo loto cụ thể |
| `window` | 0 (all) | |

---

## Module 5: Lô Rơi (Priority 3.5)

### 5.1 Mô tả

Lấy ý tưởng từ `/thong-ke-lo-roi`. Loto xuất hiện lại (rơi) trong vòng N ngày sau khi ĐB ra 1 số cụ thể.
Đây là conditional probability: P(a loto về | đề hôm trước là X).

### 5.2 API

```
GET /stats/lo-roi?loto=88&de=45&window=3
```

| Param | Default | Mô tả |
|-------|---------|-------|
| `loto` | (optional) | Loto cần kiểm tra, bỏ trống = tất cả |
| `de` | (optional) | Đề cần kiểm tra, bỏ trống = tất cả |
| `window` | 3 | Số ngày sau khi đề về để tính "rơi" |
| `limit` | 20 | |

---

## Module 6: Max Dàn Cùng Về (Priority 5)

### 6.1 Mô tả

Mở rộng từ pair lên 3+ số — tìm bộ số thường xuất hiện cùng nhau trong cùng ngày.
Tương tự `/max-dan-cung-ve`.

### 6.2 API

```
GET /stats/max-dan?size=3&min_co_occur=30&limit=20
```

| Param | Default | Mô tả |
|-------|---------|-------|
| `size` | 3 | Số lượng loto trong dàn (3-5) |
| `min_co_occur` | 20 | Số lần xuất hiện cùng nhau tối thiểu |
| `limit` | 20 | |

---

## 4. Implementation Plan

### Phase 1 — Priority 1: Pairs + refactor
- [ ] Tạo `services/stats_service.py` — pair logic (same-day + lag-1)
- [ ] Tạo `routers/stats.py` — thay thế predictions router
- [ ] Sửa `main.py` — swap router
- [ ] Test pair endpoints với data thật

### Phase 2 — Priority 2: Gap + Max Cycle + Nhịp
- [ ] Gap detail (1 loto)
- [ ] Hot/cold ranking
- [ ] Max cycle tracking
- [ ] Nhịp tần suất (giống /tan-so-nhip)
- [ ] Vị trí giải xuất hiện

### Phase 3 — Priority 3: Digit + Lô Rơi
- [ ] Digit distribution (đầu/đít)
- [ ] Đầu đề cycle (giống /chu-ky-dac-biet)
- [ ] Lô rơi (conditional trên ĐB)

### Phase 4 — Priority 4: Calendar
- [ ] Stats theo thứ/ngày/tháng
- [ ] Loto theo ĐB
- [ ] Loto theo loto

### Phase 5 — Priority 5: Max dàn + cleanup
- [ ] Max dàn cùng về (3+ loto)
- [ ] Random baseline reference
- [ ] Cập nhật README
- [ ] Vô hiệu hóa prediction scheduler

---

## 5. Thay đổi so với v1.0

| Thay đổi | Lý do |
|----------|-------|
| Gap → Gap + Max Cycle + Nhịp | Tham khảo /chu-ky, /tan-so-nhip |
| Bổ sung đầu đề cycle | Tham khảo /chu-ky-dac-biet |
| Thêm Lô Rơi | Tham khảo /thong-ke-lo-roi |
| Thêm Max Dàn Cùng Về | Tham khảo /max-dan-cung-ve |
| Thêm vị trí giải trong nhịp | Tham khảo /tan-so-nhip |
| Thêm pct_of_max trong hot-cold sort | Người chơi muốn biết lô nào gần max cycle nhất |
| Cập nhật disclaimer | Sai lầm của prediction engine: không claim càng gan càng dễ về |
