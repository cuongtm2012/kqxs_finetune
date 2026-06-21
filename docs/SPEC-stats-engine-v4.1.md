# SPEC: Stats Engine — Thống Kê Mô Tả XSMB + Candidate Filter v4.1

**Project:** `analysis-rbk-py`
**Date:** 2026-06-21
**Status:** Hoàn chỉnh — sẵn sàng code

## 1. Mục tiêu

Thay thế Prediction Engine bằng **Stats Engine** — cung cấp:
1. **Công cụ thống kê mô tả** cho người chơi chuyên
2. **Candidate pool** cho **lô** + **đề** (2 số cuối giải ĐB)
3. Lift-weighted scoring + lý do thống kê cho mọi candidate

---

## 2. Nguyên tắc

1. **Raw data first** — số liệu gốc, baseline luôn đi kèm
2. **Param hóa** — tự filter
3. **Lý do cho mọi candidate**
4. **Fast** — cache hot data
5. **Backtest quality gate**

---

## 3. Modules & Endpoints

### Module 1-6: Giống v3

| Module | Endpoint | Status |
|--------|----------|--------|
| 1 | `/stats/pairs` | Done |
| 2 | `/stats/gap/*` | Done |
| 3 | `/stats/digits/*` + `/stats/digits/de-dau` | Done |
| 4 | `/stats/lo-roi` | Done |
| 5 | `/stats/calendar/*` + `loto-theo-db/loto` | Done |
| 6 | `/stats/max-dan` | Done |

---

### Module 7: Candidate Pool

#### GET /stats/candidates

| Param | Default | Mô tả |
|-------|---------|-------|
| `target` | `loto` | `loto` / `de` |
| `top` | 20 (loto) / 10 (de) | |
| `min_filters` | 1 | |
| `sort` | `score` | `score` / `filters` / `loto` |
| `include_reasons` | true | |
| `include_pair_detail` | false | |
| `target_date` | (opt) | |

#### 7.1 Loto targets (giống v3)

| Filter | Threshold | Score contribution |
|--------|-----------|-------------------|
| `lag-1` | lift ≥ 1.10 | `(lift-1)×2` cap 0.5 |
| `same-day` | lift ≥ 1.10 | `(lift-1)×2` cap 0.5 |
| `max-cycle` | pct ≥ 70% | `pct/100` |
| `calendar` | lift ≥ 1.05 | `(lift-1)×3` cap 0.5 |
| `lo-roi` | lift > 1.0 | `(lift-1)×1` |

#### 7.2 Đề targets (de) — KHÔNG có de-max-cycle

| Filter | Threshold | Score contribution | Lý do |
|--------|-----------|-------------------|-------|
| `de-lag1` | lift ≥ 1.05 | `(lift-1)×3` cap 0.5 | P(đề hôm nay \| đề hôm qua) |
| `de-calendar` | lift ≥ 1.05 | `(lift-1)×3` cap 0.5 | Đề theo thứ |
| `de-loto-boost` | lift ≥ 1.05 | `(lift-1)×2` cap 0.3 | Loto về hôm qua → rơi vào đề |
| ~~`de-max-cycle`~~ | ❌ **LOẠI BỎ** | — | Gambler's fallacy: đề chỉ 1 slot/ngày, gan không có ý nghĩa |

**Tại sao bỏ de-max-cycle?**
- Lô: 27 slot/ngày → P(loto về) ~24%/ngày, gan 15 ngày vẫn có 24% cơ hội mỗi ngày
- Đề: 1 slot/ngày → P(đề về) ~1%/ngày, gan 50 ngày hay 0 ngày đều chỉ 1%
- Max cycle đề chỉ là thống kê mô tả, không phải signal dự đoán
- Endpoint `/stats/digits/de-dau` vẫn giữ để người chơi tham khảo

#### 7.3 Response

