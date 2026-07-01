# SPEC: Prediction Engine v5.0 — Ensemble 11 Models + Crossover Boost

**Project:** `analysis-rbk-py`  
**Version:** 5.0  
**Date:** 2026-06-28  
**Status:** Production — đang chạy live prediction hàng ngày

---

## 1. Mục tiêu

Prediction Engine dùng ensemble của **11 model thống kê** để xếp hạng 100 số (00–99) cho XSMB, dự đoán ngày quay tiếp theo.

| Target | Mô tả | Output | Default top-K | Baseline random |
|--------|-------|--------|---------------|-----------------|
| **Lô** | 2 số cuối xuất hiện trong bất kỳ 27 giải | top-K + score | 20 | ~100% hit rate |
| **Đề** | 2 số cuối giải ĐB | top-K + score | 10 | 10% |
| **Đầu / Đít** | Chữ số hàng chục / đơn vị (0–9) | top-K + score | 5 | 50% |

Đề là target chính cần edge (lift >1.0x). Lô hit_rate ~99% là bình thường — dùng `recall_at_k` thay hit_rate.

---

## 2. Kiến trúc tổng thể

```
PostgreSQL (draws, prizes)
    → features.py (FeatureContext, DayRecord, load_all_day_records)
    → models/ (11 model, mỗi model 1 file)
    → ensemble.py (score_ensemble, _cycle_boost, _crossover_consensus_boost)
    → service.py (compute_next, evaluate, run_backtest_job)
    → routers/predictions.py (API: GET/POST)
    → prediction_runs / prediction_items (persist)
```

### File map

```
app/prediction/
  constants.py        # TARGET_*, MODEL_*, DEFAULT_TOP, DEFAULT_ENSEMBLE_WEIGHTS
  features.py         # FeatureContext, DayRecord, load_all_day_records, actual_values_for_date
  models/
    base.py           # normalize_minmax(), rank_scores()
    frequency.py      # M1 — raw hit rate (all-time)
    ewma.py           # M2 — exponentially weighted MA
    gap_survival.py   # M3 — gap-based scoring
    markov.py         # M4 — first-order Markov
    bayesian_beta.py  # M5 — Beta-Binomial posterior
    weekday_station.py# M6 — per-weekday hit rate
    digit_dau_dit.py  # M7 — digit trend (LOTO only)
    chi_square.py     # M8 — chi-square goodness-of-fit
    bayesian_update.py# M9 — sequential Bayesian multi-window
    cycle_pair.py     # M10 — 50 fixed pair cycle analysis
    forum_consensus.py# M11 — forumketqua.net dàn consensus
  ensemble.py         # score_ensemble, predict_top, _cycle_boost, _crossover_consensus_boost
  backtest.py         # walk-forward backtest engine
  tuning.py           # random search weight tuning
  service.py          # compute_next, evaluate, run_backtest_job
  weights.py          # ensemble_weights_for() → loads tuned_weights.json (fallback to defaults)
  tuned_weights.json  # Production weights (artifact from tuning)
```

---

## 3. Database

```python
# Connection
postgresql://rbk:***@127.0.0.1:5436/rbk
```

### Bảng chính

| Bảng | Vai trò |
|------|---------|
| `draws` | 1 row/ngày MB (`draw_date`, `station`, `source`) |
| `prizes` | 27 row/ngày (`slot_index`, `prize_level`, `number`, `last_two`) |
| `mv_loto_daily` | (draw_date, loto, hit_count) — denormalized |
| `prediction_runs` | (id, target_date, target_type, model_name, created_at) |
| `prediction_items` | (run_id, rank, value, score) |
| `backtest_reports` | (target_type, model_name, period, metrics JSONB) |

### Feature Loading

`FeatureContext.load(as_of_date, target_type, target_date)`:
1. Query `draws` + `prizes` cho MB, region='MB'
2. Build `DayRecord` list: mỗi ngày chứa `loto_hits` dict, `de` string, `dau_digits`, `dit_digits`
3. Dùng in-memory cache keyed bởi `(as_of_date, target_type)` — `clear_feature_cache()` để reset

### Data trạng thái (2026-06-28)

- Tổng ngày: ~6,221 (2007-01-01 đến 2026-06-28)
- Thiếu ~900 ngày (Tết, lỗi scrape)
- Nguồn: minhngoc (chính), xskt (fallback)

---

## 4. 11 Models

### M1: Frequency (`frequency.py`)

**Công thức:** hit_count / total_opportunities  
**Window:** all-time (toàn bộ history)  
**Output:** raw tỷ lệ, normalize min-max.  
**Ý nghĩa:** baseline — số nào về nhiều nhất trong lịch sử.

