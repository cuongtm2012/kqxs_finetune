# SPEC: Prediction Engine — Xác Suất Thống Kê XSMB

**Project:** `kqxs_finetune` (trước: `analysis-rbk-py`)  
**Version:** 1.1  
**Date:** 2026-06-21  
**Status:** **Implemented v1** — prediction + backtest + tuning đang chạy production

---

## 1. Mục tiêu

Xây dựng **Prediction Engine** trên PostgreSQL, dùng thuật toán xác suất thống kê để **xếp hạng** các con số có khả năng xuất hiện ở **ngày quay tiếp theo** (XSMB — Miền Bắc).

Engine **không** hứa hẹn dự đoán chính xác giải ĐB 5 chữ số. Trọng tâm thực tế:

| Target | Mô tả | Output | Default top-K |
|--------|--------|--------|---------------|
| **Lô** | 2 số cuối (00–99), xuất hiện trong **bất kỳ** giải trong 27 giải | Top-K + score | 20 |
| **Đề** | 2 số cuối giải **ĐB** (`slot_index=0`) | Top-K + score | 10 |
| **Đầu / Đít** | Chữ số hàng chục / đơn của lô (0–9) | Top digit + score | 5 |

Mọi response prediction có `disclaimer`: *"Statistical ranking only. Not guaranteed."*

---

## 2. Bối cảnh dữ liệu

### 2.1 PostgreSQL

```
postgresql://rbk:rbk@127.0.0.1:5436/rbk
```

Docker: `docker compose up -d` → container `rbk-postgres`, port **5436** (tránh conflict 5432/5433).

### 2.2 Bảng / view

| Bảng / View | Vai trò |
|-------------|---------|
| `draws` | 1 row/ngày MB (`draw_date`, `station`, `source`) |
| `prizes` | 27 row/ngày (`slot_index`, `prize_level`, `number`, `last_two`, `first_digit`, `last_digit`) |
| `mv_loto_daily` | `(draw_date, loto, hit_count)` |
| `prediction_runs`, `prediction_items` | Lưu dự đoán |
| `backtest_reports` | Kết quả backtest |
| `trends`, `caudep_snapshots`, `chot_predictions` | Legacy RBK (rongbachkim scrape) |

### 2.3 Quy ước domain (`lottery_format.py`)

- 27 slot: `DB(1) + G1(1) + G2(2) + G3(6) + G4(4) + G5(6) + G6(3) + G7(4)`
- **Lô ngày D:** tập `last_two` từ 27 giải (có trùng)
- **Đề ngày D:** `last_two` slot `DB`
- **Đầu/Đít:** `first_digit` / `last_digit` từ lô

### 2.4 Trạng thái data (2026-06-21)

| Metric | Giá trị |
|--------|---------|
| Tổng ngày MB | **~6.213** (`2007-01-01` → `2026-06-20`) |
| Nguồn `minhngoc` | ~5.944 ngày |
| Nguồn `mongo-migrate` | ~269 ngày |
| Thiếu ước tính | ~900 ngày (Tết, scrape fail) |

**Import pipeline:** `mb_import_service.import_mb_day()` → minhngoc trước, xskt fallback.

---

## 3. Giả định thống kê & giới hạn

1. Không gian dự đoán chính: **100 lô** (00–99).
2. Mỗi ngày ~27 lượt hit lô (có lặp); ~20–25 lô distinct/ngày.
3. **Ngày quay tiếp theo** = `max(draw_date) + 1 calendar day` (Tết/ngày nghỉ không có row).
4. Xổ số ngẫu nhiên — **không có edge lớn** đã chứng minh.
5. **Hit rate lô ~99%** với top-20 **không** chứng minh model giỏi (random cũng ~99%).

---

## 4. Kiến trúc (đã implement)

```
PostgreSQL (draws, prizes)
    → features.py (FeatureContext, DayRecord)
    → models/ M1–M7
    → ensemble.py (M8, load tuned_weights.json)
    → service.py
    → routers/predictions.py
    → prediction_runs / prediction_items
```

### Module map (source thực tế)

```
app/prediction/
  constants.py          # TARGET_*, MODEL_*, DEFAULT_TOP
  features.py           # FeatureContext, load history
  models/
    frequency.py        # M1
    ewma.py             # M2
    gap_survival.py     # M3
    markov.py           # M4
    bayesian_beta.py    # M5
    weekday_station.py  # M6
    digit_dau_dit.py    # M7
    base.py             # normalize_minmax, rank_scores
  ensemble.py           # M8
  backtest.py           # walk-forward
  tuning.py             # weight search
  service.py            # compute_next, evaluate
  weights.py            # load tuned_weights.json
  tuned_weights.json    # artifact tuned
```

---

## 5. Thuật toán (M1–M8)

Mỗi model nhận `as_of_date` (chỉ data **≤ as_of**) → `Dict[value, score]`.

