# kqxs_finetune

XSMB (Miền Bắc) lottery analytics & **Stats Engine** — Python + PostgreSQL.

Migrate từ stack Java/MongoDB (`analysis-rbk`) sang FastAPI/Postgres. API chính hiện tại là **Stats Engine** (thống kê mô tả + candidate pool). Code prediction engine (`app/prediction/`) vẫn giữ để tham khảo nhưng **không còn mount router / scheduler**.

**Repo:** https://github.com/cuongtm2012/kqxs_finetune

---

## Stack

| Layer | Công nghệ |
|-------|-----------|
| API | FastAPI + Uvicorn (port `8081`) |
| DB | PostgreSQL 16 (Docker, port `5436`) |
| ORM/DB | psycopg3 + connection pool |
| Scheduler | APScheduler |
| Scrape | BeautifulSoup + requests/curl fallback |
| Nguồn KQXS MB | **minhngoc.net.vn** (chính), xskt.com.vn (fallback) |

---

## Cấu trúc project

```
app/
  main.py                 # FastAPI entry, lifespan, scheduler
  config.py               # RBK_* env settings
  db.py                   # Postgres pool helpers
  prediction/             # Legacy prediction engine (không active)
    ...
  repositories/           # draw, kqxs, prediction, rbk, user
  routers/                # kqxs, rbk, analytics, stats, ums
  services/               # stats_service, candidate_service, intersection_service, scrape, import
db/
  schema.sql              # Full schema + prediction tables
  migrations/002_prediction.sql
scripts/
  backfill_xsmb.py        # Backfill lịch sử MB
  tune_ensemble_weights.py
  migrate_mongo_to_pg.py  # One-time Mongo → PG
docs/
  SPEC-stats-engine-v4.2.md    # Spec hiện tại
  SPEC-stats-engine-v4.1.md
  SPEC-stats-engine-v4.md
  SPEC-stats-engine-v2.md
  SPEC-prediction-engine.md   # legacy
```

---

## Quick start

```bash
# 1. Postgres
docker compose up -d

# 2. Python env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env

# 3. Chạy API (scheduler bật mặc định)
.venv/bin/python run.py
# → http://localhost:8081
```

### Biến môi trường (`.env`)

| Biến | Mặc định | Mô tả |
|------|----------|--------|
| `RBK_PORT` | `8081` | API port |
| `RBK_DATABASE_URL` | `postgresql://rbk:rbk@127.0.0.1:5436/rbk` | Postgres |
| `RBK_ENABLE_SCHEDULER` | `true` | Cron import KQXS (không còn auto-predict) |

### Backfill lịch sử

```bash
.venv/bin/python scripts/backfill_xsmb.py --from 2007-01-01 --delay 0.3
curl -X POST http://localhost:8081/analytics/refresh-views
```

### Tune lại ensemble weights

```bash
.venv/bin/python scripts/tune_ensemble_weights.py --from 2020-01-01 --to 2025-12-31
# Ghi đè app/prediction/tuned_weights.json, reload tự động lần chạy sau
```

---

## API

### Health & analytics

| Method | Endpoint | Mô tả |
|--------|----------|--------|
| GET | `/health` | Postgres connectivity |
| GET | `/analytics/stats` | Số ngày MB, range, prizes |
| GET | `/analytics/loto-frequency` | Top lô theo tần suất |
| GET | `/analytics/loto-gan` | Lô gan (`?loto=88`) |
| POST | `/analytics/refresh-views` | Refresh `mv_loto_daily` |

### Stats Engine (`/stats/*`)