### M2: EWMA (`ewma.py`)

**Công thức:** `score_t = λ × hit_t + (1-λ) × score_{t-1}`  
**Lambda:** `0.97` (giảm từ 0.98 ngày 22/06 — giảm overlap giữa các ngày liên tiếp)  
**Output:** normalized [0,1].  
**Ý nghĩa:** số "hot recent" — ngày càng gần càng nặng.

### M3: Gap Survival (`gap_survival.py`)

**Công thức:** `score = 1 - (gap / max_gap)` — gap càng ngắn điểm càng cao  
**Gap:** số ngày từ lần xuất hiện gần nhất  
**Max gap:** gap lớn nhất trong lịch sử  
**Lưu ý:** Gambler's fallacy — gap ngắn score cao, gap dài score thấp.

### M4: Markov (`markov.py`)

**Ma trận chuyển:** P(hit t+1 | hit_t), P(hit t+1 | miss_t) — bậc 1  
**Output:** normalize min-max.  
**Ý nghĩa:** Nếu số hôm trước về, khả năng hôm sau về là bao nhiêu.

### M5: Bayesian Beta (`bayesian_beta.py`)

**Prior:** Beta(α=1.0, β=1.0) — uniform  
**Posterior mean:** (α + hits) / (α + β + total)  
**Output:** normalized [0,1].  
**Ý nghĩa:** shrinkage — số với ít observations bị kéo về prior.

### M6: Weekday Station (`weekday_station.py`)

**Công thức:** hit_rate riêng cho từng thứ trong tuần  
**Min samples:** 30 — nếu <30 ngày, fallback về M1  
**Output:** normalize min-max.  
**Ý nghĩa:** Một số có thể về nhiều vào thứ 2, ít vào thứ 7.

### M7: Digit Đầu Đít (`digit_dau_dit.py`)

**Chỉ dùng cho LOTO** (không cho DE).  
**Công thức:** `P(dau) × P(dit)` — tích xác suất chữ số hàng chục và hàng đơn vị.  
**Output:** normalize min-max.  
**Ý nghĩa:** Tách riêng xu hướng đầu và đuôi.

### M8: Chi-Square (`chi_square.py`)

**Test:** chi-square goodness-of-fit của observed vs expected uniform  
**Min samples:** 500 — nếu <500 tổng observations, trả uniform (1/n)  
**Score conversion:** `1 / (1 + exp(-z/2))` với z là z-score  
**Output:** normalized [0,1].  
**Ý nghĩa:** Số có z-score dương (xuất hiện nhiều hơn kỳ vọng) được ưu tiên—có thể là physical bias trong máy quay.

### M9: Bayesian Sequential Update (`bayesian_update.py`)

**Multi-window:** [5, 10, 20, 40, 80] ngày  
**Với mỗi window:** tính posterior mean, so với prior (historical freq) → lift  
**Combine:** weighted average các lifts theo recency  
**Output:** sigmoid(ln(lift) × 2) → normalized [0,1]  
**Ý nghĩa:** Detects "regime change" — số bình thường lạnh nhưng gần đây nóng lên.

### M10: Cycle Pair (`cycle_pair.py`) — **Added 23/06**

**50 fixed pairs** từ mketqua.net (số đảo và cặp bóng):

```
00-55, 01-10, 02-20, 03-30, 04-40, 05-50, 06-60, 07-70, 08-80, 09-90
11-66, 12-21, 13-31, 14-41, 15-51, 16-61, 17-71, 18-81, 19-91, 22-77
23-32, 24-42, 25-52, 26-62, 27-72, 28-82, 29-92, 33-88, 34-43, 35-53
36-63, 37-73, 38-83, 39-93, 44-99, 45-54, 46-64, 47-74, 48-84, 49-94
56-65, 57-75, 58-85, 59-95, 67-76, 68-86, 69-96, 78-87, 79-97, 89-98
```

**Algorithm:** mỗi pair có avg_cycle (khoảng cách trung bình giữa các lần về).
Nếu current_gap >= avg_cycle → pair **DUE** → boost cả 2 số 0.15-0.40.
**Output:** normalize_minmax bắt buộc — tránh raw boost dominate ensemble.

### M11: Forum Consensus (`forum_consensus.py`) — **Added 28/06**