| ID | Tên code | Ý tưởng | Params |
|----|----------|---------|--------|
| M1 | `frequency` | hits / opportunities | all-time |
| M2 | `ewma` | ngày gần trọng số cao | λ=0.98 |
| M3 | `gap` | lô gan (gap/max_gap) | — |
| M4 | `markov` | P(hit tomorrow \| hit/miss today) | bậc 1 |
| M5 | `bayesian` | Beta-Binomial posterior mean | α=β=1 |
| M6 | `weekday` | freq theo thứ target_date | min 30 samples → fallback M1 |
| M7 | `digit` | P(dau)×P(dit) cho lô; trực tiếp cho dau/dit | — |
| M8 | `ensemble` | Σ w_i × normalize(M_i) | `tuned_weights.json` |

**Đề:** dùng M1–M6 (không M7). **Đầu/Đít:** M1–M6 + M7 trực tiếp.

### Trọng số ensemble đã tune (2020–2025, walk-forward)

Nguồn: `app/prediction/tuned_weights.json` — reload qua `weights.ensemble_weights_for()`.

**Lô (top-20, 2146 ngày):**

| Model | Weight | Solo recall@20 |
|-------|--------|----------------|
| ewma | 0.447 | 0.2037 |
| digit | 0.152 | 0.2023 |
| weekday | 0.147 | 0.1998 |
| bayesian | 0.086 | 0.1981 |
| frequency | 0.072 | 0.1981 |
| markov | 0.071 | 0.1980 |
| gap | 0.025 | 0.2001 |
| **ensemble** | — | **0.2034** |

**Đề (top-10, 2146 ngày):**

| Model | Weight | Solo hit% |
|-------|--------|-----------|
| markov | 0.307 | 11.18% |
| ewma | 0.242 | 9.69% |
| bayesian | 0.171 | 10.48% |
| weekday | 0.133 | 10.62% |
| frequency | 0.107 | 10.48% |
| gap | 0.041 | 10.25% |
| **ensemble** | — | **11.46%** (random 10%) |

**Đầu/Đít (top-5, subsample 800 ngày):** recall ~50.5% (chọn 5/10 chữ số — gần random 50%).

### So sánh tune 1 năm gần (2025-06-20 → 2026-06-20, 362 ngày)

| Target | Weights 2020–25 | Tune 1 năm | Random |
|--------|-----------------|------------|--------|
| Lô recall@20 | 20.03% | **20.61%** | ~20% |
| Đề hit@10 | 9.94% | **12.15%** | 10% |

→ Trọng số dài hạn **underperform** trên data gần cho đề.

---

## 6. Feature store

**v1 (hiện tại):** Python on-the-fly từ `draws` + `prizes`. Cache in-memory per `(as_of_date, target_type)` — clear sau import.

**v2 (chưa làm):** `mv_loto_features` materialized view rolling.

Index đã có (`db/migrations/002_prediction.sql`):

```sql
CREATE INDEX idx_prizes_last_two_draw ON prizes (last_two, draw_id);
CREATE INDEX idx_draws_mb_date ON draws (draw_date) WHERE region = 'MB';
```

---

## 7. Backtest

### Walk-forward (`backtest.py`)

```
for each draw_date D in [start, end]:
    train = draws WHERE draw_date < D
    predict D with models trained on train
    compare vs actual
```

### Metrics

| Target | Metric | Ý nghĩa |
|--------|--------|---------|
| Lô | `hit_rate` | % ngày có ≥1 lô trong top-K trúng |
| Lô | `recall_at_k` | \|pred ∩ actual\| / \|actual\| |
| Lô | `lift` | hit_rate / random (Monte Carlo) |
| Đề | `hit_rate` | % ngày đề thực ∈ top-K |
| Đề | random | K/100 |

### Kết quả thực tế (không phải ví dụ lý thuyết)

**2020–2025 ensemble tuned:**
- Lô: recall **20.34%**, lift **~1.0** (gần random)
- Đề: hit **11.46%**, lift **~1.15**

**Tiêu chí ship v1:** đã ship; đề hơi trên random, lô không vượt random đáng kể.

---

## 8. Schema DB (đã migrate)

Tables trong `db/schema.sql` + `db/migrations/002_prediction.sql`:

- `prediction_runs` — UNIQUE `(target_date, target_type, model_name)`
- `prediction_items` — `(run_id, rank, value, score)`
- `backtest_reports` — lưu metrics JSONB

---

## 9. API (đã implement)

Prefix: `/predictions`

| Method | Path | Query / Body |
|--------|------|--------------|
| GET | `/predictions/next` | `target`, `top`, `model`, `as_of`, `persist` |
| GET | `/predictions/weights` | Trả `tuned_weights.json` |
| GET | `/predictions/evaluate` | `date`, `target`, `top`, `model` |
| POST | `/predictions/backtest` | `{from_date, to_date, target, top_k, models?}` |