| Method | Endpoint | Mô tả |
|--------|----------|--------|
| GET | `/stats/pairs` | Same-day / lag-1 pairs (`type`, `min_lift`, `min_occ`) |
| GET | `/stats/gap` | Gap chi tiết 1 loto |
| GET | `/stats/gap/hot-cold` | Ranking gan/nóng |
| GET | `/stats/gap/nhip` | Tần suất nhịp |
| GET | `/stats/gap/max-cycle` | Top gần max cycle |
| GET | `/stats/digits` | Phân phối đầu/đít |
| GET | `/stats/digits/de-dau` | Chu kỳ đầu đề |
| GET | `/stats/lo-roi` | Lô rơi sau đề |
| GET | `/stats/calendar` | Stats theo thứ/ngày/tháng |
| GET | `/stats/calendar/loto-theo-db` | Loto hay về sau đề X |
| GET | `/stats/calendar/loto-theo-loto` | Loto hay về sau loto X |
| GET | `/stats/max-dan` | Dàn 3–5 số cùng về (`size`, `min_co_occur`) |
| GET | `/stats/conditional-frequency` | ĐB hôm qua → tần suất ĐB hôm sau |
| GET | `/stats/rbk-cau` | Crawl cầu rongbachkim |
| GET | `/stats/intersection` | **v4** CF ∩ RBK cầu lặp (`min_cf_lift`, `min_rbk_cau`) |
| GET | `/stats/intersection/evaluate` | Đánh giá intersection vs KQXS 1 ngày (đề loto) |
| POST | `/stats/intersection/backtest` | Backtest intersection + so sánh CF/RBK alone |
| GET | `/stats/candidates` | Candidate pool (`target=loto\|de`, lift-weighted) |
| GET | `/stats/candidates/evaluate` | So prediction vs KQXS 1 ngày |
| POST | `/stats/candidates/backtest` | Backtest candidate vs random baseline |

Query mẫu:

```bash
curl "http://localhost:8081/stats/pairs?type=lag-1&min_lift=1.1&limit=20"
curl "http://localhost:8081/stats/conditional-frequency?db_loto=60&limit=10"
curl "http://localhost:8081/stats/rbk-cau?limit=5"
curl "http://localhost:8081/stats/intersection?min_cf_lift=3&min_rbk_cau=4"
curl "http://localhost:8081/stats/intersection/evaluate?target_date=2026-06-21"
curl -X POST http://localhost:8081/stats/intersection/backtest \
  -H 'Content-Type: application/json' -d '{"days":30}'
curl "http://localhost:8081/stats/candidates?target=de"          # default top=10
curl "http://localhost:8081/stats/candidates/evaluate?target_date=2026-06-21&target=loto"
curl -X POST http://localhost:8081/stats/candidates/backtest \
  -H 'Content-Type: application/json' -d '{"days":90,"target":"de"}'
curl "http://localhost:8081/stats/max-dan?size=3&min_co_occur=20"
```

Chi tiết: [docs/SPEC-stats-engine-v4.2.md](docs/SPEC-stats-engine-v4.2.md).

### Predictions (legacy — không mount)

Router `/predictions/*` đã thay bằng `/stats/*`. Code trong `app/prediction/` vẫn có thể chạy thủ công qua script nếu cần backtest.

```bash
# Chỉ khi mount lại router predictions hoặc chạy script
.venv/bin/python scripts/tune_ensemble_weights.py --from 2020-01-01 --to 2025-12-31
```

### Legacy (tương thích Java RBK)

| Prefix | Mô tả |
|--------|--------|
| `/kqxs/*` | ketqua, chotkq, trending, caudep, ketquamn/mt |
| `/rbk/*` | Trigger import thủ công |
| `/ums/login` | User login |

---

## Prediction engine (tóm tắt)

| Model | Tên | Target |
|-------|-----|--------|
| M1 | `frequency` | lô, đề, đầu, đít |
| M2 | `ewma` | tất cả |
| M3 | `gap` | tất cả |
| M4 | `markov` | tất cả |
| M5 | `bayesian` | tất cả |
| M6 | `weekday` | tất cả (fallback M1 nếu ít sample) |
| M7 | `digit` | lô, đầu, đít |
| M8 | `ensemble` | tổng hợp (load từ `tuned_weights.json`) |

**Top-K mặc định:** lô 20, đề 10, đầu/đít 5.

Chi tiết thuật toán, backtest, schema: [docs/SPEC-prediction-engine.md](docs/SPEC-prediction-engine.md).

---

## Kết quả backtest (đã đo)