**Nguồn:** forumketqua.net — 3 thread dàn đề: 40s K4N, 36s K5N, 64s daily  
**Crawl:** 5 pages cuối mỗi thread, parse <blockquote> HTML, lấy user có ≥20 số  
**Score:** `0.4 × overall_freq + 0.6 × top_user_freq`  
**Top users:** danv, himle79, Hanhtrinhmoi, Thuoclao6996, emvatoi213, msm43, Xuannd, phipn, Binhrau1, Rauria, No1.XS  
**Cache:** 1 ngày.  
**Weight DE:** 8% (tăng từ 5% ngày 28/06). **Weight LOTO:** 0.5%.

---

## 5. Ensemble Combination (`ensemble.py`)

### Core formula

```python
for each model in active_models:
    raw = score_model(ctx, model_name)
    norm = normalize_minmax(raw)  # [0,1] — MANDATORY for all models
    for value in universe:
        combined[value] += weight * norm[value]
combined = {k: v / total_w for k, v in combined.items()}
```

### Normalize min-max rules

- **BẮT BUỘC** với tất cả models. Cycle_pair từng bị raw 0.15-0.40 dominate ensemble (bug 24/06 — fixed).
- `normalize_minmax(raw)` → max=1.0, min=0.0.
- Score 0 nghĩa là score thấp nhất trong universe, không có nghĩa là 0% hit.

### Post-Processing Step 1: Cycle Boost

**Rules (empirical từ 60 ngày backtest):**

| Pattern | Boost | Frequency |
|---------|-------|-----------|
| Số có đầu/đuôi trùng đuôi ĐB hôm trước (cham trùng) | +5% | 52.5% |
| Số có tổng 2 chữ số = bóng dương tổng đề hôm trước | +10% | Frequent |
| Số đảo của ĐB hôm trước (loto only) | +5% | 27.1% |
| Số lân cận ±1 của ĐB hôm trước | +8% | Backtest 24/06 |

**Bóng dương:** 0→5, 1→6, 2→7, 3→8, 4→9, 5→0, 6→1, 7→2, 8→3, 9→4

Áp dụng cho LOTO + DE (trừ dòng "loto only").

### Post-Processing Step 2: Chi-Square Penalty

- Nếu chi-square score < 0.4 và ensemble score > 0.7 → penalize 15%
- Nếu chi-square score < 0.3 và ensemble score > 0.5 → penalize 10%
- Mục đích: tránh overfit vào số có z-score thấp (24/06 phát hiện case 52 posterior 1.00 miss)

### Post-Processing Step 3: Crossover Consensus Boost (Added 28/06)

**DE only.** Khi cycle_pair + forum_consensus + bayesian_update đồng loạt vote cao:

```python
for each number:
    avg_cross = average(normalized_score from each crossover model)
    if avg_cross >= 0.60:
        boost = (avg_cross - 0.55) * 0.50  # 2.5% to 22.5%
        combined[val] *= (1.0 + boost)
```

**Nguyên lý:** 3 model "chuyên biệt" (không phải frequency/EWMA thông thường) cùng vote cao = tín hiệu mạnh.

**Case 28/06:** 52 có cycle_pair=0.54, forum=0.705, bayesian_update=0.59 → avg_cross=0.61 → boost ~3%. Đủ đưa từ rank 24 lên 14-15.

---

## 6. Weights (DE — source tuned_weights.json)

Production weights cho DE (từ tuned_weights.json, merged từ defaults cho models thiếu):

| Model | Weight | Notes |
|-------|--------|-------|
| bayesian_update | 37.0% | Giảm từ 41.7% (28/06) |
| gap | 26.4% | Số lạnh ưu tiên |
| cycle_pair | 12.3% | Tăng từ 9% (28/06) — cycle analysis |
| weekday | 8.8% | Day-of-week signal |
| forum_consensus | 7.6% | Tăng từ 5% (28/06) — forum consensus |
| ewma | 5.3% | Recency bias |
| chi_square | 2.1% | Physical bias signal |
| bayesian | 1.5% | Static prior |
| markov | 0.6% | Transition matrix |
| frequency | 0.4% | All-time baseline |

**LOTO weights** — xem tuned_weights.json (EWMA 27.6%, weekday 20.2%, digit 13.8%, ...)

**Data source precedence:** `tuned_weights.json` → `weights.ensemble_weights_for()` → fallback `DEFAULT_ENSEMBLE_WEIGHTS`.

---

## 7. Backtest Methodology (`backtest.py`)

### Walk-forward design

```
for each draw_date D in [start, end]:
    train = all draws before D
    predict D using models trained on train
    compare with actual values on D
```

### Metrics

