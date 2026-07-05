# Design: Forum Expert Win Rate v2

## Vấn đề (root cause map)

```
expert_weights.json (manual track record)
        │  expert_weight()  ──► sort bảng / scoring đề xuất
        ▼
User thấy "top 1" (himle79 W=0.94)

expert_win_rates (DB, period 2026-06)
        │  expert_performance()  ──► cột Hiệu suất
        ▼
himle79: không có row (0 pick tháng 6 trong DB)
        │ fallback
        ▼
run_backtest(90): dan_40s 1/2 → 50%  OR  dan_board lookup "dan_de" → null → "—"
```

**Hai pipeline độc lập** chưa được document rõ trong UI và chưa align pick_type / dedupe.

## Kiến trúc mục tiêu

```
┌─────────────────────────────────────────────────────────────────┐
│  DATA LAYER                                                      │
├─────────────────────────────────────────────────────────────────┤
│  backfill_forum_picks_month (--month 2026-06, extended)         │
│       → forum_user_picks (đủ ngày + topic chăn nuôi dàn)       │
│                                                                  │
│  seed_expert_win_rates (--period 2026-06 | rolling_90d)         │
│       → expert_win_rates + expert_pick_results (audit)          │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│  COMPUTE LAYER (single source of truth for hit/total)           │
├─────────────────────────────────────────────────────────────────┤
│  pick_hit()              ← shared (unchanged)                   │
│  _dedupe_day_picks()     ← shared helper (NEW)                  │
│    · canonical_username                                         │
│    · latest posted_at per (user, pick_type) per day             │
│                                                                  │
│  expert_winrate_service.compute_period_stats()                  │
│  expert_backtest_service.run_backtest()  ← uses shared dedupe   │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│  LOOKUP LAYER                                                    │
├─────────────────────────────────────────────────────────────────┤
│  expert_weight(user, pick_type)                                 │
│    · pick_type-specific key OR category fallback OR 0.3         │
│    · NO cross-category default (dan → stl)                      │
│                                                                  │
│  expert_performance(user, pick_type, period)                    │
│    · pick_type exact → dan family → default → backtest          │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│  API / UI                                                        │
├─────────────────────────────────────────────────────────────────┤
│  recommendations: live_experts, dan_board, de_by_expert         │
│  extension: W column + Hiệu suất column + period hint         │
└─────────────────────────────────────────────────────────────────┘
```

## Quyết định thiết kế

### D1 — Tách W và win rate (không gộp)

| Khái niệm | Nguồn | Mục đích |
|-----------|-------|----------|
| **W** | `expert_weights.json` | Trọng số scoring đề xuất (có thể manual / blend backtest) |
| **Hiệu suất** | `expert_win_rates` DB | Hiển thị hit/total đo được từ picks + KQXS |

Sort mặc định giữ **W desc** (hành vi scoring không đổi). UI thêm toggle sort theo `rate_pct` để audit.

### D2 — Pick type families

```python
DAN_FAMILY = frozenset({"dan_de", "dan_40s", "dan_36s", "dan_64s"})
LOTO_FAMILY = frozenset({"stl", "btl", "muc_lo"})
DE_META_FAMILY = frozenset({"de_cham", "de_dau", "de_tong", "btd", "btd_dau", "btd_de", "std_de"})
```

**Performance lookup** (thứ tự):

1. `(user, pick_type, period)`
2. Nếu `pick_type == "dan_de"`: thử `dan_40s`, `dan_36s`, `dan_64s` (ưu tiên `total` lớn nhất)
3. `(user, "default", period)`
4. `run_backtest(days)` với cùng pick_type chain
5. `null`

**Weight lookup** (thứ tự):

1. `(user, pick_type)` trong JSON
2. Nếu `pick_type in LOTO_FAMILY` và không có key → `default` **chỉ khi** `default` không đến từ category dàn thuần (xem D3)
3. Nếu `pick_type in DAN_FAMILY` → `dan_de` hoặc `default`
4. Unknown → `0.3`

