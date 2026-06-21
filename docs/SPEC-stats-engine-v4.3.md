# SPEC: Stats Engine — Candidate Filter v4.3

**Project:** `analysis-rbk-py`  
**Date:** 2026-06-21  
**Status:** **Done**

> Phiên bản trước: [v4.2](SPEC-stats-engine-v4.2.md) · [v4](SPEC-stats-engine-v4.md)

## 1. Mục tiêu

Bổ sung **lô gan** và **tần suất hay về** vào candidate pool lô; tinh chỉnh intersection engine sau phân tích thực tế 22/06/2026.

---

## 2. Thay đổi v4.2 → v4.3

| # | Thay đổi | Lý do |
|---|----------|-------|
| 1 | Filter **`gap-hot`** | `max-cycle` (≥55% max) bỏ sót lô gan chưa chạm đỉnh (vd. 97 gap 14 ngày) |
| 2 | Filter **`frequency-hot`** | Bắt lô xuất hiện nhiều hơn baseline trung bình (lift ≥ 1.05) |
| 3 | **`max-cycle` ngưỡng 70% → 55%** | Nới để bắt gan sớm hơn |
| 4 | Intersection: **CF adaptive weekday** | Chỉ filter thứ khi ≥10 mẫu; ngược lại dùng toàn lịch sử |
| 5 | Intersection: **`min_occ=1`**, **`fallback=none`** | Tránh pick yếu; backtest tốt nhất dùng intersection thuần |
| 6 | `min_filters` max **8 → 10** | 9 filters lô |

---

## 3. Loto filters (9 filters)

| Filter | Threshold | Score |
|--------|-----------|-------|
| `lag-1` | lift ≥ 1.10 | `(lift−1)×2`, cap 0.5 |
| `same-day` | lift ≥ 1.10 | `(lift−1)×2`, cap 0.5 |
| `max-cycle` | pct ≥ **55%** | `pct/100`, cap 1.0 |
| **`gap-hot`** | gap ≥ **8** ngày | `gap/25`, cap **0.5** |
| **`frequency-hot`** | freq lift ≥ **1.05** | `(lift−1)×2`, cap **0.4** |
| `calendar` | lift ≥ 1.05 | `(lift−1)×3`, cap 0.5 |
| `lo-roi` | lift > 1.0 | `(lift−1)×1`, cap 1.0 |
| `conditional-frequency` | lift ≥ 1.05 | `(lift−1)×2`, cap 0.5 |
| `rbk-cau` | có cầu RBK | `weight×0.5`, cap 0.5 |

### Phân biệt gan / tần suất

| Khái niệm | Filter | API thống kê |
|-----------|--------|--------------|
| Gan gần max cycle | `max-cycle` | `/stats/gap/max-cycle` |
| Gan hiện tại (gap dài) | `gap-hot` | `/stats/gap/hot-cold?sort=gap` |
| Hay về theo thứ | `calendar` | `/stats/calendar` |
| Hay về toàn lịch sử | `frequency-hot` | `/stats/gap/hot-cold?sort=frequency` |

---

## 4. Intersection v4.3 defaults

| Param | v4.0 | **v4.3** |
|-------|------|----------|
| `min_occ` | 2 | **1** |
| `fallback` | `cf_only` | **`none`** |
| CF weekday | luôn filter | **adaptive** (≥10 samples) |

Response thêm `meta.cf_weekday_applied`, `meta.cf_weekday_skipped`.

---

## 5. Ví dụ API

```bash
curl "http://localhost:8081/stats/candidates?target=loto&target_date=2026-06-22"
curl "http://localhost:8081/stats/intersection?target_date=2026-06-22"
curl "http://localhost:8081/stats/gap/hot-cold?sort=gap&limit=10"
```

---

## 6. Implementation status

| Item | Status |
|------|--------|
| `gap_hot_matches`, `frequency_hot_matches` | **Done** |
| Candidate filters `gap-hot`, `frequency-hot` | **Done** |
| Intersection adaptive CF + defaults | **Done** |
| SPEC v4.3 | **Done** |
