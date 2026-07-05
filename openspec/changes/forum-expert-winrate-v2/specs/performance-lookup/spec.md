# Spec Delta: Expert Performance Lookup

## MODIFIED Requirements

### REQ-EP-003: `live_experts.performance` từ DB (v2)

`GET /forum/recommendations` → `live_experts[]`, `dan_board[]`, `de_by_expert[]` SHALL populate `performance` qua `expert_performance(user, pick_type, period)`.

**Lookup order (v2 — thay thế v1):**

1. `(canonical_user, pick_type, period)` trong `expert_win_rates`
2. **Dan family** — nếu `pick_type == "dan_de"` hoặc request từ `_collect_dan_board`:
   - Thử lần lượt `dan_40s`, `dan_36s`, `dan_64s`
   - Chọn row có `total` lớn nhất; hòa thì `win_rate` cao hơn
3. Nếu `pick_type` là `dan_40s`/`dan_36s`/`dan_64s` và không có row: thử `dan_de` (reverse)
4. `(canonical_user, "default", period)`
5. `run_backtest(90)` với cùng pick_type chain (đã dedupe)
6. `null` → UI `—`

**Scenario: himle79 dàn 40s tháng 6**
- GIVEN `expert_win_rates` có `(himle79, dan_40s, 2026-06)` hits=17, total=18
- WHEN `GET /forum/recommendations` → `dan_board` row user=himle79, resolved=dan_40s
- THEN `performance.rate_pct = 94.4` (hoặc 94.4 rounded 1 decimal)
- AND `expert_performance("himle79", "dan_de")` trả cùng stats (via family fallback)

**Scenario: Chưa seed — fallback backtest**
- GIVEN không có row DB cho user X, pick_type stl
- AND backtest 90d có stl 3/5
- THEN `performance = {"hits": 3, "total": 5, "rate_pct": 60.0}`

**Scenario: Không đủ mẫu**
- GIVEN total < 1
- THEN `performance = null`

---

## ADDED Requirements

### REQ-EPL-001: `performance_period` metadata

`GET /forum/recommendations` response SHALL include:

```json
{
  "performance_period": "2026-06",
  "performance_period_label": "Tháng 6/2026"
}
```

Extension dùng field này cho tooltip cột Hiệu suất.

**Scenario: Default period**
- WHEN không có env override
- THEN `performance_period = "2026-06"`

---

### REQ-EPL-002: Minimum sample hint

Khi `0 < total < 3`, API vẫn trả performance nhưng extension SHOULD hiển thị suffix `*` (mẫu nhỏ).

```json
{"hits": 1, "total": 2, "rate_pct": 50.0, "low_sample": true}
```

**Scenario: himle79 chỉ 2 ngày tháng 7**
- THEN `50.0% (1/2)*` trong UI

---

### REQ-EPL-003: Canonical username trước lookup

Mọi lookup performance SHALL dùng `canonical_username()` trước khi query DB.

**Scenario: Alias**
- GIVEN `LOKHATA 1789` → `nhcsxh`
- THEN performance đọc row `nhcsxh`