```json
{
  "endpoint": "candidates",
  "target": "de",
  "target_date": "2026-06-22",
  "as_of_date": "2026-06-20",
  "disclaimer": "...",
  "context": {
    "yesterday_de": "60",
    "yesterday_lotos": 25,
    "target_weekday": "Chủ nhật"
  },
  "candidates": [
    {
      "loto": "07",
      "score": 0.95,
      "filters_matched": 3,
      "score_breakdown": {
        "de-loto-boost": 0.30,
        "de-calendar": 0.24,
        "de-lag1": 0.41
      },
      "reasons": [
        "de-loto-boost: loto 07 về hôm qua, đề 07 có P=... (lift 1.15x)",
        "de-calendar: chủ nhật đề 07 tần suất ... (lift 1.08x)",
        "de-lag1: đề 60 hôm qua → 07 có P=... (lift 1.21x)"
      ]
    }
  ],
  "filters_applied": [
    {"name": "de-lag1", "min_lift": 1.05, "matched": 8},
    {"name": "de-calendar", "min_lift": 1.05, "matched": 12},
    {"name": "de-loto-boost", "min_lift": 1.05, "matched": 15}
  ],
  "meta": {
    "total_candidates": 10,
    "target": "de",
    "filters_run": 3,
    "avg_score": 0.85,
    "scoring_method": "lift-weighted",
    "sort": "score",
    "query_time_ms": 85,
    "warning": "Đề chỉ 1 sample/ngày — noise cao. Backtest thường dưới random. Chỉ dùng tham khảo."
  }
}
```

---

### Module 8: Backtest

#### POST /stats/candidates/backtest

| Param | Default | Mô tả |
|-------|---------|-------|
| `days` | 90 | |
| `top` | (auto) | 20 lô / 10 đề |
| `min_filters` | 1 | |
| `target` | `loto` | `loto` / `de` |

Chạy với min_filters = 1, 2, 3. Nếu target=de và lift<1.0 → tự disable + warning.

---

## 4. Scorer

### Loto
| Filter | Formula | Cap | Range |
|--------|---------|-----|-------|
| lag-1 | `(lift-1)×2` | 0.5 | 0-0.5 |
| same-day | `(lift-1)×2` | 0.5 | 0-0.5 |
| max-cycle | `pct/100` | 1.0 | 0-1.0 |
| calendar | `(lift-1)×3` | 0.5 | 0-0.5 |
| lo-roi | `(lift-1)×1` | none | 0-∞ |

### Đề
| Filter | Formula | Cap | Range |
|--------|---------|-----|-------|
| de-lag1 | `(lift-1)×3` | 0.5 | 0-0.5 |
| de-calendar | `(lift-1)×3` | 0.5 | 0-0.5 |
| de-loto-boost | `(lift-1)×2` | 0.3 | 0-0.3 |

---

## 5. Optimizations

### 5.1 Cache
- `_cached_all_loto_hits` ✅
- `_cached_de_slot_days` ✅ (mới)
- `clear_stats_cache()` gọi từ scheduler + refresh-views ✅

### 5.2 elif → 2 if ✅

### 5.3 Lo-roi sliding window ✅

### 5.4 Performance warn >1000ms ✅

---

## 6. Implementation Status

| Module | Endpoint | Status |
|--------|----------|--------|
| 1-6 | Các module cơ bản | Done |
| 7 | `/stats/candidates?target=loto` | **Done** |
| 7 | `/stats/candidates?target=de` | **Done** (3 filters, no de-max-cycle) |
| 8 | `/stats/candidates/backtest` | **Done** |

**Đã hoàn thành (v4.1):**
- [x] Xóa `de-max-cycle` khỏi filter defs trong candidate_service
- [x] Giữ endpoint `/stats/digits/de-dau` cho tham khảo
- [x] `context.yesterday_lotos` = số lượng loto hôm qua (không trả full list)

---

## 7. So sánh v4.0 → v4.1

| Thay đổi | Lý do |
|----------|-------|
| **Bỏ de-max-cycle** khỏi candidate filter | Đề chỉ 1 slot/ngày — gan không có ý nghĩa dự đoán |
| Giữ `/stats/digits/de-dau` cho tham khảo | Người chơi vẫn muốn xem thống kê |
| Filters cho đề giảm từ 4 → 3 | Chỉ giữ de-lag1, de-calendar, de-loto-boost |
| Loto max-cycle vẫn giữ | 27 slot/ngày, phân phối khác với đề |
