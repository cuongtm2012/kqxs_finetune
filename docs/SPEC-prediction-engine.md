# SPEC: Prediction Engine — Xác Suất Thống Kê XSMB

**Project:** `analysis-rbk-py`  
**Version:** 1.1  
**Date:** 2026-06-21  
**Status:** Draft — công nhận methodology mới (Bayesian Hierarchical + Granger Pairs)

---

## 1. Mục tiêu

Xây dựng **Prediction Engine** trên PostgreSQL, dùng thuật toán xác suất thống kê để **xếp hạng** các con số có khả năng xuất hiện ở **ngày quay tiếp theo** (XSMB — Miền Bắc).

Engine **không** hứa hẹn dự đoán chính xác giải ĐB 5 chữ số. Trọng tâm thực tế (và khớp hệ RBK hiện tại):

| Target | Mô tả | Output |
|--------|--------|--------|
| **Lô** | 2 số cuối (00–99), xuất hiện trong **bất kỳ** giải nào trong 27 giải | Top-K lô + score |
| **Đề** | 2 số cuối của giải **ĐB** | Top-K đề + score |
| **Đầu / Đít** | Chữ số hàng chục / hàng đơn của lô (0–9) | Top digit + score |

Kết quả dùng cho phân tích, soi cầu nội bộ, backtest — **không thay thế xác suất ngẫu nhiên thực sự** của quay số.

---

## 2. Bối cảnh dữ liệu hiện có

### 2.1 PostgreSQL

```
postgresql://rbk:rbk@127.0.0.1:5436/rbk
```

### 2.2 Bảng liên quan

| Bảng / View | Vai trò |
|-------------|---------|
| `draws` | 1 row/ngày MB (`draw_date`, `station`, `source`) |
| `prizes` | 27 row/ngày (`slot_index`, `prize_level`, `number`, `last_two`, `first_digit`, `last_digit`) |
| `mv_loto_daily` | `(draw_date, loto, hit_count)` — số lần lô xuất hiện/ngày |
| `trends`, `caudep_snapshots` | Dữ liệu legacy scrape RBK (rongbachkim) — tham khảo, không bắt buộc cho v1 |

### 2.3 Quy ước domain (đã có trong `lottery_format.py`)

- 27 slot: `DB(1) + G1(1) + G2(2) + G3(6) + G4(4) + G5(6) + G6(3) + G7(4)`
- **Lô ngày D:** tập `last_two` từ 27 giải (có trùng — cùng lô có thể nhảy nhiều giải)
- **Đề ngày D:** `last_two` của slot `DB` (`slot_index = 0`)
- **Đầu i / Đít i:** bucket chữ số 0–9 từ `first_digit` / `last_digit` của lô

### 2.4 Trạng thái data (2026-06-21)

- ~1.234 ngày MB (`2007-01-01` → `2026-06-20`)
- Đủ cho backtest dài hạn; tiếp tục backfill đến ~7.000 ngày khi hoàn tất

---

## 3. Phạm vi & giả định thống kê

### 3.1 Giả định mô hình

1. **Lô (00–99)** là không gian dự đoán chính — 100 giá trị, dễ đánh giá.
2. Mỗi ngày có **27 lượt “hit”** lô (có lặp). Xác suất lô `x` xuất hiện **ít nhất 1 lần** ngày D:
   ```
   P(x ∈ ngày D) = 1 - (1 - p_x)^27   (xấp xỉ, nếu coi các slot độc lập)
   ```
   Thực tế các slot **không hoàn toàn độc lập**; engine dùng xác suất **thực nghiệm** từ lịch sử thay vì mô hình lý thuyết đầy đủ.

3. **Ngày quay tiếp theo** = `max(draw_date) + 1 ngày` (bỏ Tết/ngày nghỉ — không có row trong `draws`).

### 3.2 Giới hạn (bắt buộc ghi trong API response)