`model` values: `ensemble`, `frequency`, `ewma`, `gap`, `markov`, `bayesian`, `weekday`, `digit`, `all`.

Legacy giữ nguyên: `/kqxs/*`, `/rbk/*`, `/analytics/*`.

---

## 10. Luồng vận hành (đã implement)

```
1. Scheduler 18:15 import MB (minhngoc → xskt)
2. refresh_loto_views()
3. clear_feature_cache() + compute_next(persist=True)
4. Dự phòng 19:05 predict nếu import fail
```

File: `app/scheduler.py` — `_import_kqxs_today()`, `_predict_next_day()`.

---

## 11. Implementation status

### Phase 1 — Foundation ✅

- [x] Migration `prediction_*`, `backtest_reports`
- [x] `features.py`
- [x] M1 Frequency + M5 Bayesian
- [x] `backtest.py` walk-forward
- [x] API `GET /predictions/next`, `POST /predictions/backtest`

### Phase 2 — Models ✅

- [x] M2 EWMA, M3 Gap, M4 Markov, M6 Weekday
- [x] M8 Ensemble + tune weights (`tuning.py`, `tuned_weights.json`)
- [x] Target đề riêng

### Phase 3 — Production ✅ (một phần)

- [x] Scheduler auto-predict
- [x] `GET /predictions/evaluate`
- [x] `GET /predictions/weights`
- [x] M7 Đầu/Đít
- [ ] Dashboard / log metrics
- [ ] UI

### Phase 4 — Backlog

- [ ] `mv_loto_features` SQL incremental
- [ ] Calibration plots
- [ ] So sánh `chot_predictions`
- [ ] MN/MT prediction
- [ ] Profile trọng số `recent` vs `long_term`
- [ ] M3 geometric survival
- [ ] Unit tests
- [ ] Backtest performance (hiện chậm trên full period)

---

## 12. Scripts

| Script | Mô tả |
|--------|--------|
| `scripts/backfill_xsmb.py` | Backfill MB `--from 2007-01-01` |
| `scripts/tune_ensemble_weights.py` | Tune + ghi `tuned_weights.json` |
| `scripts/migrate_mongo_to_pg.py` | One-time Mongo → PG |

---

## 13. Vấn đề còn tồn tại

### Data pipeline

| # | Vấn đề | Impact | Workaround |
|---|--------|--------|------------|
| D1 | xskt CrowdSec Captcha | Không scrape xskt từ IP hiện tại | Dùng minhngoc |
| D2 | ~900 ngày thiếu trong DB | Gap lịch sử | Tiếp tục backfill |
| D3 | rongbachkim blocked | chotkq/trend/caudep fail | Không dùng cho prediction v1 |
| D4 | MN/MT chỉ RSS gần | Không đủ history regional | Backlog |

### Prediction accuracy

| # | Vấn đề | Ghi chú |
|---|--------|---------|
| P1 | Lô recall ~20% ≈ random | Hit rate 99% misleading |
| P2 | Đề lift ~1.15 max (dài hạn) | Không đủ cho “chính xác cao” |
| P3 | Trọng số 2020–25 kém trên 1 năm gần (đề 9.9%) | Cần profile `recent` hoặc re-tune định kỳ |
| P4 | Gap model = gambler's fallacy | Giữ cho tương thích RBK legacy |
| P5 | dau/dit tune trên subsample 800 ngày | Metrics ít tin cậy hơn loto/de |

### Technical debt

| # | Vấn đề | File liên quan |
|---|--------|----------------|
| T1 | Feature cache không TTL | `features.py` |
| T2 | Backtest O(days × models) chậm | `backtest.py`, `tuning.py` |
| T3 | Không có tests | — |
| T4 | Python 3.9 compat | `db.py` dùng `Optional` |
| T5 | macOS LibreSSL + requests | `http_util.py` curl fallback |

---

## 14. Quyết định đã chốt (từ review)

| Câu hỏi | Quyết định |
|---------|------------|
| Top-K mặc định | Lô 20, đề 10, đầu/đít 5 |
| Ưu tiên target | Lô + đề (cả hai implemented) |
| UI | Chưa — API only |
| Trọng số ensemble | Auto-tune → `tuned_weights.json` |
| Merge caudep RBK | Chưa — backlog |

---

## 15. Tài liệu tham chiếu code

| File | Vai trò |
|------|---------|
| `app/services/lottery_format.py` | 27 slot, đầu/đít |
| `app/services/mb_import_service.py` | minhngoc + xskt fallback |
| `app/services/minhngoc_service.py` | Parser minhngoc |
| `app/routers/analytics.py` | loto-frequency, loto-gan |
| `app/routers/predictions.py` | Prediction API |
| `app/prediction/tuned_weights.json` | Trọng số production |
| `app/repositories/prediction_repo.py` | Persist predictions |
| `db/schema.sql` | Full schema |

---

*End of SPEC v1.1 — synced with source 2026-06-21*
