# SPEC: Stats Engine — Thống Kê Mô Tả XSMB + Candidate Filter v4.2

**Project:** `analysis-rbk-py`  
**Date:** 2026-06-21  
**Status:** **Done** — scoring balance + evaluate + backtest metrics (implemented)

> Phiên bản trước: [v4.1](SPEC-stats-engine-v4.1.md) · [v4](SPEC-stats-engine-v4.md)

## 1. Mục tiêu

Giữ nguyên v4.1, bổ sung cải tiến sau backtest thực tế (21/06/2026):

1. Cân bằng scoring — `lo-roi` không chi phối ranking lô
2. Tie-break đề khi score hòa
3. Metric backtest rõ ràng theo target
4. Endpoint evaluate 1 ngày — so prediction vs KQXS thực

---

## 2. Thay đổi v4.1 → v4.2

| # | Thay đổi | Lý do |
|---|----------|-------|
| 1 | **Cap `lo-roi` = 1.0** | Lift 2–3x không cap → đè lag-1, calendar, max-cycle |
| 2 | **Tie-break đề** | Nhiều đề cùng score 1.00; ưu tiên `de-loto-boost` > `de-lag1` > `de-calendar` |
| 3 | **Backtest metric** | Lô: **recall** (hit_rate ~100% vô nghĩa). Đề: **hit_rate@top** |
| 4 | **Backtest đề: chỉ min_filters 1, 2** | min_filters=3 → 6.9% dưới random |
| 5 | **`GET /stats/candidates/evaluate`** | Audit 1 ngày không cần chạy full backtest |
| 6 | **Khuyến nghị `min_filters≤2` cho đề** | API vẫn nhận >2 nhưng meta warning |

**Chưa làm (future):** persist candidates vào DB (Module 9).

---

## 3. Modules 1–6

Giống v4.1 — **Done**.

---

## 4. Module 7: Candidate Pool

### GET /stats/candidates

Giống v4.1. Scorer cập nhật:

#### Loto filters

| Filter | Threshold | Score |
|--------|-----------|-------|
| `lag-1` | lift ≥ 1.10 | `(lift−1)×2`, cap **0.5** |
| `same-day` | lift ≥ 1.10 | `(lift−1)×2`, cap **0.5** |
| `max-cycle` | pct ≥ 70% | `pct/100`, cap **1.0** |
| `calendar` | lift ≥ 1.05 | `(lift−1)×3`, cap **0.5** |
| `lo-roi` | lift > 1.0 | `(lift−1)×1`, cap **1.0** ← **mới v4.2** |

#### Đề filters (3 filter, không de-max-cycle)

| Filter | Threshold | Score |
|--------|-----------|-------|
| `de-lag1` | lift ≥ 1.05 | `(lift−1)×3`, cap 0.5 |
| `de-calendar` | lift ≥ 1.05 | `(lift−1)×3`, cap 0.5 |
| `de-loto-boost` | lift ≥ 1.05 | `(lift−1)×2`, cap 0.3 |

#### Sort tie-break (`sort=score`, `target=de`)

Khi `score` bằng nhau, sort phụ theo tổng priority filter:

```
de-loto-boost (3) > de-lag1 (2) > de-calendar (1) > loto ASC
```

---

## 5. Module 8: Backtest

### POST /stats/candidates/backtest

| Param | Default |
|-------|---------|
| `days` | **90** |
| `top` | auto (20 lô / 10 đề) |
| `target` | `loto` |

#### Metric chính

| Target | Primary metric | Lift = |
|--------|----------------|--------|
| `loto` | **recall@top** | model_recall / random_recall |
| `de` | **hit_rate@top** | model_hit / random_hit |

`hit_rate@20` cho lô vẫn trả về nhưng **không dùng làm lift** (random ~99.7%).

#### Configs chạy

| Target | min_filters tested |
|--------|-------------------|
| `loto` | 1, 2, 3 |
| `de` | **1, 2 only** |

Response `meta`:

```json
{
  "primary_metric": "recall",
  "days": 90,
  "target_enabled": true
}
```

---

## 6. Module 9: Evaluate (mới)

### GET /stats/candidates/evaluate

So sánh prediction đã build vs KQXS thực của `target_date`.

| Param | Default | Mô tả |
|-------|---------|-------|
| `target_date` | **required** | Ngày đã có KQXS |
| `target` | `loto` | `loto` / `de` |
| `top` | auto | |
| `min_filters` | 1 | |
| `sort` | `score` | |

#### Response mẫu — lô

```json
{
  "endpoint": "candidates/evaluate",
  "target": "loto",
  "target_date": "2026-06-21",
  "as_of_date": "2026-06-20",
  "prediction": ["81", "69", "49"],
  "actual": {
    "de": "83",
    "loto": ["06", "07", "13", "..."]
  },
  "metrics": {
    "primary_metric": "recall",
    "hit_day": true,
    "hits": ["06", "69", "81", "82"],
    "hits_count": 4,
    "top_k": 20,
    "recall": 0.174
  }
}
```

#### Response mẫu — đề

```json
{
  "target": "de",
  "metrics": {
    "primary_metric": "hit_rate",
    "hit": false,
    "actual_de": "83",
    "rank": null
  }
}
```

---

## 7. Module 10: Persist (future — chưa code)

Lưu candidates sau mỗi ngày vào DB để audit lịch sử. Không block v4.2.

---

## 8. Implementation status

| Module | Endpoint | Status |
|--------|----------|--------|
| 7 | `/stats/candidates` | **Done** (v4.2 scorer) |
| 8 | `/stats/candidates/backtest` | **Done** (v4.2 metrics) |
| 9 | `/stats/candidates/evaluate` | **Done** |
| 10 | persist candidates | **TODO** |

---

## 9. Ví dụ API

```bash
curl "http://localhost:8081/stats/candidates?target=de"
curl "http://localhost:8081/stats/candidates/evaluate?target_date=2026-06-21&target=loto"
curl -X POST http://localhost:8081/stats/candidates/backtest \
  -H 'Content-Type: application/json' \
  -d '{"days":90,"target":"de"}'
```

---

## 10. Kết quả thực tế (21/06/2026) — động lực v4.2

| Target | Kết quả | Ghi chú |
|--------|---------|---------|
| Lô top 20 | 6/23 recall, hit_day ✅ | lo-roi cap giúp đa dạng hóa ranking |
| Đề top 10 | Trượt 83 ❌ | Đúng kỳ vọng noise cao |
| Đề min_filters=3 (30d) | 6.9% < random | → bỏ khỏi backtest đề |
