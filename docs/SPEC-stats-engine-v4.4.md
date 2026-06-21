# SPEC: Stats Engine — Frequency Rank & Đề Trend v4.4

**Project:** `analysis-rbk-py`  
**Date:** 2026-06-21  
**Status:** **Done**

> Phiên bản trước: [v4.3](SPEC-stats-engine-v4.3.md)

## 1. Mục tiêu

1. **Lô:** frequency rank/trend theo cửa sổ **30→300 ngày**; tích hợp vào candidates.
2. **Đề:** frequency rank/trend + **đầu/tổng** trend; cửa sổ **1y→5y** (tối đa 1825 ngày).
3. **Đề ↔ Intersection:** pick CF∩RBK xuất hiện trong top đề candidates.

---

## 2. Cửa sổ (windows)

| Loại | `DEFAULT_*_WINDOWS` | Momentum | Ngưỡng trend |
|------|----------------------|----------|--------------|
| **Lô** | 30, 50, 100, 200, 300 | `rate_30d − rate_300d` | **≥ 3pp** |
| **Đề** | 365, 730, 1095, **1825** | `rate_365d − rate_1825d` | **≥ 0.8pp** |

Đề: `DE_MAX_FREQ_WINDOW_DAYS = 1825` (5 năm). Request vượt → HTTP 400.

---

## 3. API frequency

### Lô

| Endpoint | Default | Mô tả |
|----------|---------|-------|
| `GET /stats/frequency/loto-rank` | `window=30` | Hot/cold theo số **ngày** loto về |
| `GET /stats/frequency/loto-summary` | `windows=30,50,100,200,300` | Hot/cold đa cửa sổ |
| `GET /stats/frequency/loto-trend` | `windows=30,50,100,200,300` | `trending_up`, `trending_down`, `stable_hot` |

### Đề

| Endpoint | Default | Mô tả |
|----------|---------|-------|
| `GET /stats/frequency/de-rank` | `window=730` | Hot/cold đề; mỗi row có `dau`, `dit`, `tong` |
| `GET /stats/frequency/de-summary` | `windows=365,730,1095,1825` | Hot/cold đa cửa sổ |
| `GET /stats/frequency/de-trend` | `windows=365,730,1095,1825` | Momentum đề + `dau`/`tong` |
| `GET /stats/frequency/de-digit-trend` | `windows=365,730,1095,1825` | Đầu đề / tổng đề heating |

**Metric đề:**

| Field | Ý nghĩa |
|-------|---------|
| `count` | Số lần đề về trong cửa sổ |
| `rate_pct` | `count / window_days × 100` |
| `baseline_count` | `window_days / 100` |
| `lift` | `count / baseline_count` |
| `dau` / `tong` | Chữ số hàng chục / tổng `(dau+dit) % 10` |

**Stable-hot đề:** `rate_short ≥ 1.2%` và `rate_long ≥ 1.5%` (short = cửa sổ đầu, long = cửa sổ cuối).

---

## 4. Candidates — filters

### Lô (11 filters)

| Filter | Threshold | Score contribution |
|--------|-----------|-------------------|
| `lag-1` | lift ≥ 1.10 | `(lift−1)×2`, cap 0.5 |
| `same-day` | lift ≥ 1.10 | `(lift−1)×2`, cap 0.5 |
| `max-cycle` | pct ≥ 55% | `pct/100` |
| `gap-hot` | gap ≥ 8 | `gap/25`, cap 0.5 |
| `frequency-hot` | lift ≥ 1.05 | `(lift−1)×2`, cap 0.4 |
| **`frequency-rank`** | top 25 / cửa sổ | `(lift−1)×2`, cap 0.5 |
| **`frequency-trend`** | momentum ≥ 3pp | `momentum/20`, cap 0.5 |
| `calendar` | lift ≥ 1.05 | `(lift−1)×3`, cap 0.5 |
| `lo-roi` | lift > 1.0 | `(lift−1)×1`, cap 1.0 |
| `conditional-frequency` | lift ≥ 1.05 | `(lift−1)×2`, cap 0.5 |
| `rbk-cau` | có cầu RBK | `weight×0.5`, cap 0.5 |

`min_filters` max: **12**.

### Đề (9 filters)

| Filter | Priority | Threshold | Score |
|--------|----------|-----------|-------|
| **`de-intersection`** | 5 | CF∩RBK pick | `(cf_lift−1)×2` cap 0.6 + `rbk/8` cap 0.5 |
| **`de-cf`** | 4 | lift ≥ 3.0 | `(lift−1)×2`, cap 0.5 |
| **`de-frequency-trend`** | 4 | momentum ≥ 0.8pp hoặc stable-hot | `momentum/15`, cap 0.5 |
| **`de-digit-trend`** | 3 | đầu/tổng momentum ≥ 2pp | `momentum/20`, cap 0.4 |
| `de-loto-boost` | 3 | lift ≥ 1.05 | `(lift−1)×2`, cap 0.3 |
| **`de-frequency-rank`** | 2 | top 15 / cửa sổ | `(lift−1)×2`, cap 0.5 |
| `de-lag1` | 2 | lift ≥ 1.05 | `(lift−1)×3`, cap 0.5 |
| `de-calendar` | 1 | lift ≥ 1.05 | `(lift−1)×3`, cap 0.5 |

`DE_MAX_MIN_FILTERS = 2` (khuyến nghị; API cho phép cao hơn).

Tie-break đề khi score bằng nhau: tổng `DE_FILTER_PRIORITY`.

---

## 5. Response `context` (candidates)

| `target` | Fields |
|----------|--------|
| `loto` | `frequency_rank` (summary 5 cửa sổ), `frequency_trend` |
| `de` | `frequency_rank`, `frequency_trend`, **`digit_trend`**, `meta.intersection` |

`meta.intersection` (đề): `intersection`, `final_picks`, `strategy_used` — đồng bộ `/stats/intersection`.

---

## 6. Ví dụ (22/06/2026, as_of 21/06, đề **83**)

```bash
curl "http://localhost:8081/stats/candidates?target=loto&target_date=2026-06-22&top=20"
curl "http://localhost:8081/stats/candidates?target=de&target_date=2026-06-22&top=10"
curl "http://localhost:8081/stats/intersection?target_date=2026-06-22"
curl "http://localhost:8081/stats/frequency/de-trend?limit=10"
curl "http://localhost:8081/stats/frequency/de-digit-trend"
```

Kết quả tham khảo:

- **Lô top:** 96, 59, 52, 17, 84… (trending: 96, 52, 84, 85…)
- **Đề top:** 65, **63** (intersection), 14…
- **Intersection pick:** **63** (CF 3.51x, RBK 5 cầu)
- **Đề trending 1y vs 5y:** 92 +1.15pp, 83 +0.88pp (đầu 8, tổng 1)

---

## 7. Implementation status

| Item | Status |
|------|--------|
| `get_loto_frequency_rank/summary/trend` | **Done** |
| `get_de_frequency_rank/summary/trend` | **Done** |
| `get_de_digit_trend`, `de_digit_trend_matches` | **Done** |
| Loto filters `frequency-rank`, `frequency-trend` | **Done** |
| Đề filters `de-*` (9 filters) | **Done** |
| `DE_MAX_FREQ_WINDOW_DAYS`, `_normalize_de_windows` | **Done** |
| `meta.intersection` trong candidates đề | **Done** |
