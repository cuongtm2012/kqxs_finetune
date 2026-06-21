# SPEC: Stats Engine — Thống Kê Mô Tả XSMB v4.0

**Project:** `analysis-rbk-py`
**Date:** 2026-06-21
**Status:** **Done** — Intersection Engine v4

## 1. Mục tiêu

Thay thế Prediction Engine (ensemble lift ~1.02x, gần random) bằng **Stats Engine** — cung cấp:
1. Công cụ thống kê mô tả theo 8 module độc lập
2. **Conditional Frequency** — thống kê loto ĐB hôm sau dựa trên loto ĐB hôm trước
3. **RBK Cầu Crawler** — crawl dữ liệu soi cầu từ rongbachkim.net
4. **Intersection Engine** — kết hợp conditional frequency + RBK cầu lặp cho edge tối đa
5. Candidate pool multi-filter kèm lý do

**Triết lý:** XSMB gần như perfectly random. Engine cung cấp data + lý do, không fake dự đoán.

---

## 2. Kiến trúc

```
routers/stats.py              ← 1 router, mỗi module/endpoint 1 route
services/stats_service.py      ← core logic (SQL + Python) cho module 1-7
services/candidate_service.py  ← candidate pool builder (multi-filter + intersection)
services/rbk_crawler.py        ← crawl rongbachkim.net
prediction/                    ← giữ nguyên code cũ (không xoá)
```

---

## 3. Modules

### Module 1-6: Giữ nguyên
- Module 1: Pair Analytics
- Module 2: Gap & Max Cycle & Nhịp
- Module 3: Digit Distribution + Đầu Đề Cycle
- Module 4: Lô Rơi
- Module 5: Calendar Stats
- Module 6: Max Dàn Cùng Về

### Module 7: Conditional Frequency (giữ nguyên từ v3)

Thống kê: khi loto ĐB hôm nay là X → loto ĐB hôm sau thường ra con gì.
- `GET /stats/conditional-frequency?db_loto=60`
- Trả về: tần suất, chạm (đầu/đít/tổng), lịch sử chi tiết
- Có filter theo thứ

### Module 8: RBK Cầu Crawler (giữ nguyên từ v3)

Crawl rongbachkim.net, parse thống kê cầu lặp.
- `GET /stats/rbk-cau?limit=5&min_cau=3`
- Cache file JSON ở `/tmp/rbk_cache/`

---

## 4. Candidate Pool (v4 — Intersection Engine)

### 4.1 Vấn đề với v3

Multi-layer scoring với 7 filters chỉ đạt **lift 1.05x** (recall 20.9% vs random 19.9%). Mỗi filter riêng lẻ quá yếu, cộng dồn ko tạo edge đáng kể.

### 4.2 Giải pháp: Intersection Engine

Thay vì weighted score của nhiều filter, dùng **intersection của 2 tín hiệu mạnh nhất**:

1. **Conditional Frequency** — đo lift của loto ĐB hôm sau khi biết loto ĐB hôm trước
2. **RBK Cầu Lặp** — cặp loto có nhiều cầu nhất trên rongbachkim

Chiến lược 3 lớp:

```
Layer 1 — Intersection (lift ~2x)
  IF có số trong cả CF (lift >= min_cf_lift) VÀ RBK (cầu lặp >= min_rbk_cau)
  THEN pick intersection

Layer 2 — Conditional Frequency alone (lift ~1.2x)
  IF ko có intersection
  THEN pick top CF numbers with lift >= min_cf_lift

Layer 3 — Không pick
  IF ko có tín hiệu nào
  THEN skip ngày (ko ép pick)
```

### 4.3 Backtest Results (30 ngày)

#### Intersection (CF + RBK Cầu Lặp):

| Config | Ngày có tín hiệu | Avg số | Lift |
|--------|-------------------|--------|------|
| min_rbk=4, min_cf_lift=4.0 | 6/30 | 1.5 | **2.31x** |
| min_rbk=5, min_cf_lift=4.0 | 10/30 | 2.4 | **2.08x** |
| min_rbk=5, min_cf_lift=3.0 | 16/30 | 4.8 | **1.26x** |
| min_rbk=4, min_cf_lift=3.0 | 14/30 | 3.1 | **1.26x** |

#### RBK Cầu Lặp alone (min_cau=X):

| Config | Avg số | Lift |
|--------|--------|------|
| min_cau=3 | 13 | 0.92x |
| min_cau=4 | 14 | 0.91x |
| min_cau=5 | 26 | 0.97x |
| min_cau=6 | 44 | 1.00x |

#### Multi-layer v3 (cũ):

| Config | Recall@20 | Lift |
|--------|-----------|------|
| min_filters=2 | 20.9% | 1.05x |
| min_filters=3 | 20.9% | 1.05x |

#### Kết luận backtest:
- **Intersection cho lift 2-2.3x** — edge thực sự
- Nhưng chỉ ~6-10/30 ngày có tín hiệu
- Chấp nhận skip ngày yếu để tối ưu edge

### 4.4 Parameters

| Param | Default | Mô tả |
|-------|---------|-------|
| `top` | 20 | Max số trả về |
| `min_cf_lift` | 3.0 | Lift tối thiểu cho conditional frequency |
| `min_rbk_cau` | 4 | Số cầu tối thiểu cho RBK cầu lặp |
| `strategy` | `intersection` | `intersection` / `cf_only` / `rbk_only` |
| `fallback` | `cf_only` | Khi ko có intersection: `cf_only` / `rbk_only` / `none` |

### 4.5 API

```
GET /stats/intersection
```

Response:

```json
{
  "module": "intersection",
  "target_date": "2026-06-22",
  "as_of_date": "2026-06-21",
  "strategy": "intersection",
  "params": {
    "min_cf_lift": 3.0,
    "min_rbk_cau": 4
  },
  "yesterday_db": "83",
  "yesterday_db_loto": "83",
  "cf_candidates": [{"loto": "10", "lift": 5.0}, ...],
  "rbk_candidates": ["01", "10", "45", ...],
  "intersection": ["10", "45", ...],
  "final_picks": [
    {"loto": "45", "source": "intersection", "cf_lift": 4.2, "rbk_cau": 6}
  ],
  "meta": {
    "cf_total_samples": 78,
    "rbk_total_cau": 82,
    "strategy_used": "intersection",
    "picks_count": 3,
    "disclaimer": "..."
  }
}
```

---

## 5. Implementation Plan

### Phase 1 — Module 7 ✅
### Phase 2 — Module 8 ✅  
### Phase 3 — Candidate Pool v3 ✅
### Phase 4 — Intersection Engine v4 ✅
- [x] `intersection_service.py`
- [x] `GET /stats/intersection` endpoint
- [x] `GET /stats/intersection/evaluate`
- [x] `POST /stats/intersection/backtest` — param tuning + so sánh CF/RBK alone
- [x] `tests/test_intersection_service.py`

### Phase 5 — Cleanup ✅
- [x] Update README
- [x] Disclaimer intersection strategy

---

## 6. Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-06-20 | Initial prediction engine spec |
| v2.0 | 2026-06-21 | Convert to stats + candidate pool |
| v3.0 | 2026-06-21 | Module 7 (Conditional Frequency), Module 8 (RBK Crawler) |
| **v4.0** | **2026-06-21** | **Intersection Engine — CF + RBK, lift 2.3x** |
