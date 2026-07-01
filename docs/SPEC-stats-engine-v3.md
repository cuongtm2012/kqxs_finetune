# SPEC: Stats Engine — Thống Kê Mô Tả XSMB v3.0

**Project:** `analysis-rbk-py`
**Date:** 2026-06-21
**Status:** **Done** — Module 7, 8, candidate filters

## 1. Mục tiêu

Thay thế Prediction Engine (ensemble lift ~1.02x, gần random) bằng **Stats Engine** — cung cấp:
1. Công cụ thống kê mô tả theo 7 module độc lập
2. **Conditional Frequency** — thống kê loto ĐB hôm sau dựa trên loto ĐB hôm trước
3. **Cầu Crawler** — crawl dữ liệu soi cầu từ rongbachkim.net tự động
4. Candidate pool multi-filter kèm lý do

**Triết lý:** XSMB gần như perfectly random. Engine cung cấp data + lý do, không fake dự đoán.

---

## 2. Kiến trúc

```
routers/stats.py              ← 1 router, mỗi module/endpoint 1 route
services/stats_service.py      ← core logic (SQL + Python) cho module 1-7
services/candidate_service.py  ← candidate pool builder (multi-filter)
services/rbk_crawler.py        ← [NEW] crawl rongbachkim.net
prediction/                    ← giữ nguyên code cũ (không xoá)
```

Thêm file mới:
- `services/rbk_crawler.py` — crawl rongbachkim + cache
- `tests/test_rbk_crawler.py` — test crawl

---

## 3. Modules

### Module 1-6: Giữ nguyên từ v2.0
- Module 1: Pair Analytics (same-day + lag-1)
- Module 2: Gap & Max Cycle & Nhịp
- Module 3: Digit Distribution + Đầu Đề Cycle
- Module 4: Lô Rơi
- Module 5: Calendar Stats
- Module 6: Max Dàn Cùng Về

---

### Module 7: Conditional Frequency — Thống kê ĐB theo loto ĐB hôm trước

Lấy cảm hứng từ mketqua.net/giai-db-ngay-mai.

#### API

```
GET /stats/conditional-frequency
```

| Param | Default | Mô tả |
|-------|---------|-------|
| `db_loto` | (required) | Loto ĐB hôm nay (00-99) |
| `target_weekday` | (optional) | Thứ cần filter (0=CN, 1=T2, ...) |
| `min_occ` | 2 | Số lần xuất hiện tối thiểu |
| `limit` | 30 | Số kết quả |
| `sort` | `count` | `count` / `lift` |

#### Response

```json
{
  "module": "conditional-frequency",
  "db_loto": "60",
  "target_weekday": null,
  "total_samples": 12,
  "params": {...},
  "loto_frequency": [
    {"loto": "81", "count": 5, "pct": 15.6, "baseline": 10.0, "lift": 1.56},
    {"loto": "35", "count": 5, "pct": 15.6, "baseline": 10.0, "lift": 1.56}
  ],
  "cham_stats": {
    "dau": [{"digit": "8", "count": 15, "pct": 23.4}, ...],
    "duoi": [{"digit": "1", "count": 16, "pct": 25.0}, ...],
    "tong": [{"digit": "1", "count": 17, "pct": 26.6}, ...]
  },
  "history": [
    {"date": "2026-04-10", "db": "54860", "next_db": "04204", "next_loto": "04"},
    ...
  ]
}
```

#### SQL

```sql
WITH db_pairs AS (
    SELECT
        cur.draw_date,
        cur.last_two AS cur_db_loto,
        LEAD(cur.last_two) OVER (ORDER BY cur.draw_date) AS next_db_loto,
        LEAD(d.draw_date) OVER (ORDER BY cur.draw_date) AS next_date
    FROM draws d
    JOIN prizes cur ON cur.draw_id = d.id
    WHERE d.region = 'MB' AND cur.prize_level = 'DB'
)
SELECT next_db_loto, COUNT(*) AS occurrences
FROM db_pairs
WHERE cur_db_loto = %s
GROUP BY next_db_loto
HAVING COUNT(*) >= %s
ORDER BY COUNT(*) DESC;
```

---

### Module 8 (NEW): Cầu Crawler

#### Mô tả

Tích hợp dữ liệu soi cầu từ rongbachkim.net vào engine. Crawl tự động, cache kết quả, expose qua API.

**Lý do:** Không thể tự dựng cầu từ DB vì thuật toán cầu của rongbachkim dựa trên vị trí các chữ số trong bảng kết quả, rất phức tạp và không open-source.