### Tune dài hạn 2020–2025 (2.146 ngày)

| Target | Metric | Ensemble | Random baseline |
|--------|--------|----------|-----------------|
| Lô top-20 | Recall@20 | **20.34%** | ~20% |
| Lô top-20 | Hit rate (≥1 lô/ngày) | 99.8% | ~99%+ |
| Đề top-10 | Hit rate | **11.46%** | 10% |

**Kết luận:** Lô gần ngẫu nhiên; đề hơi trên random (~lift 1.15×). Không nên kỳ vọng “dự đoán chính xác cao”.

### Tune 1 năm gần (2025-06 → 2026-06, 362 ngày)

| Target | Trọng số cũ (2020–25) | Tune 1 năm |
|--------|----------------------|------------|
| Lô recall@20 | 20.03% | **20.61%** |
| Đề hit@10 | 9.94% (dưới random) | **12.15%** |

Trọng số dài hạn **không** tối ưu cho giai đoạn gần, đặc biệt với đề.

---

## Scheduler (khi `RBK_ENABLE_SCHEDULER=true`)

| Giờ | Job | Ghi chú |
|-----|-----|---------|
| 18:15–18:31 | Import XSMB hôm nay | minhngoc → xskt fallback |
| 19:00 | RSS MN/MT | |
| */25,55 | chotkq, trend | **Cần rongbachkim** — thường fail |
| 20:00 | caudep | **Cần rongbachkim** — thường fail |

> Auto-predict đã **tắt** (Stats Engine thay thế prediction).

---

## Trạng thái data (cập nhật khi deploy)

| Metric | Giá trị |
|--------|---------|
| Ngày MB | ~6.213 (`2007-01-01` → `2026-06-20`) |
| Nguồn chính | `minhngoc` (~5.944 ngày) |
| Migrate Mongo | `mongo-migrate` (~269 ngày) |
| Thiếu | ~900 ngày (Tết, scrape fail, ngày nghỉ) |

---

## Vấn đề còn tồn tại

### Data & scrape

1. **xskt.com.vn bị CrowdSec Captcha** từ IP server — không dùng được làm nguồn chính; minhngoc ổn định hơn.
2. **Backfill chưa đủ ~7.000 ngày** — còn gap ngày nghỉ/lỗi scrape.
3. **rongbachkim.com bị chặn** — chotkq, trend, caudep scheduler **không hoạt động** trên mạng hiện tại.
4. **MN/MT** chỉ có RSS gần đây, chưa backfill full.

### Prediction

5. **Lô recall ~20%** — gần random; hit rate 99% không phải metric “giỏi”.
6. **Trọng số tune 2020–25 kém trên 1 năm gần** (đề 9.9% vs random 10%).
7. **Chưa có profile trọng số “recent”** — chỉ 1 file `tuned_weights.json` (dài hạn).
8. **Backtest full period rất chậm** (~10+ phút) — tuning subsample 800 ngày cho dau/dit.
9. **Gap model (M3)** về lý thuyết là gambler's fallacy — giữ vì legacy RBK.

### Kỹ thuật

10. **Feature cache in-memory** — không TTL 5 phút như SPEC; chỉ `clear_feature_cache()` sau import.
11. **`mv_loto_features` SQL** — chưa implement; features tính on-the-fly trong Python.
12. **Không có unit tests** trong repo.
13. **Python 3.9** — tránh syntax `str | None` (đã dùng `Optional` trong `db.py`).
14. **macOS LibreSSL** — `requests` SSL có thể fail; `http_util` fallback `curl`.

### Chưa làm (backlog)

- UI / dashboard metrics
- Calibration plots
- So sánh với `chot_predictions` (crowd wisdom)
- MN/MT prediction
- Auto weekly backtest + alert
- Geometric gap survival (M3 v1.1)

---

## Docs

- [SPEC Stats Engine v2](docs/SPEC-stats-engine-v2.md) — API stats, candidate pool, implementation
- [SPEC Prediction Engine](docs/SPEC-prediction-engine.md) — legacy, thuật toán backtest