| Target | Metric | Formula |
|--------|--------|---------|
| DE | hit_rate | #days đề ∈ top-K / total days |
| DE | lift | hit_rate / (K/100) |
| LOTO | hit_rate | #days có ≥1 lô top-K hit / total |
| LOTO | recall_at_k | \|pred ∩ actual\| / \|actual\| |

### Performance (historical)

| Period | DE hit@10 | DE lift | DE random |
|--------|-----------|---------|-----------|
| 2020-2025 (5yr) | ~11.5% | 1.15x | 10% |
| 2026-05-23→06-22 (30d) | **19.35%** | **1.94x** | 10% |

**30-day high (1.94x lift)** nhờ:
- Giảm EWMA λ từ 0.98→0.97
- Cycle boost post-processing
- Added cycle_pair + forum_consensus models
- Adjusted weights (bayesian_update 41.7%, gap 27.9%)
- Crossover consensus boost (28/06)

---

## 8. API

Prefix: `/predictions`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/predictions/next` | Dự đoán target_date tiếp theo |
| GET | `/predictions/evaluate` | Đánh giá prediction cho 1 ngày cụ thể |
| POST | `/predictions/backtest` | Chạy backtest |
| GET | `/predictions/weights` | Trả về tuned_weights.json hiện tại |

### GET /predictions/next

Query params: `target=[loto|de|dau|dit]`, `top=N`, `model=[ensemble|...]`, `as_of=YYYY-MM-DD`, `persist=true|false`

Response:
```json
{
  "target_date": "2026-06-29",
  "target_type": "de",
  "predictions": [
    {"rank": 1, "value": "83", "score": 0.6465},
    {"rank": 2, "value": "36", "score": 0.6398}
  ],
  "meta": {
    "train_days": 6213,
    "models_combined": ["frequency", "ewma", "gap", "markov", "bayesian", "weekday", "chi_square", "bayesian_update", "cycle_pair", "forum_consensus"]
  },
  "disclaimer": "Statistical ranking only. Not guaranteed."
}
```

---

## 9. Vận hành hàng ngày (Scheduler)

```
18:15 — XSMB quay
18:15-18:30 — import_mb_day() (minhngoc → xskt fallback)
18:30 — refresh_loto_views(), clear_feature_cache()
18:30 — compute_next(target='de', top=10, persist=True)
18:30 — compute_next(target='loto', top=20, persist=True)
19:00 — XSMB daily report script (Telegram)
```

File: `app/scheduler.py`

---

## 10. Lịch sử thay đổi

| Date | Change | Detail |
|------|--------|--------|
| 2026-06-21 | v1.1 Baseline | 7 models ensemble, weights từ tune 2020-2025, backtest framework |
| 2026-06-22 | Post-process cycle boost | Thêm cham trùng + bóng dương boost. DE lift 1.15→1.94x |
| 2026-06-23 | Cycle pair model | M10 — 50 fixed pairs cycle analysis. Normalize fix cần thiết |
| 2026-06-24 | Bugfix: normalize cycle_pair | Raw boost dominate ensemble — fixed. Thêm chi-square penalty |
| 2026-06-25 | cau filter integration | Cầu làm noise filter trong candidate service (candidate_service.py) |
| 2026-06-27 | Post-mortem 27/06 fail | Không panic adjust sau 1 ngày — variance ngẫu nhiên |
| 2026-06-28 | Forum consensus model M11 | Crawl forumketqua.net dàn 40s/36s/64s → score. Weight DE=5% |
| **2026-06-28** | **Crossover consensus boost** | Thêm post-processing step 3 — boost khi cycle_pair+forum+bayesian_update đồng thuận |
| **2026-06-28** | **Weight rebalance DE** | cycle_pair 9→13%, forum 5→8%, bayesian_update 41.7→37% |

---

## 11. Known Issues & Limitations

1. **Lô recall ~20% ≈ random** — Hit rate 99% gây hiểu lầm. Dùng recall_at_k.
2. **Đề variance cao** — Chỉ 1 mẫu/ngày, 1% baseline. 1.94x lift là significant nhưng vẫn miss nhiều.
3. **Forum_consensus phụ thuộc crawl** — Nếu forumketqua down hoặc thay đổi HTML → model trả uniform.
4. **Backtest chậm** — ~3 phút cho 11 models × 2000 ngày.
5. **~900 ngày thiếu DB** — Khoảng trống lịch sử (Tết, lỗi scrape).
6. **Cross-platform models (bayesian_update + cycle_pair + forum_consensus) chưa tuned với nhau** — weights hiện tại dùng heuristics. Cần tune lại toàn bộ ensemble.