#### Cơ chế crawl

Dùng Python `requests` + regex:
1. Gửi request đến `https://rongbachkim.net/soicau.html?submit=1&setmode=full&exactlimit=0&limit=LIMIT&ngay=DD/MM/YYYY&nhay=1&lon=1`
2. Parse HTML response:
   - Tổng số cầu: `tìm được <span>N</span> cầu`
   - Danh sách số có cầu: từ các thẻ `<a class="a_cau">XX</a>`
   - Thống kê cầu lặp: từ bảng `<td class=col1>XX,YY</td><td class=col2>N cầu</td>`
   - Cặp nhiều cầu nhất: từ text `Cặp số có nhiều cầu nhất là XX,YY: N cầu`
   - Cầu >5 ngày: `Trong đó có N cầu dài trên 5 ngày`
   - Cặp số khác nhau: `Cầu xuất hiện tại N cặp số khác nhau, trong đó có M cặp có cầu chạy hơn 5 ngày`

#### Cache

- Lưu file JSON theo ngày ở `/tmp/rbk_cache/YYYY-MM-DD_LIMIT.json`
- Cache TTL: 1 ngày
- Tự động refresh khi có request

#### API

```
GET /stats/rbk-cau?limit=5
```

| Param | Default | Mô tả |
|-------|---------|-------|
| `date` | today | Ngày cần xem cầu (YYYY-MM-DD) |
| `limit` | 5 | Độ dài cầu tối thiểu (1-9) |
| `min_cau` | 1 | Chỉ lấy cặp có >= N cầu |

#### Response

```json
{
  "module": "rbk-cau",
  "date": "2026-06-20",
  "limit": 5,
  "total_cau": 82,
  "cau_tren_5ngay": 27,
  "cap_so_khac_nhau": 37,
  "cap_tren_5ngay": 16,
  "cap_nhieu_cau_nhat": "01,10: 6 cầu",
  "cau_lap": [
    {"pair": "01,10", "count": 6},
    {"pair": "45,54", "count": 6},
    {"pair": "05,50", "count": 5}
  ],
  "unique_numbers": ["01", "05", "06", ...],
  "recommended": ["01", "10", "45", "54", ...],
  "meta": {
    "crawl_time_ms": 850,
    "cached": false
  }
}
```

#### Tính năng recommend

Từ thống kê cầu lặp, recommend các số có nhiều cầu nhất:
- Filter: chỉ lấy cặp có >= `min_cau` cầu
- Expand từng cặp thành các số riêng lẻ
- Sort theo số cầu giảm dần
- Deduplicate

#### Backtest results (30 ngày gần nhất)

`POST /stats/rbk-cau/backtest` với `{"days": 30}` — so sánh limit 1/3/5/7/9:
- Limit cao → ít số hơn, precision cao hơn
- Limit thấp → nhiều số hơn, recall cao hơn
- Response có `recommended_limit` (sweet spot theo `hit_rate×0.4 + recall×0.6`)

---

## 4. Candidate Pool (update)

Thêm 2 filters mới:

| Filter | Mô tả | Nguồn | Score |
|--------|-------|-------|-------|
| `conditional-frequency` | Loto hay về khi ĐB hôm trước = X | Module 7 (DB) | `(lift−1)×2` cap 0.5 |
| `rbk-cau` | Loto có nhiều cầu | Module 8 (crawl) | `weight×0.5` cap 0.5 |

---

## 5. Implementation Plan

### Phase 1 — Module 7: Conditional Frequency ✅
- [x] Query + `get_conditional_frequency()`
- [x] `GET /stats/conditional-frequency`

### Phase 2 — Module 8: Cầu Crawler ✅
- [x] `services/rbk_crawler.py` — crawl + parse + cache
- [x] `GET /stats/rbk-cau`
- [x] `tests/test_rbk_crawler.py`

### Phase 3 — Candidate Pool ✅
- [x] Filters `conditional-frequency`, `rbk-cau`

### Phase 4 — Module 1-6 ✅ (từ v2/v4)

### Phase 5 — backtest + persist ✅
- [x] `POST /stats/rbk-cau/backtest`
- [x] `candidate_snapshots` + persist scheduler
- [x] `target_weekday` SPEC convention (0=CN) ở API layer

---

## 6. Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-06-20 | Initial prediction engine spec |
| v2.0 | 2026-06-21 | Convert to stats + candidate pool |
| v3.0 | 2026-06-21 | Thêm Module 7 (Conditional Frequency), Module 8 (Cầu Crawler) |