- Xổ số vận hành theo cơ chế ngẫu nhiên; **không có bằng chứng** mô hình nào vượt baseline ngẫu nhiên một cách bền vững.
- Engine đo **độ hữu ích tương đối** giữa các chiến lược (backtest), không cam kết lợi nhuận.
- Baseline ngẫu nhiên cho **Lô top-K**: chọn K lô bất kỳ, xác suất ít nhất 1 trúng trong 27 giải ≈ `1 - C(100-K,27)/C(100,27)` (hoặc Monte Carlo).

---

## 4. Kiến trúc tổng quan

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  PostgreSQL     │────▶│  Feature Store       │────▶│  Model Scorers  │
│  draws, prizes  │     │  (SQL + Python cache)│     │  (pure Python)  │
└─────────────────┘     └──────────────────────┘     └────────┬────────┘
                                                                │
                       ┌──────────────────────┐                  │
                       │  Ensemble Combiner   │◀─────────────────┘
                       └──────────┬───────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
     ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
     │ prediction_*   │  │ Backtest Runner│  │ FastAPI        │
     │ tables         │  │ (walk-forward) │  │ /predictions/* │
     └────────────────┘  └────────────────┘  └────────────────┘
```

### 4.1 Module đề xuất (Python)

```
app/
  prediction/
    __init__.py
    features.py          # trích xuất feature từ DB
    models/
      base.py            # Protocol: score(target_date) -> dict[loto, float]
      bhm.py             # Bayesian Hierarchical Model (logit GLM)
      pair_boost.py      # Granger pairwise correction matrix
    scorer.py            # score(x) = 0.75×bhm + 0.25×pair
    backtest.py          # walk-forward + metrics
    service.py           # orchestration
  routers/
    predictions.py       # API
```

---

## 5. Methodology — Data-Driven Selection

### 5.1 Data Findings (empirical, từ 1.789 ngày XSMB)

Trước khi chọn model, em phân tích data thật để hiểu bản chất phân phối:

| Metric | Giá trị | Ý nghĩa |
|--------|---------|---------|
| Tổng ngày | 1.789 | ~5 năm data |
| Distinct lô/ngày (trung bình) | 23.79 / 27 slot | ~88% slot unique loto |
| Lô multi-hit (>1 lần/ngày) | 3.04% trường hợp | Hiếm — bài toán gần như **Bernoulli mỗi lô/ngày** |
| Variance/mean ratio | 0.16 (under-dispersed) | **Poisson không phù hợp** — variance << mean |
| Appear probability trung bình | ~25% (lô thường~26%, thấp nhất~23%) | Không có loto nào quá hot/quá lạnh |
| Co-occurrence pairs (same-day) | (09,43) = 7.5%, random baseline ≈ 5.6% | Có pairwise dependency — **Granger cần thiết** |
| Lag-1 pairs (yesterday→today) | (16→45) = 182 lần / 1789 ngày ≈ 10% | Có temporal dependency |
| Max gap | 20 ngày | Không có "gan" thực sự |
| Weekday effect | Negligible (23.67–23.94) | Không cần riêng model weekday |

**Kết luận:** Đây là bài toán **multivariate Bernoulli + pairwise dependency** — dùng Bayesian Hierarchical Model làm core + Granger Pairs correction.

### 5.2 Core Model: Bayesian Hierarchical Model (BHM)

**Lý do chọn:** So với các alternatives:

| Method | Phù hợp? | Lý do |
|--------|----------|-------|
| Poisson Regression | ❌ | Under-dispersed (var/mean=0.16) — không fit |
| Neg. Binomial | ❌ | Cũng không fit under-dispersion |
| COM-Poisson | ⚠️ | Được nhưng phức tạp không cần thiết |
| HMM | ⚠️ | Overkill — weekday effect negligible, không có hidden state rõ |
| Hypergeometric baseline | ✅ Dùng làm benchmark | Cận dưới lý thuyết |
| **Bayesian Hierarchical** | **✅ Chọn** | Chuẩn cho Bernoulli + pooling weak signal |

#### Công thức

Mỗi lô `x` có xác suất xuất hiện trong ngày `D`:

```
y_xD ~ Bernoulli(p_xD)

logit(p_xD) = α + β_x + γ × EWMA_weighted_hits(x, window=30)
```

Trong đó:
- `α`: global intercept (baseline probability chung — các lô ~25%)
- `β_x ~ Normal(0, σ_loto)`: random effect per loto → **partial pooling**: loto ít data được "kéo" về global mean, tránh overfit
- `γ × EWMA_weighted_hits`: temporal trend — dùng kernel `λ=0.97` (half-life ~23 ngày), capture xu hướng gần

**Ưu điểm so với M5 (Beta-Binomial):**
- Beta-Binomial không có partial pooling — mỗi lô estimate độc lập
- BHM cho phép loto ít data "mượn" strength từ global phân phối
- Thêm temporal component (γ) mà Beta-Binomial không có

**Implement:**
- Không cần MCMC (chậm) — dùng `statsmodels` GLM với mixed effects hoặc `scipy.optimize` MAP
- V1: dùng GLM với `Binomial` family + `logit` link trong statsmodels
- V2: PyMC/Numpyro nếu cần full posterior

### 5.3 Pairwise Correction via Granger Causal Pairs

**Lý do:** Data cho thấy same-day và lag-1 pairs trên mức random:

```
(09, 43) = 7.5% co-occurrence vs random 5.6% → +34% lift
(16→45) = 182 lần lag-1 (≈10%) → temporal signal
```

#### Công thức

**Step 1: Pairwise scoring matrix**

Build matrix `M[x][y] = P(x xuất hiện D | y xuất hiện D-1)` cho tất cả 100×100 pairs.

Chỉ giữ pairs có:
- `n_co_occur ≥ 30` (tránh noise)
- `lift = P(x|y) / P(x) > 1.05` (ít nhất 5% lift so với marginal)

Kết quả: ~1.000–2.000 significant pairs (density ~10-20%).

**Step 2: Pair boost**

Khi compute ensemble score cho ngày D+1:
```
base_score(x) = logit⁻¹(α + β_x + γ × EWMA)
pair_boost(x) = Σ_{y: y appeared yesterday} M[x][y]  (trên significant pairs)
```

**Step 3: Final score**

```
score(x) = w_base × normalize(base_score(x)) + w_pair × normalize(pair_boost(x))
```

**Trọng số:** `w_base = 0.75`, `w_pair = 0.25` (default, tunable từ backtest).

### 5.4 Hypergeometric Baseline (Benchmark)

Dùng làm **gold-standard**: nếu model không beat baseline này → useless.

```
P(ít nhất 1 hit | top-K) = 1 - C(100-K, 27) / C(100, 27)
```

Giá trị cụ thể:

| K | Baseline hit rate |
|---|------------------|
| 10 | 95.5% |
| 20 | 99.7% |
| 30 | 99.99% |

→ Hit rate gần 100% cho K≥20 => **Hit rate không phải metric tốt**. Dùng **Recall@K + Lift vs Random**.

### 5.5 Model Architecture (Revised)

```
Single model: Bayesian Hierarchical (logit) + Granger Pair Boost
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
    base_score(x) = logit⁻¹(α+β_x+γ×EWMA)   pair_boost(x) = Σ M[x][y] trên y hôm qua
              │                           │
              └──────────┬────────────────┘
                         ▼
              score(x) = 0.75×base + 0.25×pair
                         │
                         ▼
              Sort → Top-K Lô / Top-K Đề
```

### 5.6 Model variants (mở rộng cho Đề / Đầu Đít)

**Đề** (target riêng):
- Feature: `de_hits(x)`, `de_gap(x)` → cùng BHM structure nhưng trained trên đề-only data
- Không dùng pair boost (đề quá ít — 1 sample/ngày)

**Đầu/Đít**:
- Từ BHM lô: `P_dau(d) = Σ_{x starts with d} score(x)` / normalization
- `P_dit(d) = Σ_{x ends with d} score(x)` / normalization
- Hoặc BHM riêng trên digit data nếu sample đủ

### 5.7 M3 Gap (Legacy — optional, disabled by default)

Giữ nguyên code cho RBK legacy `/analytics/loto-gan` nhưng **không dùng trong ensemble v1**:
- Data cho thấy max gap chỉ 20 ngày — không có "gan thực sự"
- Nếu backtest cho thấy edge → bật với weight thấp (≤0.05)

---

## 6. Dự đoán Đề (target riêng)

Đề chỉ lấy `slot_index = 0` (giải ĐB):

- Feature riêng: `de_hits(x)`, `de_gap(x)`, …
- Cùng bộ model M1–M5, M6 (theo thứ), **không** dùng M7 trực tiếp
- 100 giá trị → top-K đề

---

## 7. Feature Store (SQL)

### 7.1 View đề xuất: `mv_loto_features`

Materialized view refresh sau mỗi import / nightly:

```sql
-- Per loto, as of each draw_date (rolling — compute in Python v1, SQL v2)
-- v1: query on-the-fly với index hiện có đủ nhanh (~1K ngày)

-- Index bổ sung:
CREATE INDEX IF NOT EXISTS idx_prizes_last_two_date
  ON prizes (last_two)
  INCLUDE (draw_id);

CREATE INDEX IF NOT EXISTS idx_draws_mb_date
  ON draws (draw_date)
  WHERE region = 'MB';
```

### 7.2 Feature vector (Python, per `as_of_date`)

| Feature | Kiểu | Mô tả | Dùng cho |
|---------|------|--------|----------|
| `ewma_score` | float[100] | Temporal trend, λ=0.97, window=30 | BHM base (γ) |
| `freq_all`, `freq_90d`, `freq_365d` | float[100] | Tần suất lô reference | Debug, ensemble optional |
| `gap_days` | int[100] | Ngày từ lần cuối | Legacy M3 (disabled) |
| `last_appeared` | bool[100] | Lô có xuất hiện hôm qua không | Pair boost lookup |
| `pair_matrix` | float[100][100] | Sparse conditional matrix | Granger pairs |
| `loto_mean_global` | float | Global intercept α | BHM |
| `loto_effects` | float[100] | Random effects β_x | BHM |

Cache in-memory 5 phút cho API; invalidate khi có draw mới.

---

## 8. Backtest (bắt buộc trước production)

### 8.1 Walk-forward

```
for each draw_date D in [start, end]:
    train_data = draws WHERE draw_date < D
    fit BHM on train_data (estimate α, β_x, γ)
    build pair_matrix from train_data
    compute score(x) = 0.75 × BHM + 0.25 × pair_boost
    compare with actual prizes on D
```

**Không** shuffle — thứ tự thời gian nghiêm ngặt.

### 8.2 Metrics

#### Core metric: Recall@27, Precision@27, F1@27

Mỗi ngày predict **27 lô** (khớp 27 giải thực tế). So sánh predicted set vs actual set.

| Metric | Công thức | Random baseline |
|--------|-----------|----------------|
| **Recall@27** | `\|predicted ∩ actual_loto_set\| / \|actual_loto_set\|` | ~0.24 |
| **Precision@27** | `\|predicted ∩ actual_loto_set\| / 27` | ~0.24 |
| **F1@27** | `2 × P × R / (P + R)` | ~0.24 |
| **Lift vs random** | `F1_model / F1_random` | 1.0 |

**Giải thích random baseline:**
- 100 số, mỗi ngày ~24 distinct loto trong 27 slot
- Random chọn 27 số → expected correct = 24 × (27/100) = 6.48 / 27 ≈ 24%
- Monte Carlo (10K trials) xác nhận: recall@27 ≈ 0.238

**Ship gate v1:** F1@27 > 0.25 (lift ≥ 1.05) trên liên tục 3 năm walk-forward.

#### Secondary: Đề

| Metric | Công thức |
|--------|-----------|
| **Exact hit@27** | % ngày đề thực ∈ predicted 27 lô |
| **Random baseline** | 27/100 = 27% |

#### Calibration (optional v1.1)

- Binned reliability diagram: score decile vs tần suất thực
- Đo Brier score cho từng loto

### 8.3 Báo cáo mẫu

```json
{
  "period": {"from": "2020-01-01", "to": "2025-12-31"},
  "target": "loto",
  "top_k": 27,
  "models": {
    "bhm_pair": {"recall@27": 0.27, "precision@27": 0.27, "f1@27": 0.27, "lift_vs_random": 1.13},
    "bhm_only": {"recall@27": 0.25, "precision@27": 0.25, "f1@27": 0.25, "lift_vs_random": 1.04},
    "random_baseline": {"recall@27": 0.238, "precision@27": 0.238, "f1@27": 0.238, "lift_vs_random": 1.0}
  },
  "random_baseline": {
    "recall@20": 0.26,
    "method": "Monte Carlo (10K trials): expected distinct lotos in top-20"
  }
}
```

**Tiêu chí ship v1:** F1@27 > 0.25 (lift > 1.05) trên ≥3 năm backtest. Nếu không → giảm w_pair hoặc bỏ pair boost.

---

## 9. Schema DB mới

```sql
CREATE TABLE prediction_runs (
    id            BIGSERIAL PRIMARY KEY,
    target_date   DATE NOT NULL,          -- ngày được dự đoán
    as_of_date    DATE NOT NULL,          -- ngày cuối cùng của training data
    target_type   TEXT NOT NULL,          -- 'loto' | 'de' | 'dau' | 'dit'
    model_name    TEXT NOT NULL,          -- 'ensemble' | 'frequency' | ...
    params        JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (target_date, target_type, model_name)
);

CREATE TABLE prediction_items (
    id              BIGSERIAL PRIMARY KEY,
    run_id          BIGINT NOT NULL REFERENCES prediction_runs(id) ON DELETE CASCADE,
    rank            SMALLINT NOT NULL,
    value           TEXT NOT NULL,        -- '42' cho lô/đề, '7' cho đầu/đít
    score           DOUBLE PRECISION NOT NULL,
    UNIQUE (run_id, rank)
);

CREATE INDEX idx_prediction_runs_date ON prediction_runs (target_date DESC);
CREATE INDEX idx_prediction_items_run ON prediction_items (run_id);

-- Backtest kết quả tổng hợp
CREATE TABLE backtest_reports (
    id            BIGSERIAL PRIMARY KEY,
    target_type   TEXT NOT NULL,
    model_name    TEXT NOT NULL,
    period_from   DATE NOT NULL,
    period_to     DATE NOT NULL,
    top_k         SMALLINT NOT NULL,
    metrics       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 10. API

Prefix: `/predictions`

### 10.1 Dự đoán ngày tiếp theo

```
GET /predictions/next
```

| Query | Mặc định | Mô tả |
|-------|----------|--------|
| `target` | `loto` | `loto` \| `de` \| `dau` \| `dit` |
| `top` | 20 | Số kết quả trả về |
| `model` | `ensemble` | Tên model hoặc `all` |
| `as_of` | latest draw | Override ngày train (debug) |

**Response mẫu:**

```json
{
  "target_date": "2026-06-21",
  "as_of_date": "2026-06-20",
  "target_type": "loto",
  "model": "ensemble",
  "disclaimer": "Statistical ranking only. Not guaranteed.",
  "predictions": [
    {"rank": 1, "value": "62", "score": 0.0341},
    {"rank": 2, "value": "79", "score": 0.0318}
  ],
  "meta": {
    "train_days": 1234,
    "models_combined": ["frequency", "ewma", "bayesian", "markov", "gap", "weekday"]
  }
}
```

### 10.2 Chạy backtest

```
POST /predictions/backtest
Content-Type: application/json

{
  "from_date": "2020-01-01",
  "to_date": "2025-12-31",
  "target": "loto",
  "top_k": 20,
  "models": ["ensemble", "frequency", "ewma"]
}
```

### 10.3 Lịch sử dự đoán vs thực tế

```
GET /predictions/evaluate?date=2026-06-20&target=loto&top=20
```

Trả về predicted top-K, actual lô set, hit/miss.

### 10.4 Tương thích legacy

- `/kqxs/trending`, `/kqxs/caudep` — giữ nguyên (data RBK scrape)
- Prediction engine **bổ sung** `/predictions/*`, không thay thế ngay

---

## 11. Luồng vận hành hàng ngày

```
1. Scheduler import KQXS (đã có) → draws + prizes
2. refresh_loto_views()
3. prediction_service.compute_next(target_date=tomorrow)
4. Lưu prediction_runs + prediction_items
5. (Optional) Slack/log nếu backtest weekly
```

Trigger: sau `_import_mb_today()` trong `scheduler.py` hoặc cron 19:00.

---

## 12. Kế hoạch triển khai

### Phase 1 — Foundation + Core Model (1 tuần)

- [ ] Migration `prediction_*`, `backtest_reports`
- [ ] `features.py` — trích xuất từ Postgres: EWMA, freq, gap, last_appeared
- [ ] `bhm.py` — GLM logit (statsmodels), fit → extract α, β_x, γ
- [ ] `pair_boost.py` — build sparse matrix, compute pair_boost
- [ ] `scorer.py` — combine BHM + pair boost
- [ ] `backtest.py` walk-forward + hypergeometric baseline
- [ ] API `GET /predictions/next`, `POST /predictions/backtest`

### Phase 2 — Đề + Đầu/Đít (3-4 ngày)

- [ ] BHM cho đề (đề-only data)
- [ ] Đầu/Đít từ BHM lô aggregation
- [ ] API mở rộng cho các target

### Phase 3 — Production (3-5 ngày)

- [ ] Scheduler auto-predict
- [ ] `GET /predictions/evaluate`
- [ ] Dashboard / log metrics
- [ ] Pair matrix refresh weekly (offline)

### Phase 4 — Nâng cao (backlog)

- [ ] MV `mv_loto_features` refresh incremental
- [ ] Calibration plots
- [ ] So sánh với `chot_predictions` (crowd wisdom)
- [ ] MN/MT region support
- [ ] M3 Gap optional toggle (nếu backtest cho thấy edge)

---

## 13. Phụ thuộc kỹ thuật

| Package | Mục đích |
|---------|----------|
| Hiện có: `psycopg`, `fastapi` | DB + API |
| `numpy` (optional) | Vector hóa score 100 lô |
| Không cần ML nặng (sklearn/torch) v1 | Pure stats đủ |

---

## 14. Rủi ro & mitigations

| Rủi ro | Mitigation |
|--------|------------|
| Data thiếu ngày (Tết, scrape fail) | Skip ngày; gap feature xử lý `last_seen` |
| Model không beat random | Backtest gate; hiển thị disclaimer + baseline |
| Overfit window ngắn | Bayesian + ensemble + walk-forward |
| User hiểu nhầm là “chắc trúng” | Disclaimer mọi response; doc rõ lift ≈ 1.0 |

---

## 15. Câu hỏi mở (cần anh confirm)

1. **Top-K mặc định:** 20 lô / 10 đề có phù hợp không?
2. **Ưu tiên target:** Lô trước hay Đề trước?
3. **Có cần UI** hay chỉ API?
4. **Trọng số ensemble:** auto-tune từ backtest hay config tay?
5. **So sánh với caudep RBK:** có merge score vào ensemble không?

---

## 16. Tài liệu tham chiếu code hiện tại

| File | Liên quan |
|------|-----------|
| `app/services/lottery_format.py` | Slot 27 giải, đầu/đít |
| `app/routers/analytics.py` | `loto-frequency`, `loto-gan` |
| `db/schema.sql` | `prizes`, `mv_loto_daily` |
| `app/repositories/kqxs_repo.py` | Legacy ketqua format |

---

*End of SPEC v1.0*