### D3 — Chặn cross-category weight leak

`expert_weights.json` entry:

```json
"himle79": {"default": 0.94, "dan_de": 0.94}
```

- `weight("himle79", "dan_40s")` → `0.94` (via `dan_de` family)
- `weight("himle79", "stl")` → **`0.3`** (không có key `stl`, `default` chỉ áp dụng khi không có family conflict)

Implementation: nếu request `pick_type ∉ keys(user)` và `pick_type ∈ LOTO_FAMILY` và user chỉ có `dan_de`/`default` (không có `stl`/`btl`) → return `DEFAULT_UNKNOWN` (0.3).

### D4 — Shared dedupe helper

Extract từ `expert_winrate_service._dedupe_day`:

```python
# app/services/expert_pick_eval.py (NEW, thin module)

def dedupe_picks_for_eval(picks: list[dict]) -> list[dict]:
    """Per target_date group: canonical username + latest per (user, pick_type)."""

def aggregate_hit_stats(picks_by_date, draw_lookup) -> dict[str, dict[str, dict]]:
    """Returns stats[user][pick_type] = {hits, total}."""
```

`run_backtest()` refactor gọi helper này thay vì loop thô.

### D5 — Period strategy

| Period | Khi nào dùng | Refresh |
|--------|--------------|---------|
| `2026-06` | UI default đến khi có đủ `rolling_90d` | Manual + sau backfill |
| `rolling_90d` | Khi `dates_evaluated ≥ 60` trong 90 ngày | Sau `run_daily_settlement` (optional hook v2.1) |
| Live backtest | Fallback khi DB trống | Mỗi request (cached 1x/request) |

`expert_performance()` default period: env `EXPERT_PERF_PERIOD` hoặc `2026-06`.

### D6 — Backfill ưu tiên cao thủ dàn

Mở rộng v1 task T6.2:

- Crawl **full thread pages** topic dàn 40s/36s/64s tháng 6 (không chỉ ngày cuối tháng)
- Verify list: `himle79`, `Xuannd`, `Binhrau1`, `Thuoclao6996`, `danv`, `No1.XS`
- Acceptance: mỗi user ≥ 15 evaluated days trong tháng 6 (hoặc tối đa ngày có quay nếu user chốt ít hơn)

### D7 — Audit tooling

`scripts/audit_expert_winrate.py`:

```
--users himle79,Xuannd
--period 2026-06
--compare-trackrecord xsmb_cao_thu_trackrecord.md  # optional parse
```

Output bảng: user | pick_type | JSON W | DB hits/total | backtest | delta | PASS/FAIL

## Files dự kiến thay đổi

| File | Thay đổi |
|------|----------|
| `app/services/expert_pick_eval.py` | NEW — shared dedupe + aggregate |
| `app/services/expert_backtest_service.py` | Dùng shared dedupe |
| `app/services/expert_winrate_service.py` | Dùng shared module; export `DAN_FAMILY` lookup |
| `app/services/expert_scorer.py` | `expert_weight` D3; `expert_performance` D2 |
| `app/services/forum_recommendation_service.py` | `dan_board` performance qua resolved pick_type |
| `scripts/audit_expert_winrate.py` | NEW |
| `scripts/backfill_forum_picks_month.py` | Full-page crawl chăn nuôi |
| `extension/src/popup/popup.html` | Legend W vs Hiệu suất |
| `extension/src/popup/popup.ts` | Sort toggle; period hint |
| `tests/test_expert_performance_lookup.py` | NEW |
| `tests/test_expert_weight_category.py` | NEW |

## Rủi ro

| Rủi ro | Mitigation |
|--------|------------|
| Backfill forum chậm / rate limit | `--skip-existing`, batch sleep, resume |
| Track record thủ công lệch parse | Audit script + manual spot-check 5 ngày |
| Đổi weight STL làm đề xuất lô khác | Chỉ ảnh hưởng user chốt cross-category; document trong changelog |
| Period 2026-06 lỗi thời | `rolling_90d` + UI hiển thị period label |
